# Vaidya

Ayurveda marketplace backend for Frappe 15. Patients discover verified doctors and therapists by region, book clinic, video, or home visits, and read submitted prescriptions. Practitioners onboard in the app. Admins verify profiles and publish testimonials from Frappe Desk.

The Flutter client lives in `vaidya_flutter` next to the bench.

## Local site

```bash
cd vaidya-bench
bench start
```

Site: `http://127.0.0.1:8001`

Desk login: `Administrator` / `admin`

Developer mode returns the SMS OTP in `dev_otp` so the app can sign in without an SMS gateway. Set `vaidya_sms_url` to POST `{phone, message}` when a gateway is available.

Razorpay keys (`razorpay_key_id`, `razorpay_key_secret`, `razorpay_webhook_secret`) live in `site_config.json`. Without them, developer mode creates an `order_dev_` payment the app can confirm locally.
