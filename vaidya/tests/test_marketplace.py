import calendar
import json
from datetime import datetime, time

import frappe
from frappe.tests.utils import FrappeTestCase

from vaidya.api import auth, booking, clinical, content, payment, practitioner
from vaidya.install import create_roles, seed_masters
from vaidya.utils import ensure_user

_PHONE = 9100000000


def next_phone():
	global _PHONE
	_PHONE += 1
	return str(_PHONE)


def next_monday():
	today = frappe.utils.getdate()
	delta = (0 - today.weekday()) % 7
	if delta == 0:
		delta = 7
	return frappe.utils.add_days(today, delta)


class TestVaidyaMarketplace(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		create_roles()
		seed_masters()
		if not frappe.db.exists("Region", "Testport"):
			frappe.get_doc(
				{"doctype": "Region", "region_name": "Testport", "state": "Kerala", "city": "Testport"}
			).insert(ignore_permissions=True)
		self.day = next_monday()
		self.weekday = calendar.day_name[self.day.weekday()]

	def make_practitioner(self, status="Verified", fees=(500, 700, 900)):
		phone = next_phone()
		user = ensure_user(phone, f"Dr {phone[-4:]}", "Practitioner")
		doc = frappe.get_doc(
			{
				"doctype": "Practitioner Profile",
				"user": user,
				"practitioner_name": f"Dr {phone[-4:]}",
				"practitioner_type": "Doctor",
				"phone": phone,
				"qualifications": "BAMS",
				"registration_number": f"REG-{phone[-4:]}",
				"bio": "Test physician",
				"fee_clinic": fees[0],
				"fee_video": fees[1],
				"fee_home": fees[2],
				"status": status,
				"therapies": [{"therapy": "Panchakarma"}],
				"regions": [{"region": "Testport"}],
			}
		)
		doc.insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Practitioner Availability",
				"practitioner": doc.name,
				"weekday": self.weekday,
				"start_time": "09:00:00",
				"end_time": "11:00:00",
				"slot_minutes": 30,
				"allow_clinic": 1,
				"allow_video": 1,
				"allow_home": 0,
			}
		).insert(ignore_permissions=True)
		return doc, user

	def make_patient(self, name="Asha"):
		phone = next_phone()
		user = ensure_user(phone, name, "Patient")
		doc = frappe.get_doc(
			{
				"doctype": "Patient Profile",
				"user": user,
				"patient_name": name,
				"phone": phone,
				"region": "Testport",
				"gender": "Female",
				"date_of_birth": "1990-01-15",
				"address": "Testport",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc, user

	def slot_start(self, hour=9, minute=0):
		return datetime.combine(self.day, time(hour, minute)).strftime("%Y-%m-%d %H:%M:%S")

	def test_otp_creates_patient_and_rejects_bad_code(self):
		phone = next_phone()
		sent = auth.send_otp(phone, "Patient")
		self.assertIn("dev_otp", sent)
		self.assertRaises(frappe.AuthenticationError, auth.verify_otp, phone, "000000", "Patient", "Nila")
		session = auth.verify_otp(phone, sent["dev_otp"], "Patient", "Nila")
		self.assertIn("token", session)
		self.assertEqual(session["patient"]["patient_name"], "Nila")
		other = auth.send_otp(phone, "Practitioner")
		self.assertRaises(
			frappe.ValidationError, auth.verify_otp, phone, other["dev_otp"], "Practitioner", "Nila"
		)
		auth.send_otp(phone, "Patient")
		self.assertRaises(frappe.AuthenticationError, auth.verify_otp, phone, sent["dev_otp"], "Patient", "Nila")

	def test_home_lists_seeded_therapies_and_testimonials(self):
		frappe.set_user("Guest")
		home = content.get_home("Kochi")
		names = [row.therapy_name for row in home["therapies"]]
		self.assertIn("Panchakarma", names)
		self.assertIn("Shirodhara", names)
		self.assertTrue(any(row.placement == "home_hero" for row in home["blocks"]))
		self.assertTrue(home["testimonials"])

	def test_unverified_practitioner_is_hidden_until_admin_verifies(self):
		doc, user = self.make_practitioner(status="Draft")
		frappe.set_user("Guest")
		self.assertFalse(any(row["name"] == doc.name for row in practitioner.search("Testport")))
		frappe.set_user(user)
		doc.reload()
		doc.status = "Verified"
		self.assertRaises(frappe.PermissionError, doc.save)
		frappe.set_user(user)
		card = practitioner.save_profile(
			practitioner_name=doc.practitioner_name,
			qualifications="BAMS",
			registration_number=doc.registration_number,
			therapies=["Panchakarma"],
			regions=["Testport"],
			fee_clinic=500,
		)
		self.assertEqual(card["status"], "Draft")
		submitted = practitioner.submit_for_review()
		self.assertEqual(submitted["status"], "Pending Review")
		frappe.set_user("Administrator")
		doc.reload()
		doc.status = "Verified"
		doc.save()
		frappe.set_user("Guest")
		found = practitioner.search("Testport", therapy="Panchakarma", visit_type="Clinic")
		match = next(row for row in found if row["name"] == doc.name)
		self.assertNotIn("registration_number", match)
		self.assertEqual(match["fees"]["clinic"], 500)

	def test_slots_skip_leave_and_existing_appointments(self):
		doctor, doctor_user = self.make_practitioner()
		patient, patient_user = self.make_patient()
		frappe.set_user("Guest")
		slots = practitioner.get_slots(doctor.name, str(self.day), "Clinic")
		self.assertGreaterEqual(len(slots), 2)
		self.assertFalse(practitioner.get_slots(doctor.name, str(self.day), "Home"))
		frappe.get_doc(
			{
				"doctype": "Practitioner Leave",
				"practitioner": doctor.name,
				"from_date": self.day,
				"to_date": self.day,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(practitioner.get_slots(doctor.name, str(self.day), "Clinic"), [])
		frappe.db.delete("Practitioner Leave", {"practitioner": doctor.name})
		frappe.set_user(patient_user)
		first = booking.create(doctor.name, "Panchakarma", "Clinic", slots[0]["start"], 1)
		self.assertEqual(first["status"], "Pending Payment")
		self.assertEqual(first["fee"], 500)
		remaining = {row["start"] for row in practitioner.get_slots(doctor.name, str(self.day), "Clinic")}
		self.assertNotIn(slots[0]["start"], remaining)
		self.assertRaises(
			frappe.ValidationError,
			booking.create,
			doctor.name,
			"Panchakarma",
			"Clinic",
			slots[0]["start"],
			1,
		)
		self.assertRaises(
			frappe.ValidationError,
			booking.create,
			doctor.name,
			"Panchakarma",
			"Clinic",
			slots[1]["start"],
			0,
		)
		self.assertTrue(doctor_user)

	def test_dev_payment_confirms_and_notifies(self):
		doctor, doctor_user = self.make_practitioner()
		_patient, patient_user = self.make_patient()
		frappe.set_user(patient_user)
		start = self.slot_start()
		appt = booking.create(doctor.name, "Panchakarma", "Video", start, True)
		order = payment.create_order(appt["name"])
		self.assertTrue(order["dev_mode"])
		self.assertTrue(order["order_id"].startswith("order_dev_"))
		payment.mark_paid_dev(appt["name"])
		self.assertEqual(frappe.db.get_value("Appointment", appt["name"], "status"), "Confirmed")
		self.assertTrue(
			frappe.db.exists("Notification Log", {"for_user": patient_user, "document_name": appt["name"]})
		)
		self.assertTrue(
			frappe.db.exists("Notification Log", {"for_user": doctor_user, "document_name": appt["name"]})
		)

	def test_webhook_signature(self):
		doctor, _doctor_user = self.make_practitioner()
		_patient, patient_user = self.make_patient()
		frappe.set_user(patient_user)
		appt = booking.create(doctor.name, "Panchakarma", "Clinic", self.slot_start(9, 30), 1)
		order = payment.create_order(appt["name"])
		body = json.dumps(
			{
				"event": "payment.captured",
				"payload": {"payment": {"entity": {"id": "pay_test_1", "order_id": order["order_id"]}}},
			}
		).encode()
		frappe.conf.razorpay_webhook_secret = "whsec_test"
		from vaidya.utils import sign_body

		class Request:
			def __init__(self, data, headers):
				self._data = data
				self.headers = headers

			def get_data(self):
				return self._data

		frappe.local.request = Request(body, {"X-Razorpay-Signature": "bad"})
		self.assertRaises(frappe.AuthenticationError, payment.webhook)
		frappe.local.request = Request(body, {"X-Razorpay-Signature": sign_body("whsec_test", body)})
		payment.webhook()
		self.assertEqual(frappe.db.get_value("Appointment", appt["name"], "status"), "Confirmed")

	def test_expired_hold_releases_the_slot(self):
		doctor, _user = self.make_practitioner()
		_patient, patient_user = self.make_patient()
		frappe.set_user(patient_user)
		start = self.slot_start(10, 0)
		appt = booking.create(doctor.name, "Panchakarma", "Clinic", start, 1)
		frappe.db.set_value(
			"Appointment",
			appt["name"],
			"creation",
			frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-30),
		)
		payment.expire_pending_payments()
		self.assertEqual(frappe.db.get_value("Appointment", appt["name"], "status"), "Cancelled")
		starts = {row["start"] for row in practitioner.get_slots(doctor.name, str(self.day), "Clinic")}
		self.assertIn(start, starts)

	def test_patient_cannot_read_another_patients_clinical_record(self):
		doctor, doctor_user = self.make_practitioner()
		patient_a, user_a = self.make_patient("Asha")
		_patient_b, user_b = self.make_patient("Bina")
		frappe.set_user(user_a)
		appt = booking.create(doctor.name, "Panchakarma", "Clinic", self.slot_start(), 1)
		payment.create_order(appt["name"])
		payment.mark_paid_dev(appt["name"])
		frappe.set_user(doctor_user)
		booking.complete(appt["name"])
		clinical.save_note(
			appt["name"],
			chief_complaint="Acidity",
			observations="Agni is low",
			advice="Warm water",
			share_with_patient=0,
			submit=0,
		)
		frappe.set_user(user_a)
		self.assertIsNone(clinical.get_for_appointment(appt["name"])["note"])
		draft_note = frappe.get_doc(
			"Consultation Note", frappe.db.get_value("Consultation Note", {"appointment": appt["name"]}, "name")
		)
		self.assertRaises(frappe.PermissionError, draft_note.check_permission, "read")
		frappe.set_user(doctor_user)
		clinical.save_note(
			appt["name"],
			chief_complaint="Acidity",
			observations="Agni is low",
			advice="Warm water",
			share_with_patient=1,
			submit=1,
		)
		prescription = clinical.submit_prescription(
			appt["name"],
			items=[
				{
					"medicine_name": "Avipattikar",
					"dose": "1 tsp",
					"frequency": "twice daily",
					"duration": "14 days",
					"anupana": "warm water",
				}
			],
			advice="Light dinner",
		)
		self.assertEqual(prescription["registration_number"], doctor.registration_number)
		self.assertEqual(prescription["patient_name"], patient_a.patient_name)
		self.assertTrue(
			frappe.db.exists("Notification Log", {"for_user": user_a, "document_type": "Prescription"})
		)
		frappe.set_user(user_a)
		visible = clinical.get_for_appointment(appt["name"])
		self.assertEqual(visible["note"]["chief_complaint"], "Acidity")
		self.assertEqual(visible["prescription"]["items"][0]["medicine_name"], "Avipattikar")
		frappe.set_user(user_b)
		self.assertRaises(frappe.PermissionError, clinical.get_for_appointment, appt["name"])
		rx = frappe.get_doc("Prescription", prescription["name"])
		self.assertRaises(frappe.PermissionError, rx.check_permission, "read")

	def test_cancel_notifies_the_other_party(self):
		doctor, doctor_user = self.make_practitioner()
		_patient, patient_user = self.make_patient()
		frappe.set_user(patient_user)
		appt = booking.create(doctor.name, "Panchakarma", "Clinic", self.slot_start(10, 30), 1)
		booking.cancel(appt["name"])
		self.assertEqual(frappe.db.get_value("Appointment", appt["name"], "status"), "Cancelled")
		self.assertTrue(
			frappe.db.exists("Notification Log", {"for_user": doctor_user, "document_name": appt["name"]})
		)

	def test_video_meeting_link(self):
		doctor, doctor_user = self.make_practitioner()
		_patient, patient_user = self.make_patient()
		frappe.set_user(patient_user)
		appt = booking.create(doctor.name, "Panchakarma", "Video", self.slot_start(), 1)
		payment.create_order(appt["name"])
		payment.mark_paid_dev(appt["name"])
		frappe.set_user(doctor_user)
		updated = booking.set_meeting_url(appt["name"], "https://meet.example.com/vaidya")
		self.assertEqual(updated["meeting_url"], "https://meet.example.com/vaidya")
		self.assertTrue(frappe.db.exists("Notification Log", {"for_user": patient_user, "subject": ["like", "Video link%"]}))
