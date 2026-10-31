import calendar
from datetime import datetime, time, timedelta

import frappe

from vaidya.utils import FEE_FIELDS, HOLD_MINUTES, VISIT_FLAGS, VISIT_TYPES, combine


def assert_visit_type(visit_type):
	if visit_type not in VISIT_TYPES:
		frappe.throw("Visit type must be Clinic, Video, or Home", frappe.ValidationError)
	return visit_type


def fee_for(profile, visit_type):
	assert_visit_type(visit_type)
	amount = profile.get(FEE_FIELDS[visit_type]) or 0
	if amount <= 0:
		frappe.throw(f"This practitioner does not offer {visit_type} visits", frappe.ValidationError)
	return amount


def hold_cutoff():
	return frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-HOLD_MINUTES)


def is_on_leave(practitioner, day):
	day = frappe.utils.getdate(day)
	return bool(
		frappe.db.exists(
			"Practitioner Leave",
			{"practitioner": practitioner, "from_date": ["<=", day], "to_date": [">=", day]},
		)
	)


def busy_ranges(practitioner, day, ignore_appointment=None):
	day = frappe.utils.getdate(day)
	cutoff = hold_cutoff()
	rows = frappe.db.sql(
		"""
		select name, starts_on, ends_on, status, creation
		from `tabAppointment`
		where practitioner = %s
			and starts_on < %s
			and ends_on > %s
			and status in ('Pending Payment', 'Confirmed', 'Completed')
		""",
		(practitioner, datetime.combine(day, time.max), datetime.combine(day, time.min)),
		as_dict=True,
	)
	ranges = []
	for row in rows:
		if ignore_appointment and row.name == ignore_appointment:
			continue
		if row.status == "Pending Payment" and row.creation and row.creation < cutoff:
			continue
		ranges.append((row.starts_on, row.ends_on))
	return ranges


def overlaps(ranges, start, end):
	for existing_start, existing_end in ranges:
		if start < existing_end and end > existing_start:
			return True
	return False


def iter_slots(practitioner, day, visit_type, ignore_appointment=None):
	assert_visit_type(visit_type)
	day = frappe.utils.getdate(day)
	if is_on_leave(practitioner, day):
		return
	weekday = calendar.day_name[day.weekday()]
	windows = frappe.get_all(
		"Practitioner Availability",
		filters={"practitioner": practitioner, "weekday": weekday, VISIT_FLAGS[visit_type]: 1},
		fields=["start_time", "end_time", "slot_minutes"],
		order_by="start_time asc",
	)
	now = frappe.utils.now_datetime()
	busy = busy_ranges(practitioner, day, ignore_appointment=ignore_appointment)
	for window in windows:
		minutes = int(window.slot_minutes or 30)
		if minutes <= 0:
			continue
		cursor = combine(day, window.start_time)
		end = combine(day, window.end_time)
		step = timedelta(minutes=minutes)
		while cursor + step <= end:
			slot_end = cursor + step
			if slot_end > now and not overlaps(busy, cursor, slot_end):
				yield cursor, slot_end
			cursor = slot_end


def matching_slot(practitioner, visit_type, start, ignore_appointment=None):
	start = frappe.utils.get_datetime(start).replace(microsecond=0)
	for slot_start, slot_end in iter_slots(
		practitioner, start.date(), visit_type, ignore_appointment=ignore_appointment
	):
		if slot_start.replace(microsecond=0) == start:
			return slot_start, slot_end
	return None
