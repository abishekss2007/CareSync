"""CareSync: one hospital app with role-based workspaces. Every access rule is enforced here on the server."""
import csv
import datetime as dt
import hmac
import io
import math
import os
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Header
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from . import ai, analytics_sync, reporting
from .catalog import ensure_catalog
from .db import (ROOT, Appointment, AuditLog, Base, Bed, Message, Notification, Patient, Prescription, Request,
                 RequestEvent, SessionLocal, Setting, Task, User, Visit, engine, get_db, migrate, now)
from .db import Session as AuthSession
from .seed import DEPARTMENTS, DEPT_CODE, SLOTS, hash_password, make_pid, make_user, seed

DEMO_MODE = os.environ.get("DEMO_MODE", "1") == "1"
SESSION_HOURS = 12
STAFF = {"chairman", "dean", "doctor", "nurse", "receptionist", "admin", "coordinator"}
CLINICAL = {"chairman", "dean", "doctor", "nurse"}
LEADERS = {"chairman", "dean"}
RANK = {"chairman": 5, "dean": 4, "admin": 4, "doctor": 3, "nurse": 2, "receptionist": 2, "coordinator": 2, "patient": 0}
NEXT_LEVEL = {"nurse": "doctor", "receptionist": "dean", "doctor": "dean", "dean": "chairman", "admin": "chairman",
              "coordinator": "dean"}
PRIORITY_RANK = {"critical": 0, "urgent": 1, "normal": 2}
REQUEST_KINDS = ["Supplies", "Equipment", "Shift change", "Leave", "Patient transfer", "Other"]


def today_start():
    return now().replace(hour=0, minute=0, second=0)


def rebuild_demo():
    """Rebuild the sample data. Settings such as the Cognos dashboard link are kept."""
    kept = {}
    try:
        with SessionLocal() as db:
            kept = {row.key: row.value for row in db.scalars(select(Setting)) if row.value}
    except Exception:  # first run: the tables do not exist yet
        pass
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
        for key, value in kept.items():
            row = db.get(Setting, key)
            if row:
                row.value = value
            else:
                db.add(Setting(key=key, value=value))
        db.commit()


def add_demo_extras(db):
    """Demo databases made before the administrator, coordinator and equipment data existed get them added.
    Nothing is dropped or rebuilt."""
    from .seed import seed_extras
    if not db.scalar(select(User).where(User.role == "coordinator")):
        seed_extras(db)


def refresh_demo_if_stale():
    """Demo data is built around "today", so rebuild it when the day has changed."""
    with SessionLocal() as db:
        empty = db.scalar(select(func.count()).select_from(User)) == 0
        stale = DEMO_MODE and not empty and db.scalar(
            select(func.count()).select_from(Visit).where(Visit.checkin_at >= today_start())) == 0
    if empty or stale:
        rebuild_demo()


@asynccontextmanager
async def lifespan(_app):
    Base.metadata.create_all(engine)
    migrate()
    refresh_demo_if_stale()
    with SessionLocal() as db:
        ensure_catalog(db)
        if DEMO_MODE:
            add_demo_extras(db)
    analytics_sync.start()
    live.start_watchdog()
    yield
    live.stop_watchdog()
    analytics_sync.stop()


app = FastAPI(title="CareSync", lifespan=lifespan, docs_url=None, redoc_url=None)


@app.middleware("http")
async def no_cache(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


# ---------- auth ----------

def current_user(authorization: str = Header(default=""), db=Depends(get_db)):
    token = authorization[7:] if authorization.startswith("Bearer ") else ""
    session = db.get(AuthSession, token) if token else None
    if not session or session.created_at < now() - dt.timedelta(hours=SESSION_HOURS):
        raise HTTPException(401, "Please sign in again")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, "Please sign in again")
    return user


def require(*roles):
    def dep(user=Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(403, "Your role does not have access to this")
        return user
    return dep


staff_only = require(*STAFF)


def iso(value):
    return value.isoformat() if value else None


def user_out(u):
    return {"id": u.id, "name": u.name, "role": u.role, "department": u.department, "available": u.available}


def uname(db, user_id):
    u = db.get(User, user_id) if user_id else None
    return u.name if u else ""


def bump(db, *keys):
    """Wake the live streams of these users (ids) or topics ("emergency", "equipment") once this commit lands."""
    db.info.setdefault("bump", set()).update(keys)


def notify(db, user_ids, text, view="", kind="", ref=""):
    ids = {uid for uid in user_ids if uid}
    for uid in ids:
        db.add(Notification(user_id=uid, text=text[:300], view=view, kind=kind, ref=str(ref)[:40]))
    bump(db, *ids)


def role_ids(db, role, department=None):
    q = select(User.id).where(User.role == role)
    if department:
        q = q.where(User.department == department)
    return list(db.scalars(q))


def audit(db, user, action, target=""):
    db.add(AuditLog(user_id=user.id, action=action, target=target[:160]))


class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(default="", max_length=128)


FAILS = {}


def open_session(db, user):
    token = secrets.token_hex(32)
    db.add(AuthSession(token=token, user_id=user.id))
    audit(db, user, "signed in")
    db.commit()
    return {"token": token, "user": user_out(user)}


@app.post("/api/login")
def login(body: LoginIn, db=Depends(get_db)):
    key = body.username.strip().lower()
    count, since = FAILS.get(key, (0, 0))
    if count >= 8 and time.time() - since < 300:
        raise HTTPException(429, "Too many attempts. Try again in a few minutes")
    user = db.scalar(select(User).where(func.lower(User.username) == key))
    if not user or not hmac.compare_digest(user.password_hash, hash_password(body.password, user.salt)):
        FAILS[key] = (count + 1 if time.time() - since < 300 else 1, time.time())
        raise HTTPException(401, "Wrong username or password")
    FAILS.pop(key, None)
    if not user.active:
        raise HTTPException(403, "This account has been disabled. Ask the dean to enable it")
    return open_session(db, user)


@app.get("/api/demo/accounts")
def demo_accounts():
    if not DEMO_MODE:
        return []
    refresh_demo_if_stale()  # the sign-in page calls this, so a server left running overnight still shows a live queue
    with SessionLocal() as db:
        return _demo_accounts(db)


def _demo_accounts(db):
    users = db.scalars(select(User).where(User.active == True).order_by(User.id)).all()  # noqa: E712
    order = ["chairman", "dean", "admin", "doctor", "nurse", "receptionist", "coordinator", "patient"]
    users.sort(key=lambda u: (order.index(u.role), u.id))
    return [{"username": u.username, "name": u.name, "role": u.role, "department": u.department} for u in users]


@app.post("/api/demo/login")
def demo_login(body: LoginIn, db=Depends(get_db)):
    if not DEMO_MODE:
        raise HTTPException(404, "Not found")
    user = db.scalar(select(User).where(User.username == body.username))
    if not user or not user.active:
        raise HTTPException(404, "No such demo account")
    return open_session(db, user)


@app.post("/api/demo/reset")
def demo_reset(_=Depends(require("chairman"))):
    if not DEMO_MODE:
        raise HTTPException(404, "Not found")
    rebuild_demo()
    return {"ok": True}


@app.post("/api/logout")
def logout(authorization: str = Header(default=""), db=Depends(get_db)):
    session = db.get(AuthSession, authorization[7:])
    if session:
        db.delete(session)
        db.commit()
    return {"ok": True}


class PasswordIn(BaseModel):
    current: str = Field(max_length=128)
    new: str = Field(min_length=8, max_length=128)


@app.post("/api/password")
def change_password(body: PasswordIn, db=Depends(get_db), user=Depends(current_user)):
    if not hmac.compare_digest(user.password_hash, hash_password(body.current, user.salt)):
        raise HTTPException(400, "Your current password is not correct")
    user.salt = secrets.token_hex(16)
    user.password_hash = hash_password(body.new, user.salt)
    audit(db, user, "changed own password")
    db.commit()
    return {"ok": True}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return {"user": user_out(user), "departments": DEPARTMENTS, "request_kinds": REQUEST_KINDS,
            "watsonx": ai.configured(), "demo": DEMO_MODE, "clinical": user.role in CLINICAL}


# ---------- live hospital state ----------

def live_state(db):
    start = today_start()
    active = db.scalars(select(Visit).where(Visit.checkin_at >= start,
                                            Visit.status.in_(["waiting", "in_consultation"]))
                        .order_by(Visit.checkin_at, Visit.id)).all()
    active.sort(key=queue_key)  # clinical priority first, then arrival; the stored records are not changed
    doctors = db.scalars(select(User).where(User.role == "doctor").order_by(User.name)).all()
    rows = db.execute(select(Visit.department, Visit.start_at, Visit.end_at)
                      .where(Visit.status == "done", Visit.checkin_at >= start - dt.timedelta(days=14))).all()
    totals = {}
    for dept, s, e in rows:
        if s and e:
            minutes, n = totals.get(dept, (0, 0))
            totals[dept] = (minutes + (e - s).total_seconds() / 60, n + 1)
    avg = {d: max(5.0, totals[d][0] / totals[d][1]) if d in totals else 12.0 for d in DEPARTMENTS}
    return {"active": active, "doctors": doctors, "avg": avg}


def estimate(state, dept, ahead):
    docs = max(1, sum(1 for d in state["doctors"] if d.department == dept and d.available))
    busy = min(docs, sum(1 for v in state["active"] if v.department == dept and v.status == "in_consultation"))
    return math.ceil((ahead + 0.5 * busy) * state["avg"][dept] / docs)


def queue_key(v):
    return (PRIORITY_RANK.get(v.priority or "normal", 2), v.checkin_at, v.id)


def ahead_of(state, visit):
    return sum(1 for v in state["active"] if v.department == visit.department and v.status == "waiting"
               and queue_key(v) < queue_key(visit))


@app.get("/api/status")
def status(db=Depends(get_db), _=Depends(current_user)):
    state = live_state(db)
    depts = []
    for d in DEPARTMENTS:
        waiting = sum(1 for v in state["active"] if v.department == d and v.status == "waiting")
        depts.append({
            "name": d, "waiting": waiting,
            "in_consultation": sum(1 for v in state["active"] if v.department == d and v.status == "in_consultation"),
            "doctors_available": sum(1 for u in state["doctors"] if u.department == d and u.available),
            "est_wait": estimate(state, d, waiting),
        })
    wards = {}
    for bed in db.scalars(select(Bed)).all():
        w = wards.setdefault(bed.ward, {"ward": bed.ward, "total": 0, "free": 0})
        w["total"] += 1
        w["free"] += bed.status == "free"
    return {"departments": depts, "doctors": [user_out(u) for u in state["doctors"]],
            "wards": list(wards.values()), "updated": iso(now())}


# ---------- patients ----------

def patient_out(p):
    return {"pid": p.pid, "name": p.name, "age": p.age, "gender": p.gender, "phone": p.phone,
            "blood_group": p.blood_group, "allergies": p.allergies, "registered": iso(p.created_at)}


def visit_out(db, v, clinical=True, patient=None):
    p = patient or db.get(Patient, v.patient_id)
    out = {"id": v.id, "token": v.token, "department": v.department, "status": v.status,
           "checkin_at": iso(v.checkin_at), "start_at": iso(v.start_at), "end_at": iso(v.end_at),
           "doctor": uname(db, v.doctor_id), "doctor_id": v.doctor_id, "referred_from": v.referred_from,
           "complaint": v.complaint, "priority": v.priority or "normal",
           "patient": {"pid": p.pid, "name": p.name, "age": p.age, "gender": p.gender, "allergies": p.allergies}}
    if clinical:
        meds = db.scalars(select(Prescription).where(Prescription.visit_id == v.id).order_by(Prescription.id)).all()
        out.update({"diagnosis": v.diagnosis, "notes": v.notes, "referred_by": uname(db, v.referred_by),
                    "vitals": {"bp": v.bp, "temp": v.temp, "pulse": v.pulse, "spo2": v.spo2,
                               "by": uname(db, v.vitals_by)},
                    "prescriptions": [{"medicine": m.medicine, "dosage": m.dosage, "duration": m.duration}
                                      for m in meds]})
    return out


def find_patient(db, pid):
    p = db.scalar(select(Patient).where(Patient.pid == pid.strip().upper()))
    if not p:
        raise HTTPException(404, "No patient with that ID")
    return p


def record(db, p, clinical):
    visits = db.scalars(select(Visit).where(Visit.patient_id == p.id)
                        .order_by(Visit.checkin_at.desc(), Visit.id.desc())).all()
    bed = db.scalar(select(Bed).where(Bed.patient_id == p.id))
    return {"patient": patient_out(p), "clinical": clinical,
            "bed": {"ward": bed.ward, "label": bed.label} if bed else None,
            "visits": [visit_out(db, v, clinical, p) for v in visits]}


class PatientIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    age: int = Field(ge=0, le=120)
    gender: str = Field(max_length=12)
    phone: str = Field(default="", max_length=20)
    blood_group: str = Field(default="", max_length=6)
    allergies: str = Field(default="", max_length=240)


@app.post("/api/patients")
def register_patient(body: PatientIn, db=Depends(get_db), user=Depends(require("receptionist"))):
    p = Patient(name=body.name.strip(), age=body.age, gender=body.gender, phone=body.phone.strip(),
                blood_group=body.blood_group, allergies=body.allergies.strip())
    db.add(p)
    db.flush()
    p.pid = make_pid(p)
    pin = f"{secrets.randbelow(900000) + 100000}"
    db.add(make_user(p.pid, pin, p.name, "patient", patient_id=p.id))
    audit(db, user, "registered patient", p.pid)
    db.commit()
    return {"patient": patient_out(p), "pin": pin}


@app.get("/api/patients")
def search_patients(q: str = "", db=Depends(get_db), _=Depends(staff_only)):
    term = q.strip().lower()
    query = select(Patient)
    if term:
        query = query.where(or_(func.lower(Patient.pid).contains(term), func.lower(Patient.name).contains(term)))
    rows = db.scalars(query.order_by(Patient.id.desc()).limit(25)).all()
    return [patient_out(p) for p in rows]


@app.get("/api/patients/{pid}")
def patient_record(pid: str, db=Depends(get_db), user=Depends(staff_only)):
    p = find_patient(db, pid)
    audit(db, user, "viewed patient record", p.pid)
    db.commit()
    return record(db, p, user.role in CLINICAL)


@app.get("/api/patients/{pid}/summary")
def patient_summary(pid: str, db=Depends(get_db), user=Depends(require("doctor", "dean", "chairman"))):
    p = find_patient(db, pid)
    data = record(db, p, True)
    audit(db, user, "generated history summary", p.pid)
    db.commit()
    return ai.summarize(data["patient"], data["visits"])


@app.get("/api/my/record")
def my_record(db=Depends(get_db), user=Depends(require("patient"))):
    p = db.get(Patient, user.patient_id)
    data = record(db, p, True)
    state = live_state(db)
    data["active"] = None
    for v in state["active"]:
        if v.patient_id == p.id:
            ahead = ahead_of(state, v)
            data["active"] = {"token": v.token, "department": v.department, "status": v.status,
                              "ahead": ahead, "est_wait": estimate(state, v.department, ahead),
                              "doctor": uname(db, v.doctor_id), "checkin_at": iso(v.checkin_at)}
            break
    return data


# ---------- visits and queue ----------

class VisitIn(BaseModel):
    pid: str = Field(max_length=20)
    department: str
    complaint: str = Field(default="", max_length=240)
    priority: str = "normal"


def new_visit(db, patient, department, complaint, referred_from="", referred_by=None, priority="normal"):
    count = db.scalar(select(func.count()).select_from(Visit)
                      .where(Visit.department == department, Visit.checkin_at >= today_start()))
    v = Visit(patient_id=patient.id, department=department, complaint=complaint, priority=priority,
              token=f"{DEPT_CODE[department]}-{count + 1:03d}", referred_from=referred_from, referred_by=referred_by)
    db.add(v)
    db.flush()
    return v


def active_visit(db, patient, department):
    return db.scalar(select(Visit).where(Visit.patient_id == patient.id, Visit.department == department,
                                         Visit.checkin_at >= today_start(),
                                         Visit.status.in_(["waiting", "in_consultation"])))


@app.post("/api/visits")
def issue_token(body: VisitIn, db=Depends(get_db), user=Depends(require("receptionist"))):
    if body.department not in DEPARTMENTS:
        raise HTTPException(400, "Unknown department")
    if body.priority == "critical":
        raise HTTPException(400, "Use Critical Emergency Alert for a critical patient, so the emergency team is alerted")
    if body.priority not in ("normal", "urgent"):
        raise HTTPException(400, "Unknown priority")
    p = find_patient(db, body.pid)
    if active_visit(db, p, body.department):
        raise HTTPException(409, f"{p.name} already has an active token in {body.department}")
    v = new_visit(db, p, body.department, body.complaint.strip(), priority=body.priority)
    state = live_state(db)
    ahead = ahead_of(state, v)
    urgent = "URGENT patient" if body.priority == "urgent" else "New patient"
    notify(db, role_ids(db, "doctor", body.department) + role_ids(db, "nurse", body.department),
           f"{urgent} in queue: {p.name} ({v.token})", "home")
    audit(db, user, "issued token", f"{v.token} for {p.pid}" + (" (urgent)" if body.priority == "urgent" else ""))
    db.commit()
    return {"token": v.token, "department": v.department, "ahead": ahead, "priority": v.priority,
            "est_wait": estimate(state, v.department, ahead), "patient": patient_out(p)}


class TriageIn(BaseModel):
    complaint: str = Field(min_length=3, max_length=240)


@app.post("/api/triage")
def triage(body: TriageIn, db=Depends(get_db), user=Depends(require("receptionist"))):
    # Only the reason text is sent to the model, never the patient's name or ID.
    out = ai.suggest_department(body.complaint.strip(), DEPARTMENTS)
    audit(db, user, "asked for department suggestion", out["department"])
    db.commit()
    return out


@app.get("/api/queue")
def queue(db=Depends(get_db), user=Depends(staff_only)):
    state = live_state(db)
    own = user.department if user.role in ("doctor", "nurse") else None
    out = []
    for v in state["active"]:
        if own and v.department != own:
            continue
        item = visit_out(db, v, user.role in CLINICAL)
        ahead = ahead_of(state, v)
        item["ahead"] = ahead
        item["est_wait"] = estimate(state, v.department, ahead) if v.status == "waiting" else 0
        item["waited"] = max(0, int((now() - v.checkin_at).total_seconds() // 60))
        out.append(item)
    return {"department": own, "visits": out, "available": user.available}


def own_visit(db, visit_id, user):
    v = db.get(Visit, visit_id)
    if not v or v.department != user.department:
        raise HTTPException(404, "That visit is not in your department")
    return v


class VitalsIn(BaseModel):
    bp: str = Field(default="", max_length=12)
    temp: str = Field(default="", max_length=8)
    pulse: str = Field(default="", max_length=8)
    spo2: str = Field(default="", max_length=8)


@app.post("/api/visits/{visit_id}/vitals")
def record_vitals(visit_id: int, body: VitalsIn, db=Depends(get_db), user=Depends(require("nurse", "doctor"))):
    v = own_visit(db, visit_id, user)
    if v.status == "done":
        raise HTTPException(409, "This visit is already closed")
    v.bp, v.temp, v.pulse, v.spo2, v.vitals_by = body.bp.strip(), body.temp.strip(), body.pulse.strip(), body.spo2.strip(), user.id
    audit(db, user, "recorded vitals", v.token)
    db.commit()
    return {"ok": True}


@app.post("/api/visits/{visit_id}/start")
def start_visit(visit_id: int, db=Depends(get_db), user=Depends(require("doctor"))):
    v = own_visit(db, visit_id, user)
    if v.status == "in_consultation" and v.doctor_id == user.id:
        return {"ok": True}
    if v.status != "waiting":
        raise HTTPException(409, "This patient is no longer waiting")
    busy = db.scalar(select(Visit).where(Visit.doctor_id == user.id, Visit.status == "in_consultation",
                                         Visit.checkin_at >= today_start()))
    if busy:
        raise HTTPException(409, f"Finish the consultation for token {busy.token} first")
    v.status, v.doctor_id, v.start_at = "in_consultation", user.id, now()
    patient_user = db.scalar(select(User).where(User.patient_id == v.patient_id))
    if patient_user:
        notify(db, [patient_user.id], f"It is your turn. {user.name} is ready for token {v.token}.", "home")
    db.commit()
    return {"ok": True}


@app.get("/api/visits/{visit_id}")
def get_visit(visit_id: int, db=Depends(get_db), user=Depends(require("doctor"))):
    v = own_visit(db, visit_id, user)
    out = visit_out(db, v, True)
    out["draft"] = v.draft if v.doctor_id == user.id else ""
    return out


class DraftIn(BaseModel):
    draft: str = Field(default="", max_length=8000)


@app.post("/api/visits/{visit_id}/draft")
def save_draft(visit_id: int, body: DraftIn, db=Depends(get_db), user=Depends(require("doctor"))):
    """Keep what the doctor has typed so far, e.g. before they step away for an emergency. The visit stays open."""
    v = own_visit(db, visit_id, user)
    if v.status != "in_consultation" or v.doctor_id != user.id:
        raise HTTPException(409, "This consultation is not open in your room")
    v.draft = body.draft
    db.commit()
    return {"ok": True, "saved_at": iso(now())}


class MedIn(BaseModel):
    medicine: str = Field(min_length=1, max_length=120)
    dosage: str = Field(default="", max_length=60)
    duration: str = Field(default="", max_length=60)


class CompleteIn(BaseModel):
    diagnosis: str = Field(min_length=2, max_length=240)
    notes: str = Field(default="", max_length=2000)
    prescriptions: list[MedIn] = Field(default_factory=list, max_length=12)
    refer_to: str = ""
    refer_reason: str = Field(default="", max_length=200)


@app.post("/api/visits/{visit_id}/complete")
def complete_visit(visit_id: int, body: CompleteIn, db=Depends(get_db), user=Depends(require("doctor"))):
    v = own_visit(db, visit_id, user)
    if v.status != "in_consultation" or v.doctor_id != user.id:
        raise HTTPException(409, "Start this consultation before closing it")
    p = db.get(Patient, v.patient_id)
    referral = None
    if body.refer_to:
        if body.refer_to not in DEPARTMENTS or body.refer_to == v.department:
            raise HTTPException(400, "Choose a different department to refer to")
        if active_visit(db, p, body.refer_to):
            raise HTTPException(409, f"{p.name} is already in the {body.refer_to} queue")
    v.status, v.end_at, v.diagnosis, v.notes = "done", now(), body.diagnosis.strip(), body.notes.strip()
    v.draft = ""
    for m in body.prescriptions:
        db.add(Prescription(visit_id=v.id, patient_id=p.id, doctor_id=user.id, medicine=m.medicine.strip(),
                            dosage=m.dosage.strip(), duration=m.duration.strip()))
    db.flush()
    if body.refer_to:
        reason = body.refer_reason.strip() or f"Referred after: {v.diagnosis}"
        referral = new_visit(db, p, body.refer_to, reason, v.department, user.id)
        notify(db, role_ids(db, "doctor", body.refer_to) + role_ids(db, "nurse", body.refer_to),
               f"Referral from {v.department}: {p.name} ({p.pid}), token {referral.token}", "home")
    patient_user = db.scalar(select(User).where(User.patient_id == p.id))
    if patient_user:
        text = f"Your {v.department} visit is complete."
        if referral:
            text += f" You are referred to {referral.department}, token {referral.token}. No papers needed."
        notify(db, [patient_user.id], text, "home")
    audit(db, user, "completed consultation", f"{v.token} for {p.pid}")
    db.commit()
    return {"ok": True, "referral": {"department": referral.department, "token": referral.token} if referral else None}


class AvailabilityIn(BaseModel):
    available: bool


@app.post("/api/availability")
def set_availability(body: AvailabilityIn, db=Depends(get_db), user=Depends(require("doctor"))):
    user.available = body.available
    audit(db, user, "set availability", "available" if body.available else "away")
    db.commit()
    return {"available": user.available}


# ---------- appointments ----------

BOOK_AHEAD_DAYS = 14


def slot_label(slot):
    hour, minute = int(slot[:2]), slot[3:]
    return f"{(hour + 11) % 12 + 1}:{minute} {'AM' if hour < 12 else 'PM'}"


def free_slots(db, department, day):
    """Slots still open for a department on a day. Capacity per slot is the number of active doctors there."""
    capacity = max(1, db.scalar(select(func.count()).select_from(User).where(
        User.role == "doctor", User.department == department, User.active == True)))  # noqa: E712
    taken = {}
    for slot in db.scalars(select(Appointment.slot).where(Appointment.department == department, Appointment.day == day,
                                                          Appointment.status != "cancelled")):
        taken[slot] = taken.get(slot, 0) + 1
    current = now()
    cutoff = current.strftime("%H:%M") if day == current.date().isoformat() else ""
    return [s for s in SLOTS if s > cutoff and taken.get(s, 0) < capacity]


def appointment_out(db, a, with_patient=False):
    out = {"id": a.id, "department": a.department, "day": a.day, "slot": a.slot, "time": slot_label(a.slot),
           "reason": a.reason, "status": a.status}
    if with_patient:
        p = db.get(Patient, a.patient_id)
        out["patient"] = {"pid": p.pid, "name": p.name, "age": p.age}
    return out


def valid_day(day):
    try:
        date = dt.date.fromisoformat(day)
    except ValueError:
        raise HTTPException(400, "Choose a valid date")
    today = now().date()
    if not today <= date <= today + dt.timedelta(days=BOOK_AHEAD_DAYS):
        raise HTTPException(400, f"Appointments can be booked from today up to {BOOK_AHEAD_DAYS} days ahead")
    return date.isoformat()


@app.get("/api/appointments/slots")
def appointment_slots(department: str, day: str, db=Depends(get_db), _=Depends(current_user)):
    if department not in DEPARTMENTS:
        raise HTTPException(400, "Unknown department")
    day = valid_day(day)
    return [{"slot": s, "time": slot_label(s)} for s in free_slots(db, department, day)]


class AppointmentIn(BaseModel):
    department: str
    day: str
    slot: str
    reason: str = Field(default="", max_length=240)


@app.post("/api/my/appointments")
def book_appointment(body: AppointmentIn, db=Depends(get_db), user=Depends(require("patient"))):
    if body.department not in DEPARTMENTS:
        raise HTTPException(400, "Unknown department")
    if body.department == "Emergency":
        raise HTTPException(400, "Emergency does not take appointments. Come straight to the hospital")
    day = valid_day(body.day)
    if body.slot not in free_slots(db, body.department, day):
        raise HTTPException(409, "That time is no longer free. Choose another")
    clash = db.scalar(select(Appointment).where(Appointment.patient_id == user.patient_id, Appointment.day == day,
                                                Appointment.department == body.department,
                                                Appointment.status == "booked"))
    if clash:
        raise HTTPException(409, f"You already have a {body.department} appointment that day at {slot_label(clash.slot)}")
    a = Appointment(patient_id=user.patient_id, department=body.department, day=day, slot=body.slot,
                    reason=body.reason.strip())
    db.add(a)
    audit(db, user, "booked appointment", f"{body.department} {day} {body.slot}")
    db.commit()
    return appointment_out(db, a)


@app.get("/api/my/appointments")
def my_appointments(db=Depends(get_db), user=Depends(require("patient"))):
    rows = db.scalars(select(Appointment).where(Appointment.patient_id == user.patient_id,
                                                Appointment.day >= now().date().isoformat(),
                                                Appointment.status != "cancelled")
                      .order_by(Appointment.day, Appointment.slot)).all()
    return [appointment_out(db, a) for a in rows]


@app.post("/api/my/appointments/{appointment_id}/cancel")
def cancel_appointment(appointment_id: int, db=Depends(get_db), user=Depends(require("patient"))):
    a = db.get(Appointment, appointment_id)
    if not a or a.patient_id != user.patient_id:
        raise HTTPException(404, "No such appointment")
    if a.status != "booked":
        raise HTTPException(409, "This appointment can no longer be cancelled")
    a.status = "cancelled"
    audit(db, user, "cancelled appointment", f"{a.department} {a.day} {a.slot}")
    db.commit()
    return {"ok": True}


@app.get("/api/appointments")
def todays_appointments(db=Depends(get_db), _=Depends(require("receptionist", "dean", "chairman"))):
    rows = db.scalars(select(Appointment).where(Appointment.day == now().date().isoformat(),
                                                Appointment.status != "cancelled")
                      .order_by(Appointment.slot, Appointment.id)).all()
    return [appointment_out(db, a, with_patient=True) for a in rows]


@app.post("/api/appointments/{appointment_id}/checkin")
def checkin_appointment(appointment_id: int, db=Depends(get_db), user=Depends(require("receptionist"))):
    a = db.get(Appointment, appointment_id)
    if not a or a.day != now().date().isoformat():
        raise HTTPException(404, "No such appointment today")
    if a.status != "booked":
        raise HTTPException(409, "This appointment is already checked in")
    p = db.get(Patient, a.patient_id)
    if active_visit(db, p, a.department):
        raise HTTPException(409, f"{p.name} already has an active token in {a.department}")
    v = new_visit(db, p, a.department, a.reason or "Booked appointment")
    a.status, a.visit_id = "arrived", v.id
    state = live_state(db)
    ahead = ahead_of(state, v)
    notify(db, role_ids(db, "doctor", a.department) + role_ids(db, "nurse", a.department),
           f"Appointment arrived: {p.name} ({v.token})", "home")
    patient_user = db.scalar(select(User).where(User.patient_id == p.id))
    if patient_user:
        notify(db, [patient_user.id], f"You are checked in for {a.department}. Your token is {v.token}.", "home")
    audit(db, user, "checked in appointment", f"{v.token} for {p.pid}")
    db.commit()
    return {"token": v.token, "department": v.department, "ahead": ahead,
            "est_wait": estimate(state, v.department, ahead), "patient": patient_out(p)}


# ---------- beds ----------

@app.get("/api/beds")
def beds(db=Depends(get_db), _=Depends(staff_only)):
    out = []
    for b in db.scalars(select(Bed).order_by(Bed.id)).all():
        p = db.get(Patient, b.patient_id) if b.patient_id else None
        out.append({"id": b.id, "ward": b.ward, "label": b.label, "status": b.status,
                    "patient": {"pid": p.pid, "name": p.name} if p else None})
    return out


class BedIn(BaseModel):
    status: str
    pid: str = Field(default="", max_length=20)


@app.post("/api/beds/{bed_id}")
def update_bed(bed_id: int, body: BedIn, db=Depends(get_db),
               user=Depends(require("receptionist", "nurse", "dean", "chairman"))):
    bed = db.get(Bed, bed_id)
    if not bed:
        raise HTTPException(404, "No such bed")
    if body.status not in ("free", "occupied", "cleaning"):
        raise HTTPException(400, "Unknown bed status")
    if body.status == "occupied":
        p = find_patient(db, body.pid)
        other = db.scalar(select(Bed).where(Bed.patient_id == p.id, Bed.id != bed.id))
        if other:
            raise HTTPException(409, f"{p.name} is already in bed {other.label}")
        bed.patient_id = p.id
    else:
        bed.patient_id = None
    bed.status, bed.updated_at = body.status, now()
    audit(db, user, "updated bed", f"{bed.label} -> {body.status}")
    db.commit()
    return {"ok": True}


# ---------- requests and approvals ----------

def is_approver(r, user):
    if r.status != "pending" or r.approver_role != user.role:
        return False
    return r.approver_id in (None, user.id)


def request_out(db, r, user):
    creator = db.get(User, r.created_by)
    events = db.scalars(select(RequestEvent).where(RequestEvent.request_id == r.id).order_by(RequestEvent.id)).all()
    waiting_on = uname(db, r.approver_id) or r.approver_role.title()
    return {"id": r.id, "kind": r.kind, "title": r.title, "details": r.details, "patient_pid": r.patient_pid,
            "status": r.status, "created_at": iso(r.created_at), "closed_at": iso(r.closed_at),
            "creator": {"name": creator.name, "role": creator.role, "department": creator.department},
            "waiting_on": waiting_on if r.status == "pending" else "",
            "can_act": is_approver(r, user), "can_forward": is_approver(r, user) and user.role in NEXT_LEVEL,
            "forward_to": NEXT_LEVEL.get(user.role, ""),
            "trail": [{"who": uname(db, e.user_id), "action": e.action, "note": e.note, "at": iso(e.at)}
                      for e in events]}


class RequestIn(BaseModel):
    kind: str
    title: str = Field(min_length=3, max_length=160)
    details: str = Field(default="", max_length=2000)
    patient_pid: str = Field(default="", max_length=20)
    doctor_id: int | None = None


@app.post("/api/requests")
def create_request(body: RequestIn, db=Depends(get_db), user=Depends(require("nurse", "receptionist", "doctor", "dean"))):
    if body.kind not in REQUEST_KINDS:
        raise HTTPException(400, "Unknown request type")
    pid = body.patient_pid.strip().upper()
    if pid:
        find_patient(db, pid)
    r = Request(created_by=user.id, kind=body.kind, title=body.title.strip(), details=body.details.strip(),
                patient_pid=pid, approver_role=NEXT_LEVEL[user.role])
    if user.role == "nurse":
        doctor = db.get(User, body.doctor_id) if body.doctor_id else None
        if not doctor or doctor.role != "doctor":
            raise HTTPException(400, "Choose the doctor who should approve this")
        r.approver_id = doctor.id
    db.add(r)
    db.flush()
    db.add(RequestEvent(request_id=r.id, user_id=user.id, action="created"))
    targets = [r.approver_id] if r.approver_id else role_ids(db, r.approver_role)
    notify(db, targets, f"{user.name} needs your approval: {r.title}", "requests")
    audit(db, user, "raised request", r.title)
    db.commit()
    return request_out(db, r, user)


@app.get("/api/requests")
def list_requests(db=Depends(get_db), user=Depends(staff_only)):
    recent = db.scalars(select(Request).order_by(Request.id.desc()).limit(200)).all()
    handled_ids = set(db.scalars(select(RequestEvent.request_id).where(RequestEvent.user_id == user.id)))
    inbox = [r for r in recent if is_approver(r, user)]
    mine = [r for r in recent if r.created_by == user.id]
    handled = [r for r in recent if r.id in handled_ids and r.created_by != user.id and not is_approver(r, user)]
    out = {"inbox": [request_out(db, r, user) for r in inbox],
           "mine": [request_out(db, r, user) for r in mine],
           "handled": [request_out(db, r, user) for r in handled],
           "can_create": user.role in NEXT_LEVEL}
    if user.role == "chairman":
        out["all"] = [request_out(db, r, user) for r in recent[:60]]
    return out


class DecideIn(BaseModel):
    action: str
    note: str = Field(default="", max_length=400)


@app.post("/api/requests/{request_id}/decide")
def decide_request(request_id: int, body: DecideIn, db=Depends(get_db), user=Depends(staff_only)):
    r = db.get(Request, request_id)
    if not r or not is_approver(r, user):
        raise HTTPException(403, "This request is not waiting on you")
    involved = set(db.scalars(select(RequestEvent.user_id).where(RequestEvent.request_id == r.id))) - {user.id}
    if body.action in ("approve", "reject"):
        r.status = "approved" if body.action == "approve" else "rejected"
        r.closed_at = now()
        db.add(RequestEvent(request_id=r.id, user_id=user.id, action=r.status, note=body.note.strip()))
        notify(db, involved, f"{user.name} {r.status} the request: {r.title}", "requests")
    elif body.action == "forward" and user.role in NEXT_LEVEL:
        r.approver_role, r.approver_id = NEXT_LEVEL[user.role], None
        db.add(RequestEvent(request_id=r.id, user_id=user.id, action="forwarded", note=body.note.strip()))
        notify(db, role_ids(db, r.approver_role), f"{user.name} forwarded a request for your approval: {r.title}", "requests")
        notify(db, involved, f"{user.name} sent your request to the {r.approver_role}: {r.title}", "requests")
    else:
        raise HTTPException(400, "Unknown action")
    audit(db, user, f"request {body.action}", r.title)
    db.commit()
    return request_out(db, r, user)


# ---------- tasks ----------

def task_out(db, t):
    return {"id": t.id, "title": t.title, "details": t.details, "priority": t.priority, "status": t.status,
            "patient_pid": t.patient_pid, "created_at": iso(t.created_at), "done_at": iso(t.done_at),
            "assigned_by": uname(db, t.assigned_by), "assigned_to": uname(db, t.assigned_to),
            "assigned_to_id": t.assigned_to, "assigned_by_id": t.assigned_by}


class TaskIn(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    details: str = Field(default="", max_length=2000)
    assigned_to: int
    priority: str = "normal"
    patient_pid: str = Field(default="", max_length=20)


@app.post("/api/tasks")
def create_task(body: TaskIn, db=Depends(get_db), user=Depends(staff_only)):
    target = db.get(User, body.assigned_to)
    if not target or target.role not in STAFF:
        raise HTTPException(400, "Choose a staff member")
    if target.id != user.id and RANK[user.role] <= RANK[target.role]:
        raise HTTPException(403, "You can assign work only to staff who report to your role")
    if body.priority not in ("low", "normal", "urgent"):
        raise HTTPException(400, "Unknown priority")
    t = Task(title=body.title.strip(), details=body.details.strip(), assigned_by=user.id, assigned_to=target.id,
             priority=body.priority, patient_pid=body.patient_pid.strip().upper())
    db.add(t)
    if target.id != user.id:
        notify(db, [target.id], f"New task from {user.name}: {t.title}", "tasks")
    audit(db, user, "assigned task", f"{t.title} -> {target.name}")
    db.commit()
    return task_out(db, t)


@app.get("/api/tasks")
def list_tasks(db=Depends(get_db), user=Depends(staff_only)):
    order = (Task.status == "done", Task.id.desc())
    to_me = db.scalars(select(Task).where(Task.assigned_to == user.id).order_by(*order).limit(60)).all()
    by_me = db.scalars(select(Task).where(Task.assigned_by == user.id, Task.assigned_to != user.id)
                       .order_by(*order).limit(60)).all()
    assignable = db.scalars(select(User).where(User.role.in_(STAFF), User.active == True).order_by(User.name)).all()  # noqa: E712
    return {"to_me": [task_out(db, t) for t in to_me], "by_me": [task_out(db, t) for t in by_me],
            "assignable": [user_out(u) for u in assignable if u.id == user.id or RANK[u.role] < RANK[user.role]]}


class TaskStatusIn(BaseModel):
    status: str


@app.post("/api/tasks/{task_id}/status")
def set_task_status(task_id: int, body: TaskStatusIn, db=Depends(get_db), user=Depends(staff_only)):
    t = db.get(Task, task_id)
    if not t or user.id not in (t.assigned_to, t.assigned_by):
        raise HTTPException(404, "No such task")
    if body.status not in ("open", "in_progress", "done"):
        raise HTTPException(400, "Unknown status")
    t.status = body.status
    t.done_at = now() if body.status == "done" else None
    if t.assigned_by != user.id:
        notify(db, [t.assigned_by], f"{user.name} marked a task {body.status.replace('_', ' ')}: {t.title}", "tasks")
    db.commit()
    return task_out(db, t)


# ---------- messages ----------

@app.get("/api/staff")
def staff(db=Depends(get_db), _=Depends(staff_only)):
    users = db.scalars(select(User).where(User.role.in_(STAFF), User.active == True).order_by(User.name)).all()  # noqa: E712
    return [user_out(u) for u in users]


@app.get("/api/messages")
def threads(db=Depends(get_db), user=Depends(staff_only)):
    rows = db.scalars(select(Message).where(or_(Message.from_id == user.id, Message.to_id == user.id))
                      .order_by(Message.id.desc()).limit(600)).all()
    seen = {}
    for m in rows:
        other = m.to_id if m.from_id == user.id else m.from_id
        t = seen.setdefault(other, {"user_id": other, "last": m.body[:80], "at": iso(m.created_at), "unread": 0})
        if m.to_id == user.id and not m.is_read:
            t["unread"] += 1
    return list(seen.values())


@app.get("/api/messages/{other_id}")
def thread(other_id: int, db=Depends(get_db), user=Depends(staff_only)):
    rows = db.scalars(select(Message).where(or_(
        (Message.from_id == user.id) & (Message.to_id == other_id),
        (Message.from_id == other_id) & (Message.to_id == user.id))).order_by(Message.id.desc()).limit(200)).all()
    changed = False
    for m in rows:
        if m.to_id == user.id and not m.is_read:
            m.is_read = changed = True
    if changed:
        db.commit()
    return [{"id": m.id, "mine": m.from_id == user.id, "body": m.body, "at": iso(m.created_at)} for m in reversed(rows)]


class MessageIn(BaseModel):
    to: int
    body: str = Field(min_length=1, max_length=2000)


@app.post("/api/messages")
def send_message(body: MessageIn, db=Depends(get_db), user=Depends(staff_only)):
    target = db.get(User, body.to)
    if not target or target.role not in STAFF or target.id == user.id:
        raise HTTPException(400, "Choose another staff member")
    text = body.body.strip()
    if not text:
        raise HTTPException(400, "Message is empty")
    db.add(Message(from_id=user.id, to_id=target.id, body=text))
    notify(db, [target.id], f"Message from {user.name}: {text[:80]}", "messages")
    db.commit()
    return {"ok": True}


# ---------- notifications ----------

@app.get("/api/notifications")
def notifications(db=Depends(get_db), user=Depends(current_user)):
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id)
                      .order_by(Notification.id.desc()).limit(25)).all()
    unread = db.scalar(select(func.count()).select_from(Notification)
                       .where(Notification.user_id == user.id, Notification.is_read == False))  # noqa: E712
    return {"unread": unread, "items": [{"id": n.id, "text": n.text, "view": n.view, "read": n.is_read,
                                         "kind": n.kind, "ref": n.ref, "at": iso(n.created_at)} for n in rows]}


@app.post("/api/notifications/read")
def read_notifications(db=Depends(get_db), user=Depends(current_user)):
    for n in db.scalars(select(Notification).where(Notification.user_id == user.id,
                                                   Notification.is_read == False)).all():  # noqa: E712
        n.is_read = True
    db.commit()
    return {"ok": True}


@app.get("/api/badges")
def badges(db=Depends(get_db), user=Depends(staff_only)):
    def count(model, *where):
        return db.scalar(select(func.count()).select_from(model).where(*where))
    return {
        "requests": count(Request, Request.status == "pending", Request.approver_role == user.role,
                          or_(Request.approver_id.is_(None), Request.approver_id == user.id)),
        "messages": count(Message, Message.to_id == user.id, Message.is_read == False),  # noqa: E712
        "tasks": count(Task, Task.assigned_to == user.id, Task.status != "done"),
        "emergency": emergency.badge(db, user),
        "equipment": equipment.badge(db, user),
    }


# ---------- analytics, export for Cognos, admin ----------

def wait_minutes(v):
    return (v.start_at - v.checkin_at).total_seconds() / 60 if v.start_at else None


def mean(values):
    values = [x for x in values if x is not None]
    return round(sum(values) / len(values), 1) if values else 0


@app.get("/api/analytics")
def analytics(db=Depends(get_db), _=Depends(require(*LEADERS))):
    start = today_start()
    visits = db.scalars(select(Visit).where(Visit.checkin_at >= start - dt.timedelta(days=14))).all()
    todays = [v for v in visits if v.checkin_at >= start]
    beds_all = db.scalars(select(Bed)).all()
    closed = db.scalars(select(Request).where(Request.closed_at.is_not(None))).all()
    by_dept = []
    for d in DEPARTMENTS:
        rows = [v for v in visits if v.department == d]
        by_dept.append({"department": d, "visits": len(rows), "avg_wait": mean(wait_minutes(v) for v in rows),
                        "today": sum(1 for v in rows if v.checkin_at >= start)})
    daily = []
    for back in range(14, -1, -1):
        day = start - dt.timedelta(days=back)
        rows = [v for v in visits if day <= v.checkin_at < day + dt.timedelta(days=1)]
        daily.append({"date": day.date().isoformat(), "visits": len(rows),
                      "avg_wait": mean(wait_minutes(v) for v in rows)})
    hourly = []
    for hour in range(8, 20):
        rows = [v for v in visits if v.checkin_at.hour == hour]
        hourly.append({"hour": hour, "visits": len(rows), "avg_wait": mean(wait_minutes(v) for v in rows)})
    doctors = {}
    for v in visits:
        if v.doctor_id and v.status == "done":
            doctors[v.doctor_id] = doctors.get(v.doctor_id, 0) + 1
    referrals = sum(1 for v in visits if v.referred_from)
    return {
        "kpis": {
            "patients_today": len(todays),
            "waiting_now": sum(1 for v in todays if v.status == "waiting"),
            "avg_wait_today": mean(wait_minutes(v) for v in todays),
            "avg_wait_14d": mean(wait_minutes(v) for v in visits if v.checkin_at < start),
            "bed_occupancy": round(100 * sum(b.status == "occupied" for b in beds_all) / max(1, len(beds_all))),
            "beds_free": sum(b.status == "free" for b in beds_all),
            "pending_requests": db.scalar(select(func.count()).select_from(Request).where(Request.status == "pending")),
            "approval_hours": mean((r.closed_at - r.created_at).total_seconds() / 3600 for r in closed),
            "referrals": referrals,
        },
        "by_department": by_dept, "daily": daily, "hourly": hourly,
        "doctors": sorted(({"name": uname(db, k), "seen": n} for k, n in doctors.items()),
                          key=lambda x: -x["seen"]),
    }


def csv_response(name, header, rows):
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})


@app.get("/api/export/{name}")
def export(name: str, db=Depends(get_db), user=Depends(require(*LEADERS))):
    if name not in ("visits", "beds", "requests"):
        raise HTTPException(404, "Unknown export")
    audit(db, user, "exported data", name)
    db.commit()
    rows = [["" if cell is None else cell for cell in row] for row in reporting.rows(db, name)]
    return csv_response(f"caresync_{name}", reporting.header(name), rows)


@app.get("/api/analytics/sync")
def analytics_sync_status(_=Depends(require(*LEADERS))):
    return analytics_sync.status()


@app.get("/api/settings")
def get_settings(db=Depends(get_db), _=Depends(require(*LEADERS))):
    row = db.get(Setting, "cognos_url")
    return {"cognos_url": row.value if row else ""}


class SettingsIn(BaseModel):
    cognos_url: str = Field(default="", max_length=1000)


@app.post("/api/settings")
def save_settings(body: SettingsIn, db=Depends(get_db), user=Depends(require("chairman"))):
    url = body.cognos_url.strip()
    if url and not url.startswith("https://"):
        raise HTTPException(400, "The Cognos link must start with https://")
    row = db.get(Setting, "cognos_url")
    if row:
        row.value = url
    else:
        db.add(Setting(key="cognos_url", value=url))
    audit(db, user, "updated Cognos dashboard link")
    db.commit()
    return {"cognos_url": url}


@app.get("/api/audit")
def audit_log(db=Depends(get_db), _=Depends(require("chairman"))):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(150)).all()
    out = []
    for a in rows:
        u = db.get(User, a.user_id)
        out.append({"who": u.name if u else "", "role": u.role if u else "", "action": a.action,
                    "target": a.target, "at": iso(a.at)})
    return out


# ---------- staff accounts ----------

MANAGES = {"chairman": ["dean", "admin", "doctor", "nurse", "receptionist", "coordinator"],
           "dean": ["doctor", "nurse", "receptionist", "coordinator"]}
USERNAME_OK = set("abcdefghijklmnopqrstuvwxyz0123456789._-")


def set_temp_password(user):
    password = secrets.token_urlsafe(9)
    user.salt = secrets.token_hex(16)
    user.password_hash = hash_password(password, user.salt)
    return password


def managed_user(db, user_id, me):
    target = db.get(User, user_id)
    if not target or target.role not in STAFF:
        raise HTTPException(404, "No such staff account")
    if target.id == me.id or target.role not in MANAGES[me.role]:
        raise HTTPException(403, "You cannot manage this account")
    return target


@app.get("/api/admin/staff")
def admin_staff(db=Depends(get_db), me=Depends(require(*LEADERS))):
    users = db.scalars(select(User).where(User.role.in_(STAFF)).order_by(User.active.desc(), User.name)).all()
    return {"roles": MANAGES[me.role],
            "staff": [{**user_out(u), "username": u.username, "active": u.active,
                       "can_manage": u.id != me.id and u.role in MANAGES[me.role]} for u in users]}


class StaffIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=3, max_length=32)
    role: str
    department: str = ""


@app.post("/api/admin/staff")
def add_staff(body: StaffIn, db=Depends(get_db), me=Depends(require(*LEADERS))):
    username = body.username.strip().lower()
    if body.role not in MANAGES[me.role]:
        raise HTTPException(403, "You cannot create an account with that role")
    if not set(username) <= USERNAME_OK:
        raise HTTPException(400, "Usernames can use letters, numbers, dots, dashes and underscores")
    if db.scalar(select(User).where(func.lower(User.username) == username)):
        raise HTTPException(409, "That username is already taken")
    department = body.department if body.role in ("doctor", "nurse") else None
    if body.role in ("doctor", "nurse") and department not in DEPARTMENTS:
        raise HTTPException(400, "Choose a department for doctors and nurses")
    user = User(username=username, name=body.name.strip(), role=body.role, department=department,
                password_hash="", salt="")
    password = set_temp_password(user)
    db.add(user)
    audit(db, me, "created staff account", f"{username} ({body.role})")
    db.commit()
    return {"user": {**user_out(user), "username": user.username}, "password": password}


class ActiveIn(BaseModel):
    active: bool


@app.post("/api/admin/staff/{user_id}/active")
def set_staff_active(user_id: int, body: ActiveIn, db=Depends(get_db), me=Depends(require(*LEADERS))):
    target = managed_user(db, user_id, me)
    target.active = body.active
    if not body.active:  # sign the person out everywhere
        for session in db.scalars(select(AuthSession).where(AuthSession.user_id == target.id)).all():
            db.delete(session)
    audit(db, me, "enabled staff account" if body.active else "disabled staff account", target.username)
    db.commit()
    return {"ok": True}


@app.post("/api/admin/staff/{user_id}/reset-password")
def reset_staff_password(user_id: int, db=Depends(get_db), me=Depends(require(*LEADERS))):
    target = managed_user(db, user_id, me)
    password = set_temp_password(target)
    for session in db.scalars(select(AuthSession).where(AuthSession.user_id == target.id)).all():
        db.delete(session)
    audit(db, me, "reset staff password", target.username)
    db.commit()
    return {"user": {**user_out(target), "username": target.username}, "password": password}


# ---------- emergencies, equipment, live updates ----------

from . import emergency, equipment, live  # noqa: E402  (these modules use the helpers defined above)

app.include_router(emergency.router)
app.include_router(equipment.router)
app.include_router(live.router)


# ---------- front end ----------

@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
