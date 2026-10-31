import frappe
from frappe.model.document import Document

from vaidya.scheduling import busy_ranges, matching_slot, overlaps


class Appointment(Document):
	def validate(self):
		if self.is_new() and not self.consent:
			frappe.throw("Consent is required before booking", frappe.ValidationError)
		if self.starts_on and self.ends_on and self.ends_on <= self.starts_on:
			frappe.throw("End time must be after the start time", frappe.ValidationError)
		if self.is_new():
			slot = matching_slot(self.practitioner, self.visit_type, self.starts_on)
			if not slot:
				frappe.throw("That slot is no longer available", frappe.ValidationError)
			self.starts_on, self.ends_on = slot
		if self.status in {"Pending Payment", "Confirmed", "Completed"}:
			start = frappe.utils.get_datetime(self.starts_on)
			end = frappe.utils.get_datetime(self.ends_on)
			if overlaps(busy_ranges(self.practitioner, start.date(), ignore_appointment=self.name), start, end):
				frappe.throw("That slot is no longer available", frappe.ValidationError)
