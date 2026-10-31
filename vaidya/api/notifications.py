import frappe

from vaidya.utils import require_user


def notify_user(user, subject, message, doctype=None, docname=None):
	if not user or user == "Guest":
		return
	log = frappe.get_doc(
		{
			"doctype": "Notification Log",
			"subject": subject,
			"email_content": message,
			"for_user": user,
			"document_type": doctype,
			"document_name": docname,
			"from_user": frappe.session.user if frappe.session.user not in (None, "Guest") else user,
		}
	)
	log.insert(ignore_permissions=True)
	email = frappe.db.get_value("User", user, "email")
	if email and not str(email).endswith("@vaidya.local"):
		frappe.sendmail(recipients=[email], subject=subject, message=message, delayed=True)
	_deliver_sms(user, message)


def _deliver_sms(user, message):
	url = frappe.conf.get("vaidya_sms_url")
	phone = frappe.db.get_value("User", user, "mobile_no")
	if not url or not phone:
		return
	try:
		import requests

		requests.post(url, json={"phone": phone, "message": message}, timeout=10)
	except Exception:
		frappe.log_error(title="Vaidya notification SMS failed")


def on_prescription_submit(doc, method=None):
	patient_user = frappe.db.get_value("Patient Profile", doc.patient, "user")
	notify_user(
		patient_user,
		f"Prescription ready for {doc.appointment}",
		f"{doc.practitioner_name} submitted a prescription for your visit.",
		"Prescription",
		doc.name,
	)


@frappe.whitelist()
def mine():
	user = require_user()
	return frappe.get_all(
		"Notification Log",
		filters={"for_user": user},
		fields=["name", "subject", "email_content", "document_type", "document_name", "creation", "read"],
		order_by="creation desc",
		limit=30,
		ignore_permissions=True,
	)
