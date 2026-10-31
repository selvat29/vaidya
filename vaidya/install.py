import frappe

REGIONS = [
	("Kochi", "Kerala", "Kochi"),
	("Bengaluru", "Karnataka", "Bengaluru"),
	("Pune", "Maharashtra", "Pune"),
	("Jaipur", "Rajasthan", "Jaipur"),
	("Varanasi", "Uttar Pradesh", "Varanasi"),
]

THERAPIES = [
	("Panchakarma", "Deep detox and rejuvenation", 1),
	("Abhyanga", "Warm herbal oil massage", 2),
	("Shirodhara", "Calming oil flow therapy", 3),
	("Herbal medicine", "Personalised formulations", 4),
	("Diet & lifestyle", "Dosha-based guidance", 5),
	("Chronic care", "Joint, skin and digestion", 6),
]

HERO = {
	"title": "Healing rooted in ancient wisdom, close to home.",
	"body": (
		"Find trusted Ayurveda doctors and Panchakarma therapists in your region. "
		"Compare profiles, check availability, and book your consultation in minutes."
	),
	"placement": "home_hero",
	"sort_order": 1,
}

STEPS = [
	(
		"Choose your region",
		"Tell us where you are and we'll show practitioners who serve your area.",
		1,
	),
	(
		"Explore verified profiles",
		"Compare qualifications, specialties, experience and consultation fees.",
		2,
	),
	(
		"Book your appointment",
		"Pick a time that suits you and get confirmation from your practitioner.",
		3,
	),
]

BANNER = {
	"title": "Grow your Ayurveda practice with Vaidya",
	"body": (
		"Reach patients actively looking for care in your region. "
		"Manage your availability and appointment requests from a verified profile."
	),
	"placement": "banner",
	"sort_order": 1,
}

TESTIMONIALS = [
	(
		"Dr. Ananda explained my digestion issues without rushing. The clinic visit felt careful and unhurried.",
		"Meera Nair",
		5,
		"Kochi",
	),
	(
		"I booked Shirodhara near home and the therapist confirmed the same day. The app felt calm and clear.",
		"Arjun Menon",
		5,
		"Kochi",
	),
	(
		"Video follow-ups made it easy to stay with the diet plan between clinic visits.",
		"Lakshmi Iyer",
		4,
		"Bengaluru",
	),
]


def after_install():
	create_roles()
	seed_masters()
	if frappe.conf.get("developer_mode") or frappe.conf.get("vaidya_expose_otp"):
		seed_demo_profiles()
	frappe.db.commit()


def before_tests():
	frappe.flags.vaidya_expose_otp = True
	create_roles()
	seed_masters()


def create_roles():
	for role_name, desk_access in (("Patient", 0), ("Practitioner", 0), ("Vaidya Admin", 1)):
		if frappe.db.exists("Role", role_name):
			continue
		frappe.get_doc(
			{"doctype": "Role", "role_name": role_name, "desk_access": desk_access}
		).insert(ignore_permissions=True)


def seed_masters():
	for region_name, state, city in REGIONS:
		if frappe.db.exists("Region", region_name):
			continue
		frappe.get_doc(
			{"doctype": "Region", "region_name": region_name, "state": state, "city": city}
		).insert(ignore_permissions=True)

	for therapy_name, summary, sort_order in THERAPIES:
		if frappe.db.exists("Therapy", therapy_name):
			continue
		frappe.get_doc(
			{
				"doctype": "Therapy",
				"therapy_name": therapy_name,
				"summary": summary,
				"sort_order": sort_order,
			}
		).insert(ignore_permissions=True)

	_ensure_content(HERO)
	for title, body, sort_order in STEPS:
		_ensure_content(
			{"title": title, "body": body, "placement": "home_steps", "sort_order": sort_order}
		)
	_ensure_content(BANNER)

	for quote, display_name, rating, region in TESTIMONIALS:
		if frappe.db.exists("Testimonial", {"display_name": display_name, "quote": quote}):
			continue
		frappe.get_doc(
			{
				"doctype": "Testimonial",
				"quote": quote,
				"display_name": display_name,
				"rating": rating,
				"region": region,
				"publish": 1,
			}
		).insert(ignore_permissions=True)


def _ensure_content(data):
	if frappe.db.exists("Content Block", {"title": data["title"], "placement": data["placement"]}):
		return
	doc = {"doctype": "Content Block", "publish": 1}
	doc.update(data)
	frappe.get_doc(doc).insert(ignore_permissions=True)


def seed_demo_profiles():
	from vaidya.utils import ensure_user

	patient_user = ensure_user("9000000001", "Meera Nair", "Patient")
	if not frappe.db.exists("Patient Profile", {"user": patient_user}):
		frappe.get_doc(
			{
				"doctype": "Patient Profile",
				"user": patient_user,
				"patient_name": "Meera Nair",
				"phone": "9000000001",
				"region": "Kochi",
				"gender": "Female",
				"date_of_birth": "1992-04-12",
				"address": "Fort Kochi",
			}
		).insert(ignore_permissions=True)

	practitioner_user = ensure_user("9000000002", "Dr. Ananda Sharma", "Practitioner")
	if frappe.db.exists("Practitioner Profile", {"user": practitioner_user}):
		return
	profile = frappe.get_doc(
		{
			"doctype": "Practitioner Profile",
			"user": practitioner_user,
			"practitioner_name": "Dr. Ananda Sharma",
			"practitioner_type": "Doctor",
			"phone": "9000000002",
			"qualifications": "BAMS, MD (Kayachikitsa)",
			"registration_number": "KER-AY-10428",
			"bio": "Classical Ayurveda physician focused on digestion, joint care, and Panchakarma planning.",
			"clinic_address": "Marine Drive, Kochi",
			"fee_clinic": 800,
			"fee_video": 600,
			"fee_home": 1500,
			"status": "Verified",
			"therapies": [{"therapy": name} for name, _, _ in THERAPIES],
			"regions": [{"region": "Kochi"}],
		}
	)
	profile.insert(ignore_permissions=True)
	for weekday in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"):
		frappe.get_doc(
			{
				"doctype": "Practitioner Availability",
				"practitioner": profile.name,
				"weekday": weekday,
				"start_time": "09:00:00",
				"end_time": "13:00:00",
				"slot_minutes": 30,
				"allow_clinic": 1,
				"allow_video": 1,
				"allow_home": 1,
			}
		).insert(ignore_permissions=True)
