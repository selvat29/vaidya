import frappe

from vaidya.utils import as_bool, as_list, unrestricted_doc


def _load_appointment(appointment):
	from vaidya.api.booking import _assert_party

	doc = frappe.get_doc("Appointment", appointment)
	actor = _assert_party(doc)
	return doc, actor


def _require_practitioner(actor):
	if actor not in {"practitioner", "admin"}:
		frappe.throw("Only the practitioner can write clinical notes", frappe.PermissionError)


@frappe.whitelist()
def save_note(appointment, chief_complaint=None, observations=None, advice=None, share_with_patient=0, submit=0):
	appt, actor = _load_appointment(appointment)
	_require_practitioner(actor)
	if appt.status not in {"Confirmed", "Completed"}:
		frappe.throw("Notes can be written after the visit is confirmed", frappe.ValidationError)
	existing = frappe.db.get_value("Consultation Note", {"appointment": appt.name}, "name")
	if existing:
		note = frappe.get_doc("Consultation Note", existing)
		if note.docstatus == 1:
			frappe.throw("This note is already submitted", frappe.ValidationError)
	else:
		note = frappe.new_doc("Consultation Note")
		note.appointment = appt.name
	note.chief_complaint = chief_complaint or note.chief_complaint
	note.observations = observations or note.observations
	note.advice = advice or note.advice
	note.share_with_patient = 1 if as_bool(share_with_patient) else 0
	note.flags.ignore_permissions = True
	note.save()
	if as_bool(submit):
		note.flags.ignore_permissions = True
		note.submit()
	return _note_payload(note)


@frappe.whitelist()
def submit_prescription(appointment, items, advice=None):
	appt, actor = _load_appointment(appointment)
	_require_practitioner(actor)
	if appt.status not in {"Confirmed", "Completed"}:
		frappe.throw("A prescription follows a confirmed consultation", frappe.ValidationError)
	rows = as_list(items)
	if not rows:
		frappe.throw("Add at least one medicine", frappe.ValidationError)
	existing = frappe.db.get_value("Prescription", {"appointment": appt.name}, "name")
	if existing:
		prescription = frappe.get_doc("Prescription", existing)
		if prescription.docstatus == 1:
			frappe.throw("This prescription is already submitted", frappe.ValidationError)
		prescription.set("items", [])
	else:
		prescription = frappe.new_doc("Prescription")
		prescription.appointment = appt.name
	if advice:
		prescription.advice = advice
	for row in rows:
		prescription.append(
			"items",
			{
				"medicine_name": row.get("medicine_name"),
				"dose": row.get("dose"),
				"frequency": row.get("frequency"),
				"duration": row.get("duration"),
				"anupana": row.get("anupana"),
			},
		)
	prescription.flags.ignore_permissions = True
	prescription.save()
	prescription.flags.ignore_permissions = True
	prescription.submit()
	return _prescription_payload(prescription)


@frappe.whitelist()
def get_for_appointment(appointment):
	appt, actor = _load_appointment(appointment)
	note_name = frappe.db.get_value("Consultation Note", {"appointment": appt.name}, "name")
	rx_name = frappe.db.get_value("Prescription", {"appointment": appt.name}, "name")
	note = unrestricted_doc("Consultation Note", note_name) if note_name else None
	prescription = unrestricted_doc("Prescription", rx_name) if rx_name else None
	if actor == "patient":
		if note and (not note.share_with_patient or note.docstatus != 1):
			note = None
		if prescription and prescription.docstatus != 1:
			prescription = None
	return {
		"note": _note_payload(note) if note else None,
		"prescription": _prescription_payload(prescription) if prescription else None,
	}


def _note_payload(note):
	return {
		"name": note.name,
		"appointment": note.appointment,
		"chief_complaint": note.chief_complaint,
		"observations": note.observations,
		"advice": note.advice,
		"share_with_patient": note.share_with_patient,
		"docstatus": note.docstatus,
	}


def _prescription_payload(prescription):
	return {
		"name": prescription.name,
		"appointment": prescription.appointment,
		"practitioner_name": prescription.practitioner_name,
		"qualification": prescription.qualification,
		"registration_number": prescription.registration_number,
		"patient_name": prescription.patient_name,
		"patient_age": prescription.patient_age,
		"patient_gender": prescription.patient_gender,
		"advice": prescription.advice,
		"docstatus": prescription.docstatus,
		"items": [
			{
				"medicine_name": row.medicine_name,
				"dose": row.dose,
				"frequency": row.frequency,
				"duration": row.duration,
				"anupana": row.anupana,
			}
			for row in prescription.items
		],
	}
