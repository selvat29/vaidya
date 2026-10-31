import frappe

from vaidya.utils import FEE_FIELDS, VISIT_TYPES, as_bool, as_list, is_admin, profile_name, require_user


def profile_card(name, include_private=False):
	from vaidya.utils import unrestricted_doc

	doc = unrestricted_doc("Practitioner Profile", name)
	therapies = frappe.get_all(
		"Practitioner Therapy",
		filters={"parent": name},
		pluck="therapy",
		ignore_permissions=True,
	)
	regions = frappe.get_all(
		"Practitioner Region",
		filters={"parent": name},
		pluck="region",
		ignore_permissions=True,
	)
	card = {
		"name": doc.name,
		"practitioner_name": doc.practitioner_name,
		"practitioner_type": doc.practitioner_type,
		"qualifications": doc.qualifications,
		"bio": doc.bio,
		"photo": doc.photo,
		"clinic_address": doc.clinic_address,
		"years_experience": doc.get("years_experience") or 0,
		"languages": doc.get("languages") or "",
		"fees": {visit.lower(): doc.get(field) or 0 for visit, field in FEE_FIELDS.items()},
		"therapies": therapies,
		"regions": regions,
		"rating_average": doc.rating_average or 0,
		"rating_count": doc.rating_count or 0,
		"status": doc.status if include_private else None,
	}
	if include_private:
		card["registration_number"] = doc.registration_number
		card["phone"] = doc.phone
		card["rejection_reason"] = doc.rejection_reason
	else:
		card.pop("status", None)
	return card


@frappe.whitelist(allow_guest=True)
def search(region, therapy=None, visit_type=None):
	if not region or not frappe.db.exists("Region", region):
		frappe.throw("Choose a region", frappe.ValidationError)
	if visit_type and visit_type not in VISIT_TYPES:
		frappe.throw("Visit type must be Clinic, Video, or Home", frappe.ValidationError)
	names = frappe.get_all(
		"Practitioner Region", filters={"region": region}, pluck="parent", ignore_permissions=True
	)
	if therapy:
		offered = set(
			frappe.get_all(
				"Practitioner Therapy", filters={"therapy": therapy}, pluck="parent", ignore_permissions=True
			)
		)
		names = [name for name in names if name in offered]
	cards = []
	for name in names:
		values = frappe.db.get_value(
			"Practitioner Profile",
			name,
			["status", "fee_clinic", "fee_video", "fee_home"],
		)
		if not values:
			continue
		status, fee_clinic, fee_video, fee_home = values
		if status != "Verified":
			continue
		fees = {"Clinic": fee_clinic or 0, "Video": fee_video or 0, "Home": fee_home or 0}
		if visit_type and fees[visit_type] <= 0:
			continue
		cards.append(profile_card(name))
	cards.sort(key=lambda row: (-(row["rating_average"] or 0), row["practitioner_name"] or ""))
	return cards


@frappe.whitelist(allow_guest=True)
def get_profile(name):
	if not frappe.db.exists("Practitioner Profile", name):
		frappe.throw("Practitioner not found", frappe.DoesNotExistError)
	user = frappe.session.user
	include_private = False
	if user and user != "Guest":
		include_private = is_admin(user) or profile_name("Practitioner Profile", user) == name
	status = frappe.db.get_value("Practitioner Profile", name, "status")
	if status != "Verified" and not include_private:
		frappe.throw("Practitioner not found", frappe.DoesNotExistError)
	card = profile_card(name, include_private=include_private)
	card["testimonials"] = frappe.get_all(
		"Testimonial",
		filters={"publish": 1, "practitioner": name},
		fields=["quote", "display_name", "rating", "photo"],
		ignore_permissions=True,
	)
	return card


@frappe.whitelist()
def save_profile(**kwargs):
	user = require_user()
	if "Practitioner" not in frappe.get_roles(user) and not is_admin(user):
		frappe.throw("Only practitioners can edit a practice profile", frappe.PermissionError)
	name = profile_name("Practitioner Profile", user)
	if not name:
		frappe.throw("Practitioner profile not found", frappe.DoesNotExistError)
	doc = frappe.get_doc("Practitioner Profile", name)
	for field in (
		"practitioner_name",
		"practitioner_type",
		"qualifications",
		"registration_number",
		"bio",
		"photo",
		"clinic_address",
		"phone",
		"languages",
	):
		if field in kwargs and kwargs[field] is not None:
			doc.set(field, kwargs[field])
	if "years_experience" in kwargs and kwargs["years_experience"] not in (None, ""):
		doc.years_experience = int(kwargs["years_experience"])
	for field in ("fee_clinic", "fee_video", "fee_home"):
		if field in kwargs and kwargs[field] not in (None, ""):
			doc.set(field, float(kwargs[field]))
	if "therapies" in kwargs:
		doc.set("therapies", [])
		for therapy in as_list(kwargs.get("therapies")):
			value = therapy.get("therapy") if isinstance(therapy, dict) else therapy
			if value:
				doc.append("therapies", {"therapy": value})
	if "regions" in kwargs:
		doc.set("regions", [])
		for region in as_list(kwargs.get("regions")):
			value = region.get("region") if isinstance(region, dict) else region
			if value:
				doc.append("regions", {"region": value})
	if doc.status == "Rejected":
		doc.status = "Draft"
		doc.rejection_reason = ""
	doc.save(ignore_permissions=True)
	return profile_card(doc.name, include_private=True)


@frappe.whitelist()
def submit_for_review():
	user = require_user()
	name = profile_name("Practitioner Profile", user)
	if not name:
		frappe.throw("Practitioner profile not found", frappe.PermissionError)
	doc = frappe.get_doc("Practitioner Profile", name)
	missing = []
	if not doc.practitioner_name:
		missing.append("name")
	if not doc.practitioner_type:
		missing.append("type")
	if not doc.qualifications:
		missing.append("qualifications")
	if not doc.registration_number:
		missing.append("registration number")
	if not doc.therapies:
		missing.append("at least one therapy")
	if not doc.regions:
		missing.append("at least one region")
	if not ((doc.fee_clinic or 0) > 0 or (doc.fee_video or 0) > 0 or (doc.fee_home or 0) > 0):
		missing.append("a consultation fee")
	if missing:
		frappe.throw("Add " + ", ".join(missing) + " before submitting", frappe.ValidationError)
	doc.status = "Pending Review"
	doc.save(ignore_permissions=True)
	return profile_card(doc.name, include_private=True)


@frappe.whitelist()
def set_availability(rows):
	user = require_user()
	practitioner = profile_name("Practitioner Profile", user)
	if not practitioner:
		frappe.throw("Practitioner profile not found", frappe.PermissionError)
	for existing in frappe.get_all(
		"Practitioner Availability", filters={"practitioner": practitioner}, pluck="name"
	):
		frappe.delete_doc("Practitioner Availability", existing, ignore_permissions=True, force=True)
	saved = []
	for row in as_list(rows):
		doc = frappe.get_doc(
			{
				"doctype": "Practitioner Availability",
				"practitioner": practitioner,
				"weekday": row.get("weekday"),
				"start_time": row.get("start_time"),
				"end_time": row.get("end_time"),
				"slot_minutes": int(row.get("slot_minutes") or 30),
				"allow_clinic": 1 if as_bool(row.get("allow_clinic", 1)) else 0,
				"allow_video": 1 if as_bool(row.get("allow_video", 1)) else 0,
				"allow_home": 1 if as_bool(row.get("allow_home", 1)) else 0,
			}
		)
		doc.insert(ignore_permissions=True)
		saved.append(doc.name)
	return get_availability()


@frappe.whitelist()
def get_availability():
	user = require_user()
	practitioner = profile_name("Practitioner Profile", user)
	if not practitioner:
		frappe.throw("Practitioner profile not found", frappe.PermissionError)
	from vaidya.utils import as_time

	rows = frappe.get_all(
		"Practitioner Availability",
		filters={"practitioner": practitioner},
		fields=[
			"name",
			"weekday",
			"start_time",
			"end_time",
			"slot_minutes",
			"allow_clinic",
			"allow_video",
			"allow_home",
		],
		order_by="weekday asc, start_time asc",
	)
	for row in rows:
		row["start_time"] = as_time(row["start_time"]).strftime("%H:%M:%S")
		row["end_time"] = as_time(row["end_time"]).strftime("%H:%M:%S")
	return rows


@frappe.whitelist(allow_guest=True)
def get_slots(practitioner, date, visit_type):
	from vaidya.scheduling import iter_slots

	if frappe.db.get_value("Practitioner Profile", practitioner, "status") != "Verified":
		frappe.throw("Practitioner not found", frappe.DoesNotExistError)
	return [
		{"start": start.strftime("%Y-%m-%d %H:%M:%S"), "end": end.strftime("%Y-%m-%d %H:%M:%S")}
		for start, end in iter_slots(practitioner, date, visit_type)
	]


@frappe.whitelist()
def save_patient_profile(patient_name=None, region=None, date_of_birth=None, gender=None, address=None):
	user = require_user()
	name = profile_name("Patient Profile", user)
	if not name:
		frappe.throw("Patient profile not found", frappe.PermissionError)
	doc = frappe.get_doc("Patient Profile", name)
	if patient_name:
		doc.patient_name = patient_name
	if region:
		doc.region = region
	if date_of_birth:
		doc.date_of_birth = date_of_birth
	if gender:
		doc.gender = gender
	if address is not None:
		doc.address = address
	doc.save(ignore_permissions=True)
	return {
		"name": doc.name,
		"patient_name": doc.patient_name,
		"phone": doc.phone,
		"region": doc.region,
		"date_of_birth": str(doc.date_of_birth) if doc.date_of_birth else None,
		"gender": doc.gender,
		"address": doc.address,
	}
