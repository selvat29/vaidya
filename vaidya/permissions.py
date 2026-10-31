import frappe

from vaidya.utils import is_admin, profile_name


def _escape(value):
	return frappe.db.escape(value)


def patient_query(user, doctype=None):
	if is_admin(user):
		return ""
	return f"`tabPatient Profile`.user = {_escape(user)}"


def patient_has_permission(doc, ptype="read", user=None, debug=False):
	user = user or frappe.session.user
	if is_admin(user):
		return True
	return doc.user == user and ptype in {"read", "write"}


def practitioner_query(user, doctype=None):
	if is_admin(user):
		return ""
	own = profile_name("Practitioner Profile", user)
	if not own:
		return "1=0"
	return f"`tabPractitioner Profile`.name = {_escape(own)}"


def practitioner_has_permission(doc, ptype="read", user=None, debug=False):
	user = user or frappe.session.user
	if is_admin(user):
		return True
	return doc.user == user and ptype in {"read", "write", "create"}


def _party_clause(user, patient_field, practitioner_field):
	if is_admin(user):
		return ""
	clauses = []
	patient = profile_name("Patient Profile", user)
	practitioner = profile_name("Practitioner Profile", user)
	if patient:
		clauses.append(f"{patient_field} = {_escape(patient)}")
	if practitioner:
		clauses.append(f"{practitioner_field} = {_escape(practitioner)}")
	if not clauses:
		return "1=0"
	return "(" + " or ".join(clauses) + ")"


def appointment_query(user, doctype=None):
	return _party_clause(user, "`tabAppointment`.patient", "`tabAppointment`.practitioner")


def appointment_has_permission(doc, ptype="read", user=None, debug=False):
	user = user or frappe.session.user
	if is_admin(user):
		return True
	if ptype != "read":
		return False
	patient_user = frappe.db.get_value("Patient Profile", doc.patient, "user") if doc.patient else None
	practitioner_user = (
		frappe.db.get_value("Practitioner Profile", doc.practitioner, "user") if doc.practitioner else None
	)
	return user in {patient_user, practitioner_user}


def consultation_query(user, doctype=None):
	return _party_clause(user, "`tabConsultation Note`.patient", "`tabConsultation Note`.practitioner")


def consultation_has_permission(doc, ptype="read", user=None, debug=False):
	user = user or frappe.session.user
	if is_admin(user):
		return True
	practitioner_user = (
		frappe.db.get_value("Practitioner Profile", doc.practitioner, "user") if doc.practitioner else None
	)
	if user == practitioner_user:
		return ptype in {"read", "write", "create", "submit", "cancel"}
	if ptype != "read" or not doc.share_with_patient or doc.docstatus != 1:
		return False
	patient_user = frappe.db.get_value("Patient Profile", doc.patient, "user") if doc.patient else None
	return user == patient_user


def prescription_query(user, doctype=None):
	return _party_clause(user, "`tabPrescription`.patient", "`tabPrescription`.practitioner")


def prescription_has_permission(doc, ptype="read", user=None, debug=False):
	user = user or frappe.session.user
	if is_admin(user):
		return True
	practitioner_user = (
		frappe.db.get_value("Practitioner Profile", doc.practitioner, "user") if doc.practitioner else None
	)
	if user == practitioner_user:
		return ptype in {"read", "write", "create", "submit", "cancel"}
	if ptype != "read" or doc.docstatus != 1:
		return False
	patient_user = frappe.db.get_value("Patient Profile", doc.patient, "user") if doc.patient else None
	return user == patient_user


def _owned_schedule(user, doctype):
	if is_admin(user):
		return ""
	practitioner = profile_name("Practitioner Profile", user)
	if not practitioner:
		return "1=0"
	return f"`tab{doctype}`.practitioner = {_escape(practitioner)}"


def availability_query(user, doctype=None):
	return _owned_schedule(user, "Practitioner Availability")


def leave_query(user, doctype=None):
	return _owned_schedule(user, "Practitioner Leave")


def _schedule_permission(doc, ptype, user):
	user = user or frappe.session.user
	if is_admin(user):
		return True
	owner = frappe.db.get_value("Practitioner Profile", doc.practitioner, "user") if doc.practitioner else None
	return owner == user and ptype in {"read", "write", "create", "delete"}


def availability_has_permission(doc, ptype="read", user=None, debug=False):
	return _schedule_permission(doc, ptype, user)


def leave_has_permission(doc, ptype="read", user=None, debug=False):
	return _schedule_permission(doc, ptype, user)
