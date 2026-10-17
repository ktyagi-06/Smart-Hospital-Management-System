# Smart Hospital Management System

A web-based hospital management system built with Flask and SQLite, with a few "smart" decision-support features.

## Run it

```bash
pip install -r requirements.txt
python app.py          # then open http://127.0.0.1:5000
python -m unittest -v test_app   # run the tests
```

The database (`hms.db`) is created and seeded with sample doctors, beds, medicines, patients and demo users on first run.

## Sign in and roles

| Username | Password | Can open |
|---|---|---|
| `admin` | `admin123` | Everything |
| `reception` | `reception123` | Patients, doctors, appointments, triage, beds, billing |
| `doctor` | `doctor123` | Patients, doctors, appointments, triage, beds |
| `pharmacist` | `pharma123` | Patients and pharmacy |

Passwords are stored hashed. The session key is generated once and saved in `.secret_key` (or set `HMS_SECRET`). Set `HMS_DEMO=0` to hide the demo accounts on the login page. **Change or delete these demo accounts before any real use.** Users are managed directly in the `users` table; there is no user-management screen yet.

## Modules

| Module | What it does |
|---|---|
| Dashboard | Live stats: patients, today's appointments, bed occupancy, outstanding bills, triage queue, stock and expiry alerts |
| Patients | Registration, search, and a full patient record (appointments, triage history, bills, bed) |
| Doctors | Specialization, working hours, fees, upcoming load |
| Appointments | Books only free 30-minute slots; double booking is blocked by a database constraint |
| Smart Triage | Scores vitals and symptoms, assigns Critical / Urgent / Semi-urgent / Routine, routes to a department, suggests a doctor, and sorts the waiting queue by risk |
| Beds | Auto-allocates the first free bed in the chosen ward; discharge bills the stay by ward rate and days |
| Pharmacy | Dispensing deducts stock and bills the patient; blocks expired medicine; low-stock and expiring-soon alerts |
| Billing | Consultation, pharmacy and bed charges are created automatically; manual charges; mark as paid |

## How the smart parts work

- **Triage score:** an early-warning style point system (SpO2, heart rate, systolic BP, temperature, respiratory rate, age risk, plus symptom keywords). Every point is listed on screen so staff can see why. Rules live in `triage_score()` and `SYMPTOM_RULES` in `app.py`.
- **Slot finder:** `free_slots()` builds the day from the doctor's hours and removes already booked slots.
- **Alerts:** low stock (stock <= reorder level), expiry within 30 days, ward occupancy >= 80%.

## Important limits

- The triage scoring is a simple teaching/demo rule set, **not a validated clinical tool**. Do not use it for real patient care without clinical review.
- Sign-in and roles are basic. There is no CSRF protection, login rate limiting, audit log, HTTPS or database encryption. A real hospital system needs all of these, plus data protection compliance, before it holds real patient data.

## Ideas to extend

A user-management screen, CSRF protection, prescriptions and lab reports, PDF invoices, SMS/email appointment reminders, a REST API, and a trained ML model for readmission or no-show prediction.
