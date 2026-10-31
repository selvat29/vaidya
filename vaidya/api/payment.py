import json

import frappe

from vaidya.api.notifications import notify_user
from vaidya.scheduling import hold_cutoff
from vaidya.utils import is_admin, require_user, sign_body


def _payment_row(appointment):
	return frappe.db.get_value(
		"Appointment Payment",
		{"appointment": appointment, "status": ["in", ["Created", "Paid"]]},
		["name", "razorpay_order_id", "status", "amount"],
		as_dict=True,
	)


@frappe.whitelist()
def create_order(appointment):
	user = require_user()
	doc = frappe.get_doc("Appointment", appointment)
	patient_user = frappe.db.get_value("Patient Profile", doc.patient, "user")
	if user != patient_user and not is_admin(user):
		frappe.throw("Only the patient can pay for this appointment", frappe.PermissionError)
	if doc.status != "Pending Payment":
		frappe.throw("This appointment is not awaiting payment", frappe.ValidationError)
	if doc.creation and doc.creation < hold_cutoff():
		expire_appointment(doc.name)
		frappe.throw("This hold has expired. Book the slot again.", frappe.ValidationError)
	existing = _payment_row(doc.name)
	if existing and existing.status == "Paid":
		return _order_payload(doc, existing.razorpay_order_id, existing.amount)
	if existing and existing.status == "Created":
		return _order_payload(doc, existing.razorpay_order_id, existing.amount)
	amount_paise = int(round(float(doc.fee) * 100))
	order_id = _razorpay_order(doc.name, amount_paise)
	payment = frappe.get_doc(
		{
			"doctype": "Appointment Payment",
			"appointment": doc.name,
			"razorpay_order_id": order_id,
			"amount": doc.fee,
			"status": "Created",
			"currency": "INR",
		}
	)
	payment.insert(ignore_permissions=True)
	return _order_payload(doc, order_id, doc.fee)


def _order_payload(doc, order_id, amount):
	dev_mode = str(order_id).startswith("order_dev_")
	return {
		"appointment": doc.name,
		"order_id": order_id,
		"amount": int(round(float(amount) * 100)),
		"currency": "INR",
		"key_id": frappe.conf.get("razorpay_key_id") or ("rzp_test_dev" if dev_mode else None),
		"dev_mode": dev_mode,
	}


def _razorpay_order(receipt, amount_paise):
	key_id = frappe.conf.get("razorpay_key_id")
	key_secret = frappe.conf.get("razorpay_key_secret")
	if not key_id or not key_secret:
		if frappe.conf.get("developer_mode") or frappe.flags.get("in_test") or frappe.conf.get("vaidya_expose_otp"):
			return "order_dev_" + frappe.generate_hash(length=12)
		frappe.throw("Razorpay is not configured", frappe.ValidationError)
	import requests

	response = requests.post(
		"https://api.razorpay.com/v1/orders",
		auth=(key_id, key_secret),
		json={"amount": amount_paise, "currency": "INR", "receipt": receipt, "payment_capture": 1},
		timeout=30,
	)
	if response.status_code >= 300:
		frappe.throw("Could not start the payment", frappe.ValidationError)
	return response.json()["id"]


@frappe.whitelist()
def mark_paid_dev(appointment):
	if not (frappe.conf.get("developer_mode") or frappe.flags.get("in_test") or frappe.conf.get("vaidya_expose_otp")):
		frappe.throw("Not allowed", frappe.PermissionError)
	user = require_user()
	doc = frappe.get_doc("Appointment", appointment)
	patient_user = frappe.db.get_value("Patient Profile", doc.patient, "user")
	if user != patient_user and not is_admin(user):
		frappe.throw("Only the patient can confirm this payment", frappe.PermissionError)
	payment = _payment_row(doc.name)
	if not payment or not str(payment.razorpay_order_id).startswith("order_dev_"):
		frappe.throw("This appointment has no developer payment", frappe.ValidationError)
	mark_paid(payment.razorpay_order_id, "pay_dev_" + frappe.generate_hash(length=8))
	return {"ok": True, "appointment": doc.name, "status": "Confirmed"}


@frappe.whitelist(allow_guest=True)
def webhook():
	secret = frappe.conf.get("razorpay_webhook_secret")
	if not secret:
		frappe.throw("Webhook secret is not configured", frappe.AuthenticationError)
	body = frappe.request.get_data() or b""
	signature = frappe.get_request_header("X-Razorpay-Signature") or ""
	expected = sign_body(secret, body)
	import hmac

	if not hmac.compare_digest(expected, signature):
		frappe.throw("Invalid signature", frappe.AuthenticationError)
	payload = json.loads(body.decode() or "{}")
	event = payload.get("event")
	if event in {"payment.captured", "order.paid"}:
		entity = (((payload.get("payload") or {}).get("payment") or {}).get("entity")) or {}
		order_id = entity.get("order_id")
		payment_id = entity.get("id")
		if order_id and payment_id:
			mark_paid(order_id, payment_id)
	return {"ok": True}


def mark_paid(order_id, payment_id):
	payment_name = frappe.db.get_value("Appointment Payment", {"razorpay_order_id": order_id}, "name")
	if not payment_name:
		frappe.throw("Payment order not found", frappe.DoesNotExistError)
	payment = frappe.get_doc("Appointment Payment", payment_name)
	appointment = frappe.get_doc("Appointment", payment.appointment)
	if payment.status == "Paid" and appointment.status == "Confirmed":
		return
	payment.status = "Paid"
	payment.razorpay_payment_id = payment_id
	payment.save(ignore_permissions=True)
	if appointment.status == "Pending Payment":
		appointment.status = "Confirmed"
		appointment.save(ignore_permissions=True)
		patient_user = frappe.db.get_value("Patient Profile", appointment.patient, "user")
		practitioner_user = frappe.db.get_value("Practitioner Profile", appointment.practitioner, "user")
		message = (
			f"{appointment.therapy} · {appointment.visit_type} · {appointment.starts_on}. "
			f"Fee INR {appointment.fee}."
		)
		notify_user(patient_user, f"Appointment {appointment.name} confirmed", message, "Appointment", appointment.name)
		notify_user(
			practitioner_user,
			f"New booking {appointment.name}",
			message,
			"Appointment",
			appointment.name,
		)


def expire_appointment(name):
	appointment = frappe.get_doc("Appointment", name)
	if appointment.status != "Pending Payment":
		return
	appointment.status = "Cancelled"
	appointment.save(ignore_permissions=True)
	for payment_name in frappe.get_all(
		"Appointment Payment", filters={"appointment": name, "status": "Created"}, pluck="name"
	):
		frappe.db.set_value("Appointment Payment", payment_name, "status", "Expired")


def expire_pending_payments():
	cutoff = hold_cutoff()
	names = frappe.get_all(
		"Appointment",
		filters={"status": "Pending Payment", "creation": ["<", cutoff]},
		pluck="name",
		ignore_permissions=True,
	)
	for name in names:
		expire_appointment(name)
