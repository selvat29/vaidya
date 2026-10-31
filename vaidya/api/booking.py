import frappe

from vaidya.api.notifications import notify_user
from vaidya.scheduling import fee_for, matching_slot, overlaps, busy_ranges
from vaidya.utils import CONSENT_TEXT, as_bool, is_admin, profile_name, require_user


def appointment_payload(doc):
	patient_name = frappe.db.get_value("Patient Profile", doc.patient, "patient_name")
	practitioner_name = frappe.db.get_value("Practitioner Profile", doc.practitioner, "practitioner_name")
	return {
		"name": doc.name,
		"patient": doc.patient,
		"patient_name": patient_name,
		"practitioner": doc.practitioner,
		"practitioner_name": practitioner_name,
		"therapy": doc.therapy,
		"visit_type": doc.visit_type,
		"starts_on": str(doc.starts_on),
		"ends_on": str(doc.ends_on),
		"fee": doc.fee,
		"status": doc.status,
		"meeting_url": doc.meeting_url,
		"consent": doc.consent,
	}


def _party_users(doc):
	patient_user = frappe.db.get_value("Patient Profile", doc.patient, "user")
	practitioner_user = frappe.db.get_value("Practitioner Profile", doc.practitioner, "user")
	return patient_user, practitioner_user


def _assert_party(doc):
	user = require_user()
	if is_admin(user):
		return "admin"
	patient_user, practitioner_user = _party_users(doc)
	if user == patient_user:
		return "patient"
	if user == practitioner_user:
		return "practitioner"
	frappe.throw("You cannot access this appointment", frappe.PermissionError)


@frappe.whitelist()
def create(practitioner, therapy, visit_type, starts_on, consent):
	if not as_bool(consent):
		frappe.throw("Consent is required before booking", frappe.ValidationError)
	user = require_user()
	if "Patient" not in frappe.get_roles(user):
		frappe.throw("Only patients can book an appointment", frappe.PermissionError)
	patient = profile_name("Patient Profile", user)
	if not patient:
		frappe.throw("Complete your profile before booking", frappe.ValidationError)
	if not frappe.db.exists("Practitioner Profile", practitioner):
		frappe.throw("Practitioner not found", frappe.DoesNotExistError)
	profile = frappe.get_doc("Practitioner Profile", practitioner)
	if profile.status != "Verified":
		frappe.throw("This practitioner is not available for booking", frappe.ValidationError)
	if not frappe.db.exists("Practitioner Therapy", {"parent": practitioner, "therapy": therapy}):
		frappe.throw("This practitioner does not offer that therapy", frappe.ValidationError)
	slot = matching_slot(practitioner, visit_type, starts_on)
	if not slot:
		frappe.throw("That slot is no longer available", frappe.ValidationError)
	start, end = slot
	frappe.db.sql("select name from `tabPractitioner Profile` where name=%s for update", practitioner)
	if overlaps(busy_ranges(practitioner, start.date()), start, end):
		frappe.throw("That slot is no longer available", frappe.ValidationError)
	doc = frappe.get_doc(
		{
			"doctype": "Appointment",
			"patient": patient,
			"practitioner": practitioner,
			"therapy": therapy,
			"visit_type": visit_type,
			"starts_on": start,
			"ends_on": end,
			"fee": fee_for(profile, visit_type),
			"status": "Pending Payment",
			"consent": 1,
			"consent_text": CONSENT_TEXT,
		}
	)
	doc.insert(ignore_permissions=True)
	return appointment_payload(doc)


@frappe.whitelist()
def my_appointments(status=None):
	user = require_user()
	filters = {}
	patient = profile_name("Patient Profile", user)
	practitioner = profile_name("Practitioner Profile", user)
	if patient and "Patient" in frappe.get_roles(user) and not practitioner:
		filters["patient"] = patient
	elif practitioner and "Practitioner" in frappe.get_roles(user) and not patient:
		filters["practitioner"] = practitioner
	elif patient:
		filters["patient"] = patient
	elif practitioner:
		filters["practitioner"] = practitioner
	else:
		frappe.throw("No profile found for this account", frappe.PermissionError)
	if status:
		filters["status"] = status
	names = frappe.get_all(
		"Appointment", filters=filters, pluck="name", order_by="starts_on desc", ignore_permissions=True
	)
	return [appointment_payload(frappe.get_doc("Appointment", name)) for name in names]


@frappe.whitelist()
def cancel(appointment):
	doc = frappe.get_doc("Appointment", appointment)
	actor = _assert_party(doc)
	if doc.status in {"Completed", "Cancelled", "No Show"}:
		frappe.throw("This appointment can no longer be cancelled", frappe.ValidationError)
	doc.status = "Cancelled"
	doc.save(ignore_permissions=True)
	patient_user, practitioner_user = _party_users(doc)
	subject = f"Appointment {doc.name} was cancelled"
	message = f"{doc.therapy} on {doc.starts_on} was cancelled."
	if actor != "patient":
		notify_user(patient_user, subject, message, "Appointment", doc.name)
	if actor != "practitioner":
		notify_user(practitioner_user, subject, message, "Appointment", doc.name)
	return appointment_payload(doc)


@frappe.whitelist()
def complete(appointment):
	doc = frappe.get_doc("Appointment", appointment)
	if _assert_party(doc) != "practitioner" and not is_admin():
		frappe.throw("Only the practitioner can complete this visit", frappe.PermissionError)
	if doc.status != "Confirmed":
		frappe.throw("Only a confirmed appointment can be completed", frappe.ValidationError)
	doc.status = "Completed"
	doc.save(ignore_permissions=True)
	return appointment_payload(doc)


@frappe.whitelist()
def set_meeting_url(appointment, meeting_url):
	doc = frappe.get_doc("Appointment", appointment)
	if _assert_party(doc) not in {"practitioner", "admin"}:
		frappe.throw("Only the practitioner can set the meeting link", frappe.PermissionError)
	if doc.visit_type != "Video":
		frappe.throw("Meeting links are only used for video visits", frappe.ValidationError)
	if doc.status not in {"Confirmed", "Completed"}:
		frappe.throw("Confirm the appointment before adding a meeting link", frappe.ValidationError)
	doc.meeting_url = (meeting_url or "").strip()
	doc.save(ignore_permissions=True)
	patient_user, _practitioner_user = _party_users(doc)
	notify_user(
		patient_user,
		f"Video link for {doc.name}",
		f"Your video visit link: {doc.meeting_url}",
		"Appointment",
		doc.name,
	)
	return appointment_payload(doc)
