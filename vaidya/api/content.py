import frappe


@frappe.whitelist(allow_guest=True)
def get_home(region=None):
	blocks = frappe.get_all(
		"Content Block",
		filters={"publish": 1},
		fields=["name", "title", "body", "image", "placement", "region", "sort_order"],
		order_by="sort_order asc, modified asc",
		ignore_permissions=True,
	)
	if region:
		blocks = [row for row in blocks if not row.region or row.region == region]
	therapies = frappe.get_all(
		"Therapy",
		fields=["name", "therapy_name", "summary", "image", "sort_order"],
		order_by="sort_order asc, therapy_name asc",
		ignore_permissions=True,
	)
	testimonials = frappe.get_all(
		"Testimonial",
		filters={"publish": 1},
		fields=["name", "quote", "display_name", "rating", "region", "practitioner", "photo"],
		order_by="modified desc",
		ignore_permissions=True,
	)
	if region:
		testimonials = [row for row in testimonials if not row.region or row.region == region]
	regions = frappe.get_all(
		"Region",
		fields=["name", "region_name", "state", "city"],
		order_by="region_name asc",
		ignore_permissions=True,
	)
	return {
		"regions": regions,
		"blocks": blocks,
		"therapies": therapies,
		"testimonials": testimonials[:12],
	}
