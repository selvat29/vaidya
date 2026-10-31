import hashlib
import hmac
import re
from datetime import datetime, timedelta

import frappe

PHONE_RE = re.compile(r"^[6-9]\d{9}$")
APP_ROLES = {"Patient", "Practitioner"}
VISIT_TYPES = ("Clinic", "Video", "Home")
FEE_FIELDS = {"Clinic": "fee_clinic", "Video": "fee_video", "Home": "fee_home"}
VISIT_FLAGS = {"Clinic": "allow_clinic", "Video": "allow_video", "Home": "allow_home"}
HOLD_MINUTES = 15
CONSENT_TEXT = (
	"I consent to this consultation and to sharing my name, age, contact details, "
	"and the reason for the visit with the selected practitioner. "
	"This includes in-clinic, video, and home visits."
)


def prepare_request():
	"""Token-authenticated mobile and web clients do not carry a Desk CSRF cookie."""
	request = getattr(frappe.local, "request", None)
	if request and (request.path or "").startswith("/api/method/vaidya."):
		frappe.flags.ignore_csrf = True


def normalize_phone(phone):
	digits = re.sub(r"\D", "", phone or "")
	if digits.startswith("91") and len(digits) == 12:
		digits = digits[2:]
	if len(digits) == 11 and digits.startswith("0"):
		digits = digits[1:]
	if not PHONE_RE.match(digits):
		frappe.throw("Enter a valid 10-digit Indian mobile number", frappe.ValidationError)
	return digits


def user_email(phone):
	return f"{normalize_phone(phone)}@vaidya.local"


def require_user():
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw("Please sign in", frappe.AuthenticationError)
	return user


def roles_of(user=None):
	return set(frappe.get_roles(user or frappe.session.user))


def is_admin(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(roles_of(user) & {"System Manager", "Vaidya Admin"})


def as_bool(value):
	if isinstance(value, bool):
		return value
	return str(value).strip().lower() in {"1", "true", "yes", "on"}


def as_list(value):
	if not value:
		return []
	if isinstance(value, str):
		value = frappe.parse_json(value)
	return list(value)


def hash_otp(phone, otp):
	return hashlib.sha256(f"{phone}:{otp}".encode()).hexdigest()


def sign_body(secret, body):
	return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def expose_otp():
	return bool(
		frappe.conf.get("developer_mode")
		or frappe.conf.get("vaidya_expose_otp")
		or frappe.flags.get("in_test")
		or frappe.flags.get("vaidya_expose_otp")
	)


def as_time(value):
	if value is None or value == "":
		frappe.throw("A start and end time are required", frappe.ValidationError)
	if isinstance(value, timedelta):
		return (datetime.min + value).time()
	if isinstance(value, datetime):
		return value.time()
	text = str(value).strip()
	for fmt in ("%H:%M:%S", "%H:%M:%S.%f", "%H:%M"):
		try:
			return datetime.strptime(text, fmt).time()
		except ValueError:
			continue
	frappe.throw(f"Invalid time {value}", frappe.ValidationError)


def combine(day, clock):
	return datetime.combine(frappe.utils.getdate(day), as_time(clock))


def issue_token(user_name):
	user = frappe.get_doc("User", user_name)
	if not user.api_key:
		user.api_key = frappe.generate_hash(length=15)
	api_secret = frappe.generate_hash(length=15)
	user.api_secret = api_secret
	user.save(ignore_permissions=True)
	return f"{user.api_key}:{api_secret}"


def ensure_user(phone, full_name, role):
	if role not in APP_ROLES:
		frappe.throw("Role must be Patient or Practitioner", frappe.ValidationError)
	phone = normalize_phone(phone)
	email = f"{phone}@vaidya.local"
	if frappe.db.exists("User", email):
		existing = roles_of(email)
		other = (APP_ROLES - {role}) & existing
		if other and role not in existing:
			frappe.throw(
				"This mobile number is already registered with a different role",
				frappe.ValidationError,
			)
		if role not in existing:
			user = frappe.get_doc("User", email)
			user.append("roles", {"role": role})
			user.save(ignore_permissions=True)
		return email
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": (full_name or phone).strip(),
			"mobile_no": phone,
			"send_welcome_email": 0,
			"user_type": "Website User",
			"roles": [{"role": role}],
		}
	)
	user.insert(ignore_permissions=True)
	return user.name


def profile_name(doctype, user=None):
	user = user or frappe.session.user
	return frappe.db.get_value(doctype, {"user": user}, "name")


def unrestricted_doc(doctype, name):
	previous = frappe.flags.ignore_permissions
	frappe.flags.ignore_permissions = True
	try:
		return frappe.get_doc(doctype, name)
	finally:
		frappe.flags.ignore_permissions = previous


def age_years(dob):
	if not dob:
		return None
	today = frappe.utils.getdate()
	born = frappe.utils.getdate(dob)
	return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
