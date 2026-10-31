import frappe
from frappe.model.document import Document

from vaidya.utils import as_time


class PractitionerAvailability(Document):
	def validate(self):
		start = as_time(self.start_time)
		end = as_time(self.end_time)
		if end <= start:
			frappe.throw("End time must be after start time", frappe.ValidationError)
		if int(self.slot_minutes or 0) <= 0:
			frappe.throw("Slot length must be at least one minute", frappe.ValidationError)
