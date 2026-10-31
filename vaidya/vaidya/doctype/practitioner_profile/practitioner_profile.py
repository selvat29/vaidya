import frappe
from frappe.model.document import Document

from vaidya.utils import is_admin


class PractitionerProfile(Document):
	def validate(self):
		if self.practitioner_type and self.practitioner_type not in {"Doctor", "Therapist"}:
			frappe.throw("Practitioner type must be Doctor or Therapist", frappe.ValidationError)
		if self.is_new():
			if self.status in {"Verified", "Rejected"} and not is_admin():
				frappe.throw("Only an admin can verify a practitioner", frappe.PermissionError)
			return
		previous = self.get_doc_before_save()
		if not previous or previous.status == self.status:
			return
		if self.status in {"Verified", "Rejected"} and not is_admin():
			frappe.throw("Only an admin can change verification status", frappe.PermissionError)
