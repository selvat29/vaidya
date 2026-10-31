import frappe
from frappe.model.document import Document


def recompute_rating(practitioner, exclude=None):
	if not practitioner:
		return
	rows = frappe.get_all(
		"Testimonial",
		filters={"practitioner": practitioner, "publish": 1},
		fields=["name", "rating"],
	)
	rows = [row for row in rows if row.name != exclude]
	count = len(rows)
	average = (sum((row.rating or 0) for row in rows) / count) if count else 0
	frappe.db.set_value(
		"Practitioner Profile",
		practitioner,
		{"rating_average": average, "rating_count": count},
		update_modified=False,
	)


class Testimonial(Document):
	def validate(self):
		if self.rating is not None and not 1 <= int(self.rating) <= 5:
			frappe.throw("Rating must be between 1 and 5", frappe.ValidationError)

	def on_update(self):
		recompute_rating(self.practitioner)
		previous = self.get_doc_before_save()
		if previous and previous.practitioner and previous.practitioner != self.practitioner:
			recompute_rating(previous.practitioner)

	def on_trash(self):
		practitioner = self.practitioner
		super().on_trash()
		recompute_rating(practitioner, exclude=self.name)
