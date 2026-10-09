"""Synthetic demo data. No real patient information is used anywhere in this project."""
import datetime as dt
import hashlib
import os
import random
import secrets

from .db import (Appointment, Bed, Message, Patient, Prescription, Request, RequestEvent, Setting, Task, User,
                 Visit, now)

# Demo accounts all share this password. Change it with DEMO_PASSWORD in .env.
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "CareSync#2026")

DEPARTMENTS = ["General Medicine", "Cardiology", "Orthopedics", "Neurology", "Pediatrics", "Emergency"]
DEPT_CODE = {"General Medicine": "GEN", "Cardiology": "CAR", "Orthopedics": "ORT",
             "Neurology": "NEU", "Pediatrics": "PED", "Emergency": "EMR"}
SLOTS = [f"{h:02d}:{m:02d}" for h in (9, 10, 11, 12, 16, 17, 18) for m in (0, 30)]
WARDS = [("ICU", "I", 6), ("General A", "A", 12), ("General B", "B", 12), ("Pediatric", "P", 8), ("Emergency", "E", 6)]

STAFF = [
    ("chairman", "Dr. R. Venkataraman", "chairman", None),
    ("dean", "Dr. Meera Nair", "dean", None),
    ("dr.arjun", "Dr. Arjun Menon", "doctor", "Cardiology"),
    ("dr.anita", "Dr. Anita Rao", "doctor", "Cardiology"),
    ("dr.kavya", "Dr. Kavya Iyer", "doctor", "Orthopedics"),
    ("dr.rahul", "Dr. Rahul Sharma", "doctor", "General Medicine"),
    ("dr.sana", "Dr. Sana Khan", "doctor", "Neurology"),
    ("dr.vikram", "Dr. Vikram Pillai", "doctor", "Pediatrics"),
    ("dr.joseph", "Dr. Joseph Mathew", "doctor", "Emergency"),
    ("nurse.priya", "Priya Thomas", "nurse", "Cardiology"),
    ("nurse.deepa", "Deepa Krishnan", "nurse", "Orthopedics"),
    ("nurse.latha", "Latha Suresh", "nurse", "General Medicine"),
    ("reception.ravi", "Ravi Kumar", "receptionist", None),
    ("reception.divya", "Divya Raj", "receptionist", None),
]

FIRST = ["Arun", "Lakshmi", "Karthik", "Fathima", "Suresh", "Anjali", "Mohan", "Revathi", "Imran", "Sneha",
         "Ganesh", "Pooja", "Naveen", "Shalini", "Rajesh", "Divya", "Vijay", "Meena", "Ashok", "Nisha",
         "Prakash", "Swathi", "Manoj", "Keerthi", "Dinesh", "Asha", "Ramesh", "Bhavana", "Sanjay", "Geetha"]
LAST = ["Kumar", "Nair", "Reddy", "Pillai", "Iyer", "Menon", "Das", "Varma", "Fernandes", "Bose", "Shetty", "Joseph"]

CLINICAL = {
    "General Medicine": [("Fever and body ache", "Viral fever", [("Paracetamol 650mg", "1-0-1", "5 days")]),
                         ("Persistent cough", "Upper respiratory infection", [("Azithromycin 500mg", "1-0-0", "3 days"), ("Cough syrup", "10ml x3", "5 days")]),
                         ("Tiredness, frequent thirst", "Type 2 diabetes mellitus", [("Metformin 500mg", "1-0-1", "30 days")])],
    "Cardiology": [("Chest discomfort on exertion", "Stable angina", [("Aspirin 75mg", "0-1-0", "30 days"), ("Atorvastatin 20mg", "0-0-1", "30 days")]),
                   ("Palpitations", "Sinus tachycardia", [("Metoprolol 25mg", "1-0-1", "14 days")]),
                   ("High blood pressure readings", "Essential hypertension", [("Amlodipine 5mg", "1-0-0", "30 days")])],
    "Orthopedics": [("Knee pain while climbing stairs", "Osteoarthritis of knee", [("Aceclofenac 100mg", "1-0-1", "7 days"), ("Calcium + D3", "0-1-0", "30 days")]),
                    ("Wrist pain after a fall", "Distal radius hairline fracture", [("Ibuprofen 400mg", "1-0-1", "5 days")]),
                    ("Lower back pain", "Lumbar strain", [("Thiocolchicoside 4mg", "1-0-1", "5 days")])],
    "Neurology": [("Recurring one-sided headache", "Migraine without aura", [("Sumatriptan 50mg", "as needed", "10 tablets")]),
                  ("Numbness in fingers", "Carpal tunnel syndrome", [("Methylcobalamin 1500mcg", "1-0-0", "30 days")])],
    "Pediatrics": [("Fever and sore throat", "Acute tonsillitis", [("Amoxicillin 250mg", "1-1-1", "5 days")]),
                   ("Loose stools", "Acute gastroenteritis", [("ORS", "after each stool", "3 days"), ("Zinc 20mg", "1-0-0", "14 days")])],
    "Emergency": [("Cut on forearm", "Laceration, sutured", [("Tetanus toxoid", "single dose", "once")]),
                  ("Breathlessness", "Acute asthma exacerbation", [("Salbutamol inhaler", "2 puffs as needed", "30 days")])],
}
BASE_WAIT = {"General Medicine": 22, "Cardiology": 36, "Orthopedics": 28, "Neurology": 31, "Pediatrics": 17, "Emergency": 7}
WEIGHT = {"General Medicine": 30, "Cardiology": 18, "Orthopedics": 17, "Neurology": 10, "Pediatrics": 15, "Emergency": 10}
HOURS = [8, 9, 9, 10, 10, 10, 11, 11, 11, 12, 12, 13, 14, 15, 16, 17, 17, 18, 18, 19]


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 60000).hex()


def make_user(username, password, name, role, department=None, patient_id=None):
    salt = secrets.token_hex(16)
    return User(username=username, password_hash=hash_password(password, salt), salt=salt, name=name,
                role=role, department=department, patient_id=patient_id)


def make_pid(patient):
    return f"CS-{patient.created_at.year}-{patient.id:05d}"


def seed(db):
    rnd = random.Random(7)
    users = {}
    for username, name, role, dept in STAFF:
        users[username] = make_user(username, DEMO_PASSWORD, name, role, dept)
        db.add(users[username])
    db.flush()
    doctors = {}
    for u in users.values():
        if u.role == "doctor":
            doctors.setdefault(u.department, []).append(u)

    patients = []
    for i in range(48):
        p = Patient(name=f"{FIRST[i % len(FIRST)]} {LAST[(i * 5 + i // 7) % len(LAST)]}",
                    age=rnd.choice([6, 9, 12]) if i % 9 == 4 else rnd.randint(19, 78),
                    gender="Female" if i % 2 else "Male",
                    phone=f"90000{10000 + i}",
                    blood_group=rnd.choice(["A+", "B+", "O+", "AB+", "O-", "A-"]),
                    allergies=rnd.choice(["", "", "", "Penicillin", "Sulfa drugs", "Dust"]),
                    created_at=now() - dt.timedelta(days=rnd.randint(15, 300)))
        db.add(p)
        patients.append(p)
    db.flush()
    for p in patients:
        p.pid = make_pid(p)
    for p in patients[:3]:
        db.add(make_user(p.pid, DEMO_PASSWORD, p.name, "patient", patient_id=p.id))

    def add_visit(patient, dept, checkin, wait, consult, status="done", token_no=1, referred_from="", case=None):
        complaint, diagnosis, meds = case or rnd.choice(CLINICAL[dept])
        doc = rnd.choice(doctors[dept])
        v = Visit(patient_id=patient.id, department=dept, token=f"{DEPT_CODE[dept]}-{token_no:03d}",
                  status=status, checkin_at=checkin, complaint=complaint, referred_from=referred_from)
        if status in ("done", "in_consultation"):
            v.doctor_id = doc.id
            v.start_at = checkin + dt.timedelta(minutes=wait)
            v.bp = f"{rnd.randint(108, 148)}/{rnd.randint(68, 94)}"
            v.temp = f"{rnd.uniform(97.4, 100.6):.1f}"
            v.pulse = str(rnd.randint(64, 104))
            v.spo2 = str(rnd.randint(95, 99))
        if status == "done":
            v.end_at = v.start_at + dt.timedelta(minutes=consult)
            v.diagnosis = diagnosis
            v.notes = "Advised rest and review if symptoms persist."
        db.add(v)
        db.flush()
        if status == "done":
            for med, dose, days in meds:
                db.add(Prescription(visit_id=v.id, patient_id=patient.id, doctor_id=doc.id, medicine=med,
                                    dosage=dose, duration=days, created_at=v.end_at))
        return v

    today = now().replace(hour=0, minute=0, second=0)
    depts = list(WEIGHT)
    for back in range(14, 0, -1):
        day = today - dt.timedelta(days=back)
        counters = {d: 0 for d in depts}
        busy = 0.75 if day.weekday() == 6 else 1.15 if day.weekday() == 0 else 1.0
        for _ in range(int(rnd.randint(30, 42) * busy)):
            dept = rnd.choices(depts, weights=[WEIGHT[d] for d in depts])[0]
            hour = rnd.choice(HOURS)
            peak = 1.45 if hour in (10, 11, 18) else 1.0
            wait = max(2, int(rnd.gauss(BASE_WAIT[dept] * peak * busy, 7)))
            counters[dept] += 1
            pool = [p for p in patients[3:] if (p.age < 16) == (dept == "Pediatrics")]
            add_visit(rnd.choice(pool), dept, day.replace(hour=hour, minute=rnd.randint(0, 59)), wait,
                      rnd.randint(7, 19), token_no=counters[dept])

    # A cross-department story for the first demo patient: Orthopedics two days ago, referred to Cardiology today.
    hero = patients[0]
    add_visit(hero, "General Medicine", today - dt.timedelta(days=20, hours=-10), 19, 11, token_no=90,
              case=CLINICAL["General Medicine"][2])
    add_visit(hero, "Orthopedics", today - dt.timedelta(days=2, hours=-11), 26, 14, token_no=91,
              case=CLINICAL["Orthopedics"][0])

    # Today's live queue, placed in the last couple of hours.
    current = now()
    counters = {d: 0 for d in depts}

    def today_visit(patient, dept, minutes_ago, status, **kw):
        counters[dept] += 1
        checkin = max(today, current - dt.timedelta(minutes=minutes_ago))
        return add_visit(patient, dept, checkin, max(1, minutes_ago - 12) if status != "waiting" else 0,
                         9, status=status, token_no=counters[dept], **kw)

    adults = iter([p for p in patients[3:] if p.age >= 16])
    kids = iter([p for p in patients[3:] if p.age < 16])
    for dept, done_n, waiting_n in [("General Medicine", 5, 4), ("Cardiology", 3, 3), ("Orthopedics", 3, 2),
                                    ("Neurology", 2, 2), ("Pediatrics", 2, 1), ("Emergency", 2, 1)]:
        pool = kids if dept == "Pediatrics" else adults
        for k in range(done_n):
            v = today_visit(next(pool), dept, 170 - k * 18, "done")
            v.start_at = v.checkin_at + dt.timedelta(minutes=rnd.randint(8, 30))
            v.end_at = min(current, v.start_at + dt.timedelta(minutes=rnd.randint(7, 15)))
            v.start_at = min(v.start_at, v.end_at)
        for k in range(waiting_n):
            today_visit(next(pool), dept, 38 - k * 9, "waiting")
    today_visit(hero, "Cardiology", 6, "waiting", referred_from="Orthopedics",
                case=("Breathlessness noted during knee assessment", "", []))
    today_visit(patients[1], "General Medicine", 4, "waiting")

    beds = []
    for ward, prefix, count in WARDS:
        for n in range(1, count + 1):
            bed = Bed(ward=ward, label=f"{prefix}-{n}")
            roll = rnd.random()
            if roll < 0.55:
                bed.status = "occupied"
                bed.patient_id = rnd.choice(patients[5:]).id
            elif roll < 0.63:
                bed.status = "cleaning"
            beds.append(bed)
    db.add_all(beds)

    u = users
    r1 = Request(created_by=u["nurse.priya"].id, kind="Supplies", title="Extra infusion pump for Cardiology ward",
                 details="Two patients need continuous infusion tonight and only one pump is free.",
                 approver_role="doctor", approver_id=u["dr.arjun"].id, created_at=now() - dt.timedelta(minutes=50))
    r2 = Request(created_by=u["dr.kavya"].id, kind="Equipment", title="Portable X-ray unit servicing",
                 details="Image quality has dropped this week. Requesting a service visit.",
                 approver_role="dean", created_at=now() - dt.timedelta(hours=5))
    r3 = Request(created_by=u["reception.ravi"].id, kind="Shift change", title="Swap Saturday morning shift",
                 details="Requesting a swap with Divya for Saturday morning.", approver_role="dean",
                 created_at=now() - dt.timedelta(hours=26), status="approved",
                 closed_at=now() - dt.timedelta(hours=22))
    db.add_all([r1, r2, r3])
    db.flush()
    db.add_all([
        RequestEvent(request_id=r1.id, user_id=r1.created_by, action="created", at=r1.created_at),
        RequestEvent(request_id=r2.id, user_id=r2.created_by, action="created", at=r2.created_at),
        RequestEvent(request_id=r3.id, user_id=r3.created_by, action="created", at=r3.created_at),
        RequestEvent(request_id=r3.id, user_id=u["dean"].id, action="approved", note="Approved. Please update the roster.",
                     at=r3.closed_at),
    ])
    db.add_all([
        Task(title="Record vitals for all waiting Cardiology patients", assigned_by=u["dr.arjun"].id,
             assigned_to=u["nurse.priya"].id, priority="urgent"),
        Task(title="Prepare discharge summary for bed A-4", assigned_by=u["dr.rahul"].id,
             assigned_to=u["nurse.latha"].id),
        Task(title="Review last week's waiting time report", assigned_by=u["chairman"].id, assigned_to=u["dean"].id),
        Task(title="Audit Orthopedics follow-up schedule", assigned_by=u["dean"].id, assigned_to=u["dr.kavya"].id,
             status="in_progress"),
    ])
    db.add_all([
        Message(from_id=u["dr.kavya"].id, to_id=u["dr.arjun"].id,
                body=f"Referring {hero.name} ({hero.pid}) to you. Breathless during knee assessment, please check.",
                created_at=now() - dt.timedelta(minutes=7)),
        Message(from_id=u["nurse.priya"].id, to_id=u["dr.arjun"].id, body="Vitals are done for the first two tokens.",
                created_at=now() - dt.timedelta(minutes=15)),
        Message(from_id=u["dean"].id, to_id=u["reception.ravi"].id,
                body="Please route walk-in fever cases to General Medicine today.",
                created_at=now() - dt.timedelta(hours=2)),
    ])
    # A few booked appointments for today, at the next free half-hour slots.
    upcoming = [s for s in SLOTS if s > current.strftime("%H:%M")] or SLOTS[-3:]
    booked = [(patients[2], "Neurology", "Follow-up for recurring headache"),
              (patients[45], "General Medicine", "Blood sugar review"),
              (patients[46], "Orthopedics", "Knee pain review")]
    for n, (patient, dept, reason) in enumerate(booked):
        db.add(Appointment(patient_id=patient.id, department=dept, day=today.date().isoformat(),
                           slot=upcoming[min(n, len(upcoming) - 1)], reason=reason))
    db.add(Setting(key="cognos_url", value=os.environ.get("COGNOS_DASHBOARD_URL", "")))
    db.commit()
