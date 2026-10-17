import os, tempfile, unittest
from datetime import date, timedelta

os.environ["HMS_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
import app as hms  # noqa: E402


class HMSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        hms.init_db()
        cls.c = hms.app.test_client()
        cls.c.post("/login", data=dict(username="admin", password="admin123"))

    def login_as(self, user, pw):
        c = hms.app.test_client()
        c.post("/login", data=dict(username=user, password=pw))
        return c

    def test_login_required_and_wrong_password(self):
        anon = hms.app.test_client()
        r = anon.get("/patients")
        self.assertEqual(r.status_code, 302); self.assertIn("/login", r.headers["Location"])
        self.assertEqual(anon.get("/api/slots?doctor_id=1").status_code, 401)
        bad = anon.post("/login", data=dict(username="admin", password="nope"))
        self.assertEqual(bad.status_code, 401)
        self.assertIn("incorrect", bad.get_data(as_text=True))
        self.assertEqual(anon.get("/login").status_code, 200)

    def test_open_redirect_blocked(self):
        c = hms.app.test_client()
        r = c.post("/login?next=//evil.com", data=dict(username="admin", password="admin123"))
        self.assertNotIn("evil.com", r.headers["Location"])

    def test_role_access(self):
        ph = self.login_as("pharmacist", "pharma123")
        self.assertEqual(ph.get("/pharmacy").status_code, 200)
        r = ph.get("/triage"); self.assertEqual(r.status_code, 302)
        self.assertIn("does not have access", ph.get("/").get_data(as_text=True))
        rc = self.login_as("reception", "reception123")
        self.assertEqual(rc.get("/billing").status_code, 200)
        self.assertEqual(rc.get("/pharmacy").status_code, 302)
        dr = self.login_as("doctor", "doctor123")
        self.assertEqual(dr.get("/billing").status_code, 302)

    def test_logout(self):
        c = self.login_as("doctor", "doctor123")
        self.assertEqual(c.get("/patients").status_code, 200)
        c.post("/logout")
        self.assertEqual(c.get("/patients").status_code, 302)

    def test_pages_load(self):
        for url in ["/", "/patients", "/patients/1", "/doctors", "/appointments",
                    "/triage", "/beds", "/pharmacy", "/billing"]:
            self.assertEqual(self.c.get(url).status_code, 200, url)

    def test_triage_scoring(self):
        s, lvl, dept, _ = hms.triage_score("chest pain, breathless", 135, 85, 88, 37, 28, 60)
        self.assertEqual(lvl, "Critical"); self.assertEqual(dept, "Emergency")
        s, lvl, dept, _ = hms.triage_score("mild headache", 80, 120, 98, 36.8, 16, 30)
        self.assertEqual(lvl, "Routine"); self.assertEqual(dept, "General Medicine")
        s, lvl, dept, _ = hms.triage_score("fever and cough", 90, 120, 97, 38.4, 18, 30)
        self.assertIn(lvl, ("Semi-urgent", "Urgent"))

    def test_triage_endpoint_and_queue_order(self):
        self.c.post("/triage", data=dict(patient_id=1, symptoms="headache", spo2=98))
        self.c.post("/triage", data=dict(patient_id=2, symptoms="chest pain", spo2=85, heart_rate=140))
        html = self.c.get("/triage").get_data(as_text=True)
        html = html[html.index("Waiting queue"):]  # skip the patient dropdown above the table
        self.assertLess(html.index("Sunita Devi"), html.index("Amit Kumar"))  # riskier first

    def test_double_booking_blocked(self):
        day = (date.today() + timedelta(days=2)).isoformat()
        with hms.app.test_request_context():
            hms.g.db = hms.sqlite3.connect(hms.DB_PATH); hms.g.db.row_factory = hms.sqlite3.Row
            slot = hms.free_slots(1, day)[0]
        self.c.post("/appointments", data=dict(patient_id=1, doctor_id=1, slot=slot, reason="x"))
        r = self.c.post("/appointments", data=dict(patient_id=2, doctor_id=1, slot=slot), follow_redirects=True)
        self.assertIn("just taken", r.get_data(as_text=True))
        self.assertEqual(self.c.get(f"/api/slots?doctor_id=1&date={day}").get_json().count(slot), 0)

    def test_admit_discharge_bills(self):
        self.c.post("/beds", data=dict(action="admit", patient_id=3, ward="ICU"))
        self.assertIn("ICU-1", self.c.get("/beds").get_data(as_text=True))
        r = self.c.post("/beds", data=dict(action="admit", patient_id=3, ward="ICU"), follow_redirects=True)
        self.assertIn("already admitted", r.get_data(as_text=True))
        self.c.post("/beds", data=dict(action="discharge", bed_id=1))
        self.assertIn("8000", self.c.get("/billing").get_data(as_text=True))

    def test_pharmacy_rules(self):
        r = self.c.post("/pharmacy", data=dict(action="dispense", patient_id=1, medicine_id=2, qty=999),
                        follow_redirects=True)
        self.assertIn("insufficient", r.get_data(as_text=True))
        self.c.post("/pharmacy", data=dict(action="dispense", patient_id=1, medicine_id=1, qty=10))
        self.assertIn("Paracetamol 500mg x 10", self.c.get("/billing").get_data(as_text=True))
        self.assertIn("Low stock", self.c.get("/pharmacy").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
