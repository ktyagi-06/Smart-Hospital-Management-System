# Presentation guide

How to explain this project to your professor in about 5 minutes, plus answers to likely questions.

## 1. The 30-second pitch

> Hospitals lose time and make mistakes because patient registration, appointments, beds, pharmacy and billing are handled separately. I built one web application that connects all of them, and adds a few smart rules: it ranks patients by how urgent they are, it stops double booking, and it warns staff about low stock and full wards.

## 2. Say it in three layers

1. **What the user sees** - web pages (HTML and CSS in `templates/`).
2. **What decides things** - Python and Flask in `app.py`. It receives a request, applies the rules, reads or writes the database, and returns a page.
3. **Where data lives** - an SQLite database (one file, `hms.db`) with 7 tables.

If you remember one sentence: *the browser asks, Flask decides, the database remembers.*

## 3. Live demo script (about 4 minutes)

Run `python app.py`, then open http://127.0.0.1:5000.

| Step | Do this | Say this |
|---|---|---|
| 1 | Sign in as `admin` / `admin123` | "Every user has a role. Staff only see what their job needs." |
| 2 | Look at the dashboard | "This is the live picture: beds, today's appointments, unpaid bills, and alerts." |
| 3 | **Patients** - register a new patient | "Registration is the starting point. Everything else links to a patient." |
| 4 | **Smart triage** - choose a patient, enter SpO2 `85`, heart rate `135`, symptoms `chest pain, breathless`, press Calculate | "It scored this as Critical, routed to Emergency, and listed exactly why. Staff can check the reasoning." |
| 5 | Add a second, mild patient (`headache`, normal vitals) and open the queue | "The sickest patient is always at the top, not first-come-first-served." |
| 6 | **Appointments** - book a slot, then try to book the same slot again | "The second booking is rejected. The database itself enforces it." |
| 7 | **Beds** - admit a patient to ICU, then discharge | "A free bed is picked automatically. Discharge creates the bill for the stay." |
| 8 | **Pharmacy** - dispense a medicine | "Stock goes down and the patient is billed. Expired medicine is blocked." |
| 9 | **Billing** - mark a bill paid | "Consultation, medicine and bed charges were all added automatically." |
| 10 | Sign out, sign in as `pharmacist`, try to open Billing | "Role-based access: the pharmacist is sent back with a message." |

## 4. Likely questions and good answers

**Why Flask and SQLite?**
Flask is small and readable, so the logic is easy to follow. SQLite needs no setup because the database is a single file. For a real hospital you would move to a server database such as PostgreSQL; the SQL would barely change.

**What is "smart" about it? Is it AI?**
It is rule-based decision support, not machine learning. The rules are written by hand, so every decision can be explained. That is a strength in healthcare, where staff need to know why. Machine learning is listed as future work because it needs real patient data.

**How does the triage score work?**
Each abnormal vital sign or serious symptom adds points. The total maps to Critical, Urgent, Semi-urgent or Routine. The rules are modelled on early-warning scoring used in hospitals. It is a teaching model, not a certified medical tool.

**How do you prevent double booking?**
The appointments table has a UNIQUE rule on (doctor, time). Even if two receptionists click at the same instant, the database refuses the second one and the user sees a friendly message.

**How are passwords protected?**
They are never stored as text. Each one is hashed with Werkzeug's password hashing, so even someone who reads the database cannot see the original passwords.

**What would you add for real-world use?**
CSRF protection, login attempt limits, audit logs of who viewed or changed what, HTTPS, backups, and compliance with health data law (for example HIPAA or India's DPDP Act).

**How did you test it?**
`python -m unittest -v` runs 10 automated tests: every page loads, triage scoring is correct, queue order is by risk, double booking is blocked, billing is created, stock rules work, and role permissions are enforced.

**What was the hardest part?**
Pick a real one that you actually found hard. Good candidates: making billing automatic across modules, or deciding the triage point values.

## 5. Where to look in the code if asked

| Question about... | Open |
|---|---|
| Triage rules | `app.py` - `triage_score()` and `SYMPTOM_RULES` |
| Free appointment slots | `app.py` - `free_slots()` |
| Database tables | `app.py` - `SCHEMA` |
| Login and roles | `app.py` - `login()`, `guard()`, `ROLE_PAGES` |
| A page's layout | `templates/<module>.html` |
| Tests | `test_app.py` |

## 6. Before you present

- Run it once on the laptop you will use, and run the tests.
- Delete `hms.db` right before the demo so the sample data starts fresh.
- Be ready to say plainly that the triage rules are a simple teaching model, not a medical device. Professors respond well to honest limits.
