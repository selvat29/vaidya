app_name = "vaidya"
app_title = "Vaidya"
app_publisher = "Vaidya"
app_description = "Ayurveda marketplace for patients and practitioners"
app_email = "dev@vaidya.local"
app_license = "MIT"

after_install = "vaidya.install.after_install"
before_tests = "vaidya.install.before_tests"
before_request = ["vaidya.utils.prepare_request"]

scheduler_events = {
    "hourly": [
        "vaidya.api.payment.expire_pending_payments",
    ],
}

permission_query_conditions = {
    "Patient Profile": "vaidya.permissions.patient_query",
    "Practitioner Profile": "vaidya.permissions.practitioner_query",
    "Appointment": "vaidya.permissions.appointment_query",
    "Consultation Note": "vaidya.permissions.consultation_query",
    "Prescription": "vaidya.permissions.prescription_query",
    "Practitioner Availability": "vaidya.permissions.availability_query",
    "Practitioner Leave": "vaidya.permissions.leave_query",
}

has_permission = {
    "Patient Profile": "vaidya.permissions.patient_has_permission",
    "Practitioner Profile": "vaidya.permissions.practitioner_has_permission",
    "Appointment": "vaidya.permissions.appointment_has_permission",
    "Consultation Note": "vaidya.permissions.consultation_has_permission",
    "Prescription": "vaidya.permissions.prescription_has_permission",
    "Practitioner Availability": "vaidya.permissions.availability_has_permission",
    "Practitioner Leave": "vaidya.permissions.leave_has_permission",
}
