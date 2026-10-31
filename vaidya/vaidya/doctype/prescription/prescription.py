import frappe
from frappe.model.document import Document

from vaidya.utils import age_years


class Prescription(Document):
	def before_insert(self):
		self._copy_header()

	def validate(self):
		self._copy_header()
		if self.appointment:
			status = frappe.db.get_value("Appointment", self.appointment, "status")
			if status not in {"Confirmed", "Completed"}:
				frappe.throw("A prescription follows a confirmed consultation", frappe.ValidationError)

	def before_submit(self):
		if not self.items:
			frappe.throw("Add at least one medicine", frappe.ValidationError)
		if not self.registration_number:
			frappe.throw(
				"Practitioner registration number is required on a prescription",
				frappe.ValidationError,
			)

	def on_submit(self):
		from vaidya.api.notifications import on_prescription_submit

		on_prescription_submit(self)

	def _copy_header(self):
		if not self.appointment:
			return
		patient, practitioner = frappe.db.get_value(
			"Appointment", self.appointment, ["patient", "practitioner"]
		)
		self.patient = patient
		self.practitioner = practitioner
		profile = frappe.db.get_value(
			"Practitioner Profile",
			practitioner,
			["practitioner_name", "qualifications", "registration_number"],
			as_dict=True,
		)
		person = frappe.db.get_value(
			"Patient Profile",
			patient,
			["patient_name", "date_of_birth", "gender"],
			as_dict=True,
		)
		self.practitioner_name = profile.practitioner_name
		self.qualification = profile.qualifications
		self.registration_number = profile.registration_number
		self.patient_name = person.patient_name
		self.patient_age = age_years(person.date_of_birth)
		self.patient_gender = person.gender
