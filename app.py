"""Smart Hospital Management System - Flask + SQLite."""
import os
import sqlite3
from datetime import datetime, timedelta, date
from flask import Flask, g, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("HMS_DB", os.path.join(BASE, "hms.db"))


def load_secret_key():
    """Use HMS_SECRET if set, else create a random key once and keep it in .secret_key."""
    if os.environ.get("HMS_SECRET"):
        return os.environ["HMS_SECRET"]
    path = os.path.join(BASE, ".secret_key")
    if not os.path.exists(path):
        with open(path, "wb") as fh:
            fh.write(os.urandom(32).hex().encode())
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    with open(path, "rb") as fh:
        return fh.read().decode()


app = Flask(__name__)
app.secret_key = load_secret_key()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
SHOW_DEMO_HINT = os.environ.get("HMS_DEMO", "1") == "1"

# Which pages each role may open. None means everything.
_CLINICAL = {"dashboard", "patients", "patient_detail", "doctors", "appointments", "api_slots",
             "appointment_action", "triage", "triage_seen", "beds"}
ROLE_PAGES = {
    "admin": None,
    "doctor": _CLINICAL,
    "reception": _CLINICAL | {"billing"},
    "pharmacist": {"dashboard", "patients", "patient_detail", "pharmacy"},
}
DEMO_USERS = [
    ("admin", "Admin", "admin", "admin123"),
    ("reception", "Riya (Reception)", "reception", "reception123"),
    ("doctor", "Dr. Anita Sharma", "doctor", "doctor123"),
    ("pharmacist", "Karan (Pharmacy)", "pharmacist", "pharma123"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, full_name TEXT,
  role TEXT NOT NULL, password_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS patients(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, age INTEGER, gender TEXT,
  phone TEXT, address TEXT, blood_group TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS doctors(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, specialization TEXT,
  start_hour INTEGER DEFAULT 9, end_hour INTEGER DEFAULT 17, fee REAL DEFAULT 500);
CREATE TABLE IF NOT EXISTS appointments(
  id INTEGER PRIMARY KEY, patient_id INTEGER, doctor_id INTEGER,
  slot TEXT, reason TEXT, status TEXT DEFAULT 'Scheduled',
  UNIQUE(doctor_id, slot));
CREATE TABLE IF NOT EXISTS triage(
  id INTEGER PRIMARY KEY, patient_id INTEGER, symptoms TEXT, heart_rate INTEGER,
  systolic INTEGER, spo2 INTEGER, temp REAL, resp_rate INTEGER,
  score INTEGER, level TEXT, suggested_dept TEXT, created_at TEXT, status TEXT DEFAULT 'Waiting');
CREATE TABLE IF NOT EXISTS beds(
  id INTEGER PRIMARY KEY, ward TEXT, number TEXT, patient_id INTEGER, admitted_at TEXT);
CREATE TABLE IF NOT EXISTS medicines(
  id INTEGER PRIMARY KEY, name TEXT, stock INTEGER, reorder_level INTEGER,
  price REAL, expiry TEXT);
CREATE TABLE IF NOT EXISTS bills(
  id INTEGER PRIMARY KEY, patient_id INTEGER, description TEXT, amount REAL,
  paid INTEGER DEFAULT 0, created_at TEXT);
"""


# ---------------------------------------------------------------- database
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def can(endpoint):
    role = session.get("role")
    if not role:
        return False
    pages = ROLE_PAGES.get(role)
    return pages is None or endpoint in pages


@app.context_processor
def inject_globals():
    return {"today_label": datetime.now().strftime("%A, %d %B %Y"), "can": can,
            "user": {"name": session.get("name"), "role": session.get("role")}}


@app.before_request
def guard():
    ep = request.endpoint
    if ep in (None, "static", "login"):
        return None
    if "uid" not in session:
        if request.path.startswith("/api/"):
            return jsonify(error="Sign in required"), 401
        return redirect(url_for("login", next=request.path))
    if ep != "logout" and not can(ep):
        flash("Your role does not have access to that page.", "error")
        return redirect(url_for("dashboard"))
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if "uid" in session:
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        u = db().execute("SELECT * FROM users WHERE username=?",
                         (request.form.get("username", "").strip().lower(),)).fetchone()
        if u and check_password_hash(u["password_hash"], request.form.get("password", "")):
            session.clear()
            session.update(uid=u["id"], name=u["full_name"] or u["username"], role=u["role"])
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("dashboard"))
        error = "Username or password is incorrect."
    return render_template("login.html", error=error, demo=SHOW_DEMO_HINT, demo_users=DEMO_USERS), \
        (401 if error else 200)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def init_db(seed=True):
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    if seed and conn.execute("SELECT COUNT(*) FROM doctors").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO doctors(name,specialization,start_hour,end_hour,fee) VALUES(?,?,?,?,?)",
            [("Dr. Anita Sharma", "Cardiology", 9, 17, 800),
             ("Dr. Rahul Verma", "General Medicine", 9, 18, 400),
             ("Dr. Meera Nair", "Pulmonology", 10, 16, 700),
             ("Dr. Sanjay Gupta", "Emergency", 8, 20, 600),
             ("Dr. Priya Singh", "Pediatrics", 9, 15, 500)])
        beds = [("ICU", f"ICU-{i}") for i in range(1, 5)] + \
               [("General", f"G-{i}") for i in range(1, 9)] + \
               [("Private", f"P-{i}") for i in range(1, 5)]
        conn.executemany("INSERT INTO beds(ward,number) VALUES(?,?)", beds)
        today = date.today()
        conn.executemany(
            "INSERT INTO medicines(name,stock,reorder_level,price,expiry) VALUES(?,?,?,?,?)",
            [("Paracetamol 500mg", 500, 100, 2.0, str(today + timedelta(days=400))),
             ("Amoxicillin 250mg", 40, 80, 8.5, str(today + timedelta(days=200))),
             ("Metformin 500mg", 300, 100, 3.0, str(today + timedelta(days=25))),
             ("Insulin Glargine", 25, 30, 650.0, str(today + timedelta(days=150))),
             ("Salbutamol Inhaler", 60, 20, 120.0, str(today + timedelta(days=300)))])
        conn.executemany(
            "INSERT INTO patients(name,age,gender,phone,address,blood_group,created_at) VALUES(?,?,?,?,?,?,?)",
            [("Amit Kumar", 54, "Male", "9810000001", "Delhi", "B+", now()),
             ("Sunita Devi", 38, "Female", "9810000002", "Noida", "O+", now()),
             ("Rohan Mehta", 8, "Male", "9810000003", "Gurgaon", "A+", now())])
    if seed and conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO users(username,full_name,role,password_hash) VALUES(?,?,?,?)",
            [(u, n, r, generate_password_hash(pw)) for u, n, r, pw in DEMO_USERS])
    conn.commit()
    conn.close()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ------------------------------------------------------------ smart logic
SYMPTOM_RULES = {
    # keyword: (points, department)
    "chest pain": (30, "Cardiology"), "breathless": (25, "Pulmonology"),
    "shortness of breath": (25, "Pulmonology"), "unconscious": (40, "Emergency"),
    "bleeding": (25, "Emergency"), "stroke": (40, "Emergency"),
    "seizure": (30, "Emergency"), "accident": (30, "Emergency"),
    "palpitation": (15, "Cardiology"), "cough": (6, "Pulmonology"),
    "asthma": (15, "Pulmonology"), "fever": (8, "General Medicine"),
    "vomiting": (8, "General Medicine"), "headache": (5, "General Medicine"),
    "rash": (4, "General Medicine"), "child": (3, "Pediatrics"),
}


def triage_score(symptoms, hr, sys_bp, spo2, temp, rr, age=None):
    """Rule-based early-warning score (NEWS-inspired). Returns (score, level, dept, reasons)."""
    s, reasons = 0, []

    def add(p, why):
        nonlocal s
        if p:
            s += p
            reasons.append(f"{why} (+{p})")

    if spo2 is not None:
        add(30 if spo2 < 90 else 15 if spo2 < 94 else 0, f"SpO2 {spo2}%")
    if hr is not None:
        add(15 if hr > 130 or hr < 40 else 8 if hr > 110 or hr < 50 else 0, f"Heart rate {hr}")
    if sys_bp is not None:
        add(25 if sys_bp < 90 else 10 if sys_bp > 180 else 0, f"Systolic BP {sys_bp}")
    if temp is not None:
        add(10 if temp >= 39.5 or temp < 35 else 5 if temp >= 38 else 0, f"Temp {temp}C")
    if rr is not None:
        add(15 if rr > 30 or rr < 8 else 8 if rr > 24 else 0, f"Resp rate {rr}")
    if age is not None and (age >= 65 or age <= 5):
        add(5, f"Age {age} (high-risk group)")

    text = (symptoms or "").lower()
    dept_votes = {}
    for kw, (pts, dept) in SYMPTOM_RULES.items():
        if kw in text:
            add(pts, f"Symptom '{kw}'")
            dept_votes[dept] = dept_votes.get(dept, 0) + pts
    dept = max(dept_votes, key=dept_votes.get) if dept_votes else "General Medicine"
    if s >= 40:
        level, dept = "Critical", "Emergency"
    elif s >= 20:
        level = "Urgent"
    elif s >= 8:
        level = "Semi-urgent"
    else:
        level = "Routine"
    return s, level, dept, reasons


def free_slots(doctor_id, day):
    """Return list of free 30-minute slots for a doctor on a day (YYYY-MM-DD)."""
    d = db().execute("SELECT * FROM doctors WHERE id=?", (doctor_id,)).fetchone()
    if not d:
        return []
    booked = {r["slot"] for r in db().execute(
        "SELECT slot FROM appointments WHERE doctor_id=? AND slot LIKE ? AND status!='Cancelled'",
        (doctor_id, day + "%"))}
    out, t = [], datetime.strptime(f"{day} {d['start_hour']:02d}:00", "%Y-%m-%d %H:%M")
    end = datetime.strptime(f"{day} {d['end_hour']:02d}:00", "%Y-%m-%d %H:%M")
    while t < end:
        label = t.strftime("%Y-%m-%d %H:%M")
        if label not in booked and t > datetime.now():
            out.append(label)
        t += timedelta(minutes=30)
    return out


def recommend_doctor(dept):
    row = db().execute(
        "SELECT * FROM doctors WHERE specialization=? LIMIT 1", (dept,)).fetchone()
    return row or db().execute("SELECT * FROM doctors WHERE specialization='General Medicine'").fetchone()


# ------------------------------------------------------------------ routes
@app.route("/")
def dashboard():
    q = lambda sql, *a: db().execute(sql, a).fetchone()[0]
    stats = {
        "patients": q("SELECT COUNT(*) FROM patients"),
        "doctors": q("SELECT COUNT(*) FROM doctors"),
        "today_appts": q("SELECT COUNT(*) FROM appointments WHERE slot LIKE ? AND status!='Cancelled'",
                         date.today().isoformat() + "%"),
        "beds_total": q("SELECT COUNT(*) FROM beds"),
        "beds_used": q("SELECT COUNT(*) FROM beds WHERE patient_id IS NOT NULL"),
        "unpaid": q("SELECT COALESCE(SUM(amount),0) FROM bills WHERE paid=0"),
        "revenue": q("SELECT COALESCE(SUM(amount),0) FROM bills WHERE paid=1"),
    }
    stats["occupancy"] = round(100 * stats["beds_used"] / stats["beds_total"]) if stats["beds_total"] else 0
    low = db().execute("SELECT * FROM medicines WHERE stock<=reorder_level").fetchall()
    soon = (date.today() + timedelta(days=30)).isoformat()
    expiring = db().execute("SELECT * FROM medicines WHERE expiry<=?", (soon,)).fetchall()
    queue = db().execute(
        """SELECT t.*, p.name FROM triage t JOIN patients p ON p.id=t.patient_id
           WHERE t.status='Waiting' ORDER BY t.score DESC LIMIT 5""").fetchall()
    wards = db().execute(
        """SELECT ward, COUNT(*) total, SUM(patient_id IS NOT NULL) used FROM beds GROUP BY ward
           ORDER BY CASE ward WHEN 'ICU' THEN 0 WHEN 'General' THEN 1 ELSE 2 END""").fetchall()
    bed_board = db().execute(
        """SELECT b.*, p.name pname FROM beds b LEFT JOIN patients p ON p.id=b.patient_id
           ORDER BY CASE b.ward WHEN 'ICU' THEN 0 WHEN 'General' THEN 1 ELSE 2 END, b.id""").fetchall()
    week = []
    for i in range(7):
        d = date.today() + timedelta(days=i)
        n = q("SELECT COUNT(*) FROM appointments WHERE slot LIKE ? AND status!='Cancelled'", d.isoformat() + "%")
        week.append({"label": "Today" if i == 0 else d.strftime("%a"), "n": n})
    week_max = max([w["n"] for w in week] + [1])
    return render_template("dashboard.html", s=stats, low=low, expiring=expiring, queue=queue,
                           wards=wards, bed_board=bed_board, week=week, week_max=week_max)


# ---- patients
@app.route("/patients", methods=["GET", "POST"])
def patients():
    if request.method == "POST":
        f = request.form
        if not f.get("name", "").strip():
            flash("Name is required", "error")
        else:
            db().execute(
                "INSERT INTO patients(name,age,gender,phone,address,blood_group,created_at) VALUES(?,?,?,?,?,?,?)",
                (f["name"].strip(), f.get("age") or None, f.get("gender"), f.get("phone"),
                 f.get("address"), f.get("blood_group"), now()))
            db().commit()
            flash("Patient registered", "ok")
        return redirect(url_for("patients"))
    term = request.args.get("q", "")
    rows = db().execute("SELECT * FROM patients WHERE name LIKE ? OR phone LIKE ? ORDER BY id DESC",
                        (f"%{term}%", f"%{term}%")).fetchall()
    return render_template("patients.html", rows=rows, term=term)


@app.route("/patients/<int:pid>")
def patient_detail(pid):
    p = db().execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    if not p:
        return "Not found", 404
    appts = db().execute("""SELECT a.*, d.name dname FROM appointments a JOIN doctors d ON d.id=a.doctor_id
                            WHERE patient_id=? ORDER BY slot DESC""", (pid,)).fetchall()
    tri = db().execute("SELECT * FROM triage WHERE patient_id=? ORDER BY id DESC", (pid,)).fetchall()
    bills = db().execute("SELECT * FROM bills WHERE patient_id=? ORDER BY id DESC", (pid,)).fetchall()
    bed = db().execute("SELECT * FROM beds WHERE patient_id=?", (pid,)).fetchone()
    return render_template("patient_detail.html", p=p, appts=appts, tri=tri, bills=bills, bed=bed)


# ---- appointments
@app.route("/appointments", methods=["GET", "POST"])
def appointments():
    if request.method == "POST":
        f = request.form
        try:
            db().execute("INSERT INTO appointments(patient_id,doctor_id,slot,reason) VALUES(?,?,?,?)",
                         (f["patient_id"], f["doctor_id"], f["slot"], f.get("reason")))
            doc = db().execute("SELECT * FROM doctors WHERE id=?", (f["doctor_id"],)).fetchone()
            db().execute("INSERT INTO bills(patient_id,description,amount,created_at) VALUES(?,?,?,?)",
                         (f["patient_id"], f"Consultation - {doc['name']}", doc["fee"], now()))
            db().commit()
            flash("Appointment booked and consultation billed", "ok")
        except sqlite3.IntegrityError:
            flash("That slot was just taken - pick another", "error")
        return redirect(url_for("appointments"))
    rows = db().execute("""SELECT a.*, p.name pname, d.name dname, d.specialization FROM appointments a
        JOIN patients p ON p.id=a.patient_id JOIN doctors d ON d.id=a.doctor_id
        ORDER BY slot DESC LIMIT 100""").fetchall()
    return render_template("appointments.html", rows=rows,
                           patients=db().execute("SELECT id,name FROM patients ORDER BY name").fetchall(),
                           doctors=db().execute("SELECT * FROM doctors").fetchall(),
                           today=date.today().isoformat())


@app.route("/api/slots")
def api_slots():
    day = request.args.get("date", date.today().isoformat())
    return jsonify(free_slots(int(request.args.get("doctor_id", 0)), day))


@app.route("/appointments/<int:aid>/<action>", methods=["POST"])
def appointment_action(aid, action):
    status = {"cancel": "Cancelled", "complete": "Completed"}.get(action)
    if status:
        db().execute("UPDATE appointments SET status=? WHERE id=?", (status, aid))
        db().commit()
    return redirect(url_for("appointments"))


# ---- triage
@app.route("/triage", methods=["GET", "POST"])
def triage():
    result = None
    if request.method == "POST":
        f = request.form
        num = lambda k, cast=int: cast(f[k]) if f.get(k) else None
        p = db().execute("SELECT * FROM patients WHERE id=?", (f["patient_id"],)).fetchone()
        score, level, dept, reasons = triage_score(
            f.get("symptoms"), num("heart_rate"), num("systolic"), num("spo2"),
            num("temp", float), num("resp_rate"), p["age"] if p else None)
        db().execute("""INSERT INTO triage(patient_id,symptoms,heart_rate,systolic,spo2,temp,resp_rate,
                        score,level,suggested_dept,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                     (f["patient_id"], f.get("symptoms"), num("heart_rate"), num("systolic"), num("spo2"),
                      num("temp", float), num("resp_rate"), score, level, dept, now()))
        db().commit()
        doc = recommend_doctor(dept)
        result = dict(score=score, level=level, dept=dept, reasons=reasons, doctor=doc, patient=p)
    queue = db().execute("""SELECT t.*, p.name FROM triage t JOIN patients p ON p.id=t.patient_id
                            WHERE t.status='Waiting' ORDER BY t.score DESC, t.id""").fetchall()
    return render_template("triage.html", result=result, queue=queue,
                           patients=db().execute("SELECT id,name FROM patients ORDER BY name").fetchall())


@app.route("/triage/<int:tid>/seen", methods=["POST"])
def triage_seen(tid):
    db().execute("UPDATE triage SET status='Seen' WHERE id=?", (tid,))
    db().commit()
    return redirect(url_for("triage"))


# ---- beds
@app.route("/beds", methods=["GET", "POST"])
def beds():
    if request.method == "POST":
        f = request.form
        if f["action"] == "admit":
            bed_id = f.get("bed_id")
            if not bed_id:  # smart allocation: first free bed in the requested ward
                row = db().execute("SELECT id FROM beds WHERE ward=? AND patient_id IS NULL LIMIT 1",
                                   (f["ward"],)).fetchone()
                bed_id = row["id"] if row else None
            already = db().execute("SELECT 1 FROM beds WHERE patient_id=?", (f["patient_id"],)).fetchone()
            if already:
                flash("Patient is already admitted", "error")
            elif not bed_id:
                flash(f"No free bed in {f['ward']} ward", "error")
            else:
                db().execute("UPDATE beds SET patient_id=?, admitted_at=? WHERE id=? AND patient_id IS NULL",
                             (f["patient_id"], now(), bed_id))
                db().commit()
                flash("Patient admitted", "ok")
        else:  # discharge -> bill for stay
            b = db().execute("SELECT * FROM beds WHERE id=?", (f["bed_id"],)).fetchone()
            if b and b["patient_id"]:
                rate = {"ICU": 8000, "Private": 4000, "General": 1500}.get(b["ward"], 1500)
                days = max(1, (datetime.now() - datetime.strptime(b["admitted_at"], "%Y-%m-%d %H:%M")).days + 1)
                db().execute("INSERT INTO bills(patient_id,description,amount,created_at) VALUES(?,?,?,?)",
                             (b["patient_id"], f"{b['ward']} bed {b['number']} x {days} day(s)", rate * days, now()))
                db().execute("UPDATE beds SET patient_id=NULL, admitted_at=NULL WHERE id=?", (b["id"],))
                db().commit()
                flash(f"Discharged. Stay billed: {rate * days:.0f}", "ok")
        return redirect(url_for("beds"))
    rows = db().execute("""SELECT b.*, p.name pname FROM beds b LEFT JOIN patients p ON p.id=b.patient_id
                           ORDER BY ward, id""").fetchall()
    return render_template("beds.html", rows=rows,
                           patients=db().execute("SELECT id,name FROM patients ORDER BY name").fetchall())


# ---- pharmacy
@app.route("/pharmacy", methods=["GET", "POST"])
def pharmacy():
    if request.method == "POST":
        f = request.form
        if f["action"] == "add":
            db().execute("INSERT INTO medicines(name,stock,reorder_level,price,expiry) VALUES(?,?,?,?,?)",
                         (f["name"], f["stock"], f["reorder_level"], f["price"], f["expiry"]))
            flash("Medicine added", "ok")
        elif f["action"] == "dispense":
            m = db().execute("SELECT * FROM medicines WHERE id=?", (f["medicine_id"],)).fetchone()
            qty = int(f["qty"])
            if qty <= 0 or qty > m["stock"]:
                flash("Invalid quantity or insufficient stock", "error")
            elif m["expiry"] < date.today().isoformat():
                flash("Medicine is expired - cannot dispense", "error")
            else:
                db().execute("UPDATE medicines SET stock=stock-? WHERE id=?", (qty, m["id"]))
                db().execute("INSERT INTO bills(patient_id,description,amount,created_at) VALUES(?,?,?,?)",
                             (f["patient_id"], f"{m['name']} x {qty}", qty * m["price"], now()))
                flash("Dispensed and billed", "ok")
        elif f["action"] == "restock":
            db().execute("UPDATE medicines SET stock=stock+? WHERE id=?", (f["qty"], f["medicine_id"]))
            flash("Restocked", "ok")
        db().commit()
        return redirect(url_for("pharmacy"))
    rows = db().execute("SELECT * FROM medicines ORDER BY name").fetchall()
    return render_template("pharmacy.html", rows=rows, today=date.today().isoformat(),
                           soon=(date.today() + timedelta(days=30)).isoformat(),
                           patients=db().execute("SELECT id,name FROM patients ORDER BY name").fetchall())


# ---- billing
@app.route("/billing", methods=["GET", "POST"])
def billing():
    if request.method == "POST":
        f = request.form
        if f["action"] == "pay":
            db().execute("UPDATE bills SET paid=1 WHERE id=?", (f["bill_id"],))
        else:
            db().execute("INSERT INTO bills(patient_id,description,amount,created_at) VALUES(?,?,?,?)",
                         (f["patient_id"], f["description"], f["amount"], now()))
        db().commit()
        return redirect(url_for("billing"))
    rows = db().execute("""SELECT b.*, p.name pname FROM bills b JOIN patients p ON p.id=b.patient_id
                           ORDER BY paid, id DESC""").fetchall()
    return render_template("billing.html", rows=rows,
                           patients=db().execute("SELECT id,name FROM patients ORDER BY name").fetchall())


@app.route("/doctors")
def doctors():
    rows = db().execute("""SELECT d.*, (SELECT COUNT(*) FROM appointments a WHERE a.doctor_id=d.id
                           AND a.status='Scheduled') upcoming FROM doctors d""").fetchall()
    return render_template("doctors.html", rows=rows)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
