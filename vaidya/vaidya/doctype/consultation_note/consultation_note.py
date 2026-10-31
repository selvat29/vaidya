import frappe
from frappe.model.document import Document


class ConsultationNote(Document):
	def before_insert(self):
		self._copy_parties()

	def validate(self):
		self._copy_parties()
		if self.appointment:
			status = frappe.db.get_value("Appointment", self.appointment, "status")
			if status not in {"Confirmed", "Completed"}:
				frappe.throw("Notes can be written after the visit is confirmed", frappe.ValidationError)

	def _copy_parties(self):
		if not self.appointment:
			return
		patient, practitioner = frappe.db.get_value(
			"Appointment", self.appointment, ["patient", "practitioner"]
		)
		self.patient = patient
		self.practitioner = practitioner
