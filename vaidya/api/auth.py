import frappe

from vaidya.utils import ensure_user, expose_otp, hash_otp, issue_token, normalize_phone, profile_name, require_user


def _public_patient(name):
	doc = frappe.get_doc("Patient Profile", name)
	return {
		"name": doc.name,
		"patient_name": doc.patient_name,
		"phone": doc.phone,
		"region": doc.region,
		"date_of_birth": doc.date_of_birth,
		"gender": doc.gender,
		"address": doc.address,
	}


def _public_practitioner(name, include_private=False):
	from vaidya.api.practitioner import profile_card

	return profile_card(name, include_private=include_private)


@frappe.whitelist(allow_guest=True)
def send_otp(phone, role):
	phone = normalize_phone(phone)
	if role not in {"Patient", "Practitioner"}:
		frappe.throw("Role must be Patient or Practitioner", frappe.ValidationError)
	window = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-1)
	recent = frappe.db.count("Login OTP", {"phone": phone, "creation": [">=", window]})
	if recent >= 5:
		frappe.throw("Too many codes were requested. Try again in an hour.", frappe.ValidationError)
	import secrets

	otp = f"{secrets.randbelow(900000) + 100000}"
	frappe.get_doc(
		{
			"doctype": "Login OTP",
			"phone": phone,
			"otp_hash": hash_otp(phone, otp),
			"expires_on": frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=10),
			"used": 0,
		}
	).insert(ignore_permissions=True)
	_deliver_sms(phone, f"Your Vaidya sign-in code is {otp}")
	payload = {"sent": True, "phone": phone}
	if expose_otp():
		payload["dev_otp"] = otp
	return payload


@frappe.whitelist(allow_guest=True)
def verify_otp(phone, otp, role, full_name=None):
	phone = normalize_phone(phone)
	if role not in {"Patient", "Practitioner"}:
		frappe.throw("Role must be Patient or Practitioner", frappe.ValidationError)
	row = frappe.db.get_value(
		"Login OTP",
		{"phone": phone, "used": 0, "otp_hash": hash_otp(phone, str(otp).strip())},
		["name", "expires_on"],
		as_dict=True,
	)
	if not row or row.expires_on < frappe.utils.now_datetime():
		frappe.throw("That code is invalid or has expired", frappe.AuthenticationError)
	frappe.db.set_value("Login OTP", row.name, "used", 1)
	user = ensure_user(phone, full_name, role)
	if full_name:
		frappe.db.set_value("User", user, "first_name", full_name.strip())
	if role == "Patient":
		_ensure_patient(user, phone, full_name)
	else:
		_ensure_practitioner(user, phone, full_name)
	token = issue_token(user)
	frappe.set_user(user)
	return {"token": token, "user": user, **me()}


@frappe.whitelist()
def me():
	user = require_user()
	roles = frappe.get_roles(user)
	payload = {
		"user": user,
		"full_name": frappe.db.get_value("User", user, "full_name") or frappe.db.get_value("User", user, "first_name"),
		"phone": frappe.db.get_value("User", user, "mobile_no"),
		"roles": [role for role in ("Patient", "Practitioner", "Vaidya Admin") if role in roles],
	}
	patient = profile_name("Patient Profile", user)
	practitioner = profile_name("Practitioner Profile", user)
	if patient:
		payload["patient"] = _public_patient(patient)
	if practitioner:
		payload["practitioner"] = _public_practitioner(practitioner, include_private=True)
	return payload


@frappe.whitelist()
def logout():
	user = require_user()
	issue_token(user)
	return {"ok": True}


def _ensure_patient(user, phone, full_name):
	if frappe.db.exists("Patient Profile", {"user": user}):
		if full_name:
			frappe.db.set_value("Patient Profile", {"user": user}, "patient_name", full_name.strip())
		return
	frappe.get_doc(
		{
			"doctype": "Patient Profile",
			"user": user,
			"patient_name": (full_name or phone).strip(),
			"phone": phone,
		}
	).insert(ignore_permissions=True)


def _ensure_practitioner(user, phone, full_name):
	if frappe.db.exists("Practitioner Profile", {"user": user}):
		return
	frappe.get_doc(
		{
			"doctype": "Practitioner Profile",
			"user": user,
			"practitioner_name": (full_name or "Practitioner").strip(),
			"phone": phone,
			"status": "Draft",
			"practitioner_type": "Doctor",
		}
	).insert(ignore_permissions=True)


def _deliver_sms(phone, message):
	url = frappe.conf.get("vaidya_sms_url")
	if not url:
		return
	try:
		import requests

		requests.post(url, json={"phone": phone, "message": message}, timeout=10)
	except Exception:
		frappe.log_error(title="Vaidya SMS failed")
