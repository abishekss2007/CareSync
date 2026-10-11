"""Synthetic demo data. No real patient information is used anywhere in this project."""
import datetime as dt
import hashlib
import os
import random
import secrets

from .catalog import ensure_catalog
from .db import (Appointment, Bed, Dispatch, EmergencyAlert, EmergencyEvent, EquipmentAsset, EquipmentCatalogItem,
                 EquipmentEvent, EquipmentRequest, InventoryItem, MaintenanceEvent, MaintenanceTicket, Message, Patient,
                 Prescription, Request, RequestEvent, Setting, SourcingOrder, StockTransaction, Supplier, Task, User,
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
# Added with the emergency and equipment modules; also added to older demo databases without rebuilding them.
EXTRA_STAFF = [
    ("admin", "Sandhya Varghese", "admin", None),
    ("stores.thomas", "Thomas Abraham", "coordinator", None),
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
    seed_extras(db)


# (catalogue name, model, location, min stock, [available, reserved, in service, maintenance, damaged], tag prefix)
STOCK = [
    ("Multiparameter patient monitor", "Mindray uMEC 12", "Biomedical store", 2, [3, 0, 9, 1, 0], "MON"),
    ("ICU ventilator", "Hamilton C3", "Biomedical store", 1, [1, 0, 5, 0, 0], "VEN"),
    ("Infusion pump", "B. Braun Infusomat", "Biomedical store", 3, [4, 0, 10, 1, 0], "INF"),
    ("Syringe pump", "B. Braun Perfusor", "Biomedical store", 2, [3, 0, 6, 0, 0], "SYR"),
    ("Defibrillator", "Philips HeartStart XL+", "Biomedical store", 1, [2, 0, 4, 0, 0], "DEF"),
    ("Portable suction unit", "Laerdal LCSU 4", "Central stores", 2, [1, 0, 3, 0, 0], "SUC"),
    ("Wheelchair", "Karma KM-2500", "Central stores", 4, [6, 0, 14, 0, 1], "WCH"),
    ("Stretcher trolley", "Hydraulic, 5-function", "Central stores", 2, [3, 0, 8, 0, 0], "STR"),
    ("Hospital bed", "Semi-Fowler, manual", "Central stores", 2, [3, 0, 0, 0, 0], "BED"),
    ("Stethoscope", "Littmann Classic III", "Central stores", 5, [12, 0, 0, 0, 0], "STH"),
    ("BP apparatus", "Omron HBP-1320", "Central stores", 4, [6, 0, 0, 0, 0], "BPA"),
    ("Pulse oximeter", "Masimo MightySat", "Central stores", 4, [7, 0, 0, 0, 0], "POX"),
    ("ECG machine", "BPL Cardiart 9108", "Biomedical store", 1, [1, 0, 3, 0, 0], "ECG"),
    ("Surgical scissors", "Mayo, 17 cm", "Central sterile supply", 10, [24, 0, 0, 0, 0], "SCI"),
    ("Portable oxygen cylinder and regulator", "D-type with regulator", "Gas store", 4, [8, 0, 6, 0, 0], "OXY"),
    ("Surgical gloves", "Sterile, size 7, box of 50", "Central stores", 80, [240, 0, 0, 0, 0], None),
    ("Face masks", "3-ply, box of 50", "Central stores", 80, [55, 0, 0, 0, 0], None),
    ("Syringes and needles", "5 ml, box of 100", "Central stores", 40, [120, 0, 0, 0, 0], None),
    ("IV cannulas", "20G, box of 50", "Central stores", 30, [26, 0, 0, 0, 0], None),
    ("Gauze and bandages", "Sterile gauze, pack of 100", "Central stores", 30, [90, 0, 0, 0, 0], None),
    ("Bed linen", "Sheet set", "Linen store", 100, [320, 0, 0, 0, 0], None),
    ("Sharps containers", "5 litre", "Central stores", 20, [44, 0, 0, 0, 0], None),
    ("Colour-coded biomedical waste bins and bags", "Bag roll, 50", "Central stores", 30, [70, 0, 0, 0, 0], None),
]
SUPPLIERS = [("MedEquip Distributors", "supplier", "Anil Joseph", "0484 2400 110"),
             ("Kerala Surgicals", "supplier", "Reena Paul", "0484 2311 202"),
             ("BioCare Service Engineers", "service", "Vinod Menon", "0484 2650 330"),
             ("Southern Medical Gases", "supplier", "Hari Prasad", "0484 2209 404")]


def seed_extras(db):
    """Administrator and coordinator accounts, stock, suppliers and sample equipment and emergency records."""
    ensure_catalog(db)
    users = {u.username: u for u in db.query(User).all()}
    for username, name, role, dept in EXTRA_STAFF:
        if username not in users:
            users[username] = make_user(username, DEMO_PASSWORD, name, role, dept)
            db.add(users[username])
    db.flush()
    if db.query(InventoryItem).count():
        db.commit()
        return
    u = users
    rnd = random.Random(11)
    current = now()
    suppliers = {}
    for name, kind, contact, phone in SUPPLIERS:
        suppliers[name] = Supplier(name=name, kind=kind, contact=contact, phone=phone)
        db.add(suppliers[name])
    db.flush()
    catalog = {c.name: c for c in db.query(EquipmentCatalogItem).all()}
    items = {}
    depts = list(DEPT_CODE)
    for name, model, location, min_stock, counts, prefix in STOCK:
        c = catalog[name]
        avail, res, used, maint, dmg = counts
        nxt = (current.date() + dt.timedelta(days=rnd.randint(2, 150))).isoformat() if c.needs_service else ""
        i = InventoryItem(code="", catalog_id=c.id, name=name, category=c.category, model=model, tracking=c.tracking,
                          unit=c.unit, total=sum(counts), available=avail, reserved=res, in_service=used,
                          maintenance=maint, damaged=dmg, min_stock=min_stock, location=location,
                          supplier_id=suppliers["MedEquip Distributors" if c.tracking == "asset" else "Kerala Surgicals"].id,
                          warranty="3 years from purchase" if c.tracking == "asset" else "",
                          last_maintenance=(current.date() - dt.timedelta(days=rnd.randint(20, 170))).isoformat() if nxt else "",
                          next_maintenance=nxt, low_notified=avail < min_stock)
        db.add(i)
        db.flush()
        i.code = f"INV-{i.id:04d}"
        items[name] = i
        if prefix:
            n = 0
            for state, k in zip(("available", "reserved", "in_service", "maintenance", "damaged"), counts):
                for _ in range(k):
                    n += 1
                    db.add(EquipmentAsset(inventory_id=i.id, asset_tag=f"CS-{prefix}-{n:03d}", serial=f"SN{rnd.randint(100000, 999999)}",
                                          state=state, department=rnd.choice(depts) if state == "in_service" else "",
                                          condition="damaged" if state == "damaged" else "good",
                                          warranty_until=(current.date() + dt.timedelta(days=rnd.randint(60, 900))).isoformat(),
                                          next_maintenance=nxt))
        db.add(StockTransaction(inventory_id=i.id, kind="receive", qty=i.total, from_state="outside", to_state="available",
                                user_id=u["stores.thomas"].id, note="Opening stock", at=current - dt.timedelta(days=30)))
    db.flush()

    def request(n, who, name, qty, urgency, why, rtype="new", hours=3, **kw):
        doc = u[who]
        c = catalog[name]
        r = EquipmentRequest(ref=f"EQ-{current.year}-{n:04d}", idem_key=f"seed-{n}-{secrets.token_hex(6)}",
                             created_by=doc.id, department=doc.department, location=kw.pop("location", doc.department + " ward"),
                             catalog_id=c.id, item_name=name, category=c.category, request_type=rtype, quantity=qty,
                             urgency=urgency, justification=why, created_at=current - dt.timedelta(hours=hours),
                             updated_at=current - dt.timedelta(hours=hours), **kw)
        db.add(r)
        db.flush()
        db.add(EquipmentEvent(request_id=r.id, user_id=doc.id, action="created", to_status="pending_dean", qty=qty,
                              note=f"{qty} x {name}", at=r.created_at))
        return r

    def event(r, who, action, frm, to, note="", qty=None, hours=1):
        db.add(EquipmentEvent(request_id=r.id, user_id=u[who].id if who else None, action=action, from_status=frm,
                              to_status=to, qty=qty, note=note, at=current - dt.timedelta(hours=hours)))

    request(1, "dr.arjun", "Infusion pump", 2, "urgent",
            "Two post-angioplasty patients need continuous heparin infusion tonight; the ward has one free pump.", hours=2)
    request(2, "dr.sana", "EEG machine", 1, "routine",
            "Annual calibration is due and the trace shows baseline drift on two channels.", "servicing", hours=20)
    r3 = request(3, "dr.vikram", "Pediatric cot", 2, "routine", "Winter admissions are rising in the pediatric ward.",
                 hours=30, dean_status="clarification", status="clarification", clarification_from=u["dean"].id)
    event(r3, "dean", "clarification requested", "pending_dean", "clarification",
          "How many cots are out of service now, and can the two in the store room be repaired instead?", hours=26)
    r4 = request(4, "dr.kavya", "Wheelchair", 3, "routine", "Outpatient knee and hip patients wait for wheelchairs at the entrance.",
                 hours=28, dean_status="approved", status="approved", qty_approved=3, decided_by=u["dean"].id,
                 decision_note="Approved.")
    event(r4, "dean", "approved", "pending_dean", "approved", "Approved.", 3, hours=24)
    r5 = request(5, "dr.joseph", "Portable suction unit", 2, "critical",
                 "Only one working suction unit in the emergency bays; trauma cases need one per bay.", hours=72,
                 dean_status="approved", status="sourcing", qty_approved=2, qty_sourced=2, decided_by=u["dean"].id,
                 procurement_status="sourcing", supplier_id=suppliers["MedEquip Distributors"].id,
                 expected_date=(current.date() - dt.timedelta(days=1)).isoformat(), location="Emergency bays")
    event(r5, "dean", "approved", "pending_dean", "approved", "Approved, urgent.", 2, hours=70)
    event(r5, "stores.thomas", "stock checked", "approved", "sourcing_required", "1 available, 2 needed", hours=69)
    event(r5, "stores.thomas", "sourcing", "sourcing_required", "sourcing", "2 from MedEquip Distributors, ref PO-2210", 2, hours=68)
    db.add(SourcingOrder(request_id=r5.id, supplier_id=suppliers["MedEquip Distributors"].id, reference="PO-2210",
                         qty_ordered=2, expected_date=r5.expected_date, created_by=u["stores.thomas"].id,
                         created_at=current - dt.timedelta(hours=68)))
    masks = items["Face masks"]
    r6 = request(6, "dr.rahul", "Face masks", 50, "urgent", "Fever clinic volumes doubled this week.", "consumable", hours=50,
                 dean_status="approved", status="partially_fulfilled", qty_approved=50, qty_dispatched=30,
                 qty_delivered=30, decided_by=u["dean"].id, inventory_id=masks.id, procurement_status="stock_checked",
                 dispatch_status="partially_delivered")
    event(r6, "dean", "approved", "pending_dean", "approved", "Approved.", 50, hours=48)
    event(r6, "stores.thomas", "dispatched", "approved", "dispatched", "30 to General Medicine OPD, carried by Ajith", 30, hours=40)
    event(r6, "dr.rahul", "delivery confirmed", "dispatched", "partially_fulfilled", "30 of 30 received by Latha Suresh", 30, hours=39)
    db.add(Dispatch(idem_key=f"seed-d-{secrets.token_hex(6)}", request_id=r6.id, inventory_id=masks.id, qty=30,
                    destination="General Medicine OPD", handled_by="Ajith (stores porter)", dispatched_by=u["stores.thomas"].id,
                    dispatched_at=current - dt.timedelta(hours=40), status="delivered", qty_delivered=30,
                    received_by="Latha Suresh", confirmed_by=u["dr.rahul"].id, delivered_at=current - dt.timedelta(hours=39)))
    db.add(StockTransaction(inventory_id=masks.id, request_id=r6.id, kind="dispatch", qty=30, from_state="reserved",
                            to_state="outside", user_id=u["stores.thomas"].id, note="To General Medicine OPD",
                            at=current - dt.timedelta(hours=40)))

    pump = items["Infusion pump"]
    broken = db.query(EquipmentAsset).filter(EquipmentAsset.inventory_id == pump.id, EquipmentAsset.state == "maintenance").first()
    broken.condition, broken.department = "unsafe", "Cardiology"
    t = MaintenanceTicket(ref=f"MT-{current.year}-0001", idem_key=f"seed-m-{secrets.token_hex(6)}", inventory_id=pump.id,
                          asset_id=broken.id, item_name=pump.name, qty=1, qty_held=1, held_from="in_service",
                          department="Cardiology", reported_by=u["nurse.priya"].id,
                          issue="Occlusion alarm fails to trigger during the pre-use check.", unsafe=True, status="assigned",
                          technician="Vinod Menon", supplier_id=suppliers["BioCare Service Engineers"].id,
                          created_at=current - dt.timedelta(hours=9), updated_at=current - dt.timedelta(hours=6))
    db.add(t)
    db.flush()
    db.add_all([MaintenanceEvent(ticket_id=t.id, user_id=u["nurse.priya"].id, action="reported",
                                 note="UNSAFE. " + t.issue, at=t.created_at),
                MaintenanceEvent(ticket_id=t.id, user_id=u["stores.thomas"].id, action="assign",
                                 note="Assigned to Vinod Menon, BioCare Service Engineers", at=t.updated_at)])

    # One closed emergency from yesterday, for the alert history and acknowledgement report.
    patient = db.query(Patient).order_by(Patient.id).offset(12).first()
    created = (current - dt.timedelta(days=1)).replace(hour=15, minute=10)
    a = EmergencyAlert(ern=f"ER-{created.year}-0001", idem_key=f"seed-e-{secrets.token_hex(6)}", patient_id=patient.id,
                       emergency_type="Road traffic accident", description="Two-wheeler collision, head and left arm injury, conscious.",
                       priority="critical", triage_level="Level 2 - Emergent", location="Emergency bay 2", team="Emergency",
                       assigned_doctor_id=u["dr.joseph"].id, status="closed", arrival_at=created - dt.timedelta(minutes=2),
                       created_by=u["reception.ravi"].id, created_at=created, received_at=created + dt.timedelta(seconds=20),
                       acknowledged_at=created + dt.timedelta(seconds=75), acknowledged_by=u["dr.joseph"].id,
                       updated_at=created + dt.timedelta(hours=2), closed_at=created + dt.timedelta(hours=2))
    db.add(a)
    db.flush()
    steps = [(0, "reception.ravi", "created", "", "alert_created", "critical · Road traffic accident"),
             (0, None, "status", "alert_created", "notification_sent", "Saved notifications for the alert recipients"),
             (75, "dr.joseph", "status", "notification_sent", "acknowledged", ""),
             (240, "dr.joseph", "status", "acknowledged", "response_started", "In bay 2"),
             (600, "dr.joseph", "triage", "critical", "critical / Level 2 - Emergent", "Stable airway, GCS 14"),
             (900, "dr.joseph", "status", "response_started", "under_care", ""),
             (5400, "dr.joseph", "status", "under_care", "admitted", "Admitted to General A for observation"),
             (7200, "dr.joseph", "status", "admitted", "closed", "Handed over to the ward team")]
    for secs, who, action, frm, to, note in steps:
        db.add(EmergencyEvent(alert_id=a.id, user_id=u[who].id if who else None, action=action, from_value=frm,
                              to_value=to, note=note, at=created + dt.timedelta(seconds=secs)))
    db.commit()
