"""Critical emergency alerts: registration, notification, acknowledgement, escalation and status tracking.

This coordinates people. It never decides how ill a patient is: priority and triage level are entered by staff
following the hospital's own triage protocol.
"""
import datetime as dt
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from .db import EmergencyAlert, EmergencyEvent, Notification, Patient, Setting, User, Visit, get_db, now
from .main import (CLINICAL, PRIORITY_RANK, audit, bump, current_user, find_patient, iso, make_pid, make_user,
                   new_visit, notify, patient_out, require, uname)

router = APIRouter(prefix="/api/emergencies")

# Ordered workflow. An alert only moves forward; every move is stored with who made it and when.
STATUSES = ["alert_created", "notification_sent", "acknowledged", "response_started", "under_care",
            "transferred", "admitted", "closed"]
STATUS_LABEL = {"alert_created": "Alert created", "notification_sent": "Notification sent", "acknowledged": "Acknowledged",
                "response_started": "Clinical response started", "under_care": "Patient under emergency care",
                "transferred": "Transferred", "admitted": "Admitted", "closed": "Closed"}
OPEN = STATUSES[:-1]
AWAITING_ACK = ("alert_created", "notification_sent")
TYPES = ["Road traffic accident", "Fall or severe injury", "Chest pain / cardiac", "Breathing difficulty",
         "Stroke symptoms", "Unconscious / collapse", "Severe bleeding", "Burns", "Poisoning / overdose",
         "Obstetric emergency", "Seizure", "Other"]
TRIAGE_PRIORITIES = ["critical", "urgent", "normal"]

# Who can do what. Enforced here, not by hiding buttons.
RAISE = {"receptionist", "doctor", "nurse", "dean", "chairman"}
VIEW = {"receptionist", "doctor", "nurse", "dean", "chairman", "admin"}
FULL_DETAILS = CLINICAL | {"receptionist"}  # see the patient's name and the clinical description
CLINICAL_UPDATE = {"doctor", "nurse", "dean", "chairman"}  # status and triage priority
ASSIGN = {"doctor", "receptionist", "dean", "chairman", "admin"}
POLICY_EDIT = {"chairman", "admin"}
REPORT = {"dean", "chairman", "admin"}

POLICY_DEFAULTS = {"ack_seconds": 120, "repeat_seconds": 120, "max_level": 3, "retry_seconds": 30, "max_attempts": 3}
POLICY_LIMITS = {"ack_seconds": (15, 3600), "repeat_seconds": (15, 3600), "max_level": (0, 6),
                 "retry_seconds": (5, 600), "max_attempts": (1, 10)}


def policy(db):
    out = dict(POLICY_DEFAULTS)
    for key in out:
        row = db.get(Setting, "emergency_" + key)
        if row and row.value.strip().isdigit():
            out[key] = int(row.value)
    return out


def recipients(db, alert):
    """Chairman, dean, administrator, reception, the assigned doctor and the emergency team."""
    ids = set()
    for role in ("chairman", "dean", "admin", "receptionist"):
        ids.update(active_ids(db, role))
    team = alert.team or "Emergency"
    ids.update(active_ids(db, "doctor", team))
    ids.update(active_ids(db, "nurse", team))
    if alert.assigned_doctor_id:
        ids.add(alert.assigned_doctor_id)
    return ids


def active_ids(db, role, department=None):
    q = select(User.id).where(User.role == role, User.active == True)  # noqa: E712
    if department:
        q = q.where(User.department == department)
    return list(db.scalars(q))


def alert_text(db, a, role, heading="CRITICAL EMERGENCY ALERT"):
    p = db.get(Patient, a.patient_id)
    who = f"{p.name} ({p.pid})" if role in FULL_DETAILS else p.pid
    doctor = uname(db, a.assigned_doctor_id) or f"{a.team} team"
    if a.priority != "critical" and heading == "CRITICAL EMERGENCY ALERT":
        heading = "URGENT EMERGENCY ALERT"
    parts = [heading, a.ern, who, a.emergency_type, a.priority, f"arrived {a.arrival_at.strftime('%H:%M')}",
             doctor, a.location or "location not set", STATUS_LABEL[a.status]]
    return " · ".join(parts)


def send(db, a, user_ids, heading="CRITICAL EMERGENCY ALERT"):
    """One persisted notification per person, worded for what their role may see."""
    roles = dict(db.execute(select(User.id, User.role).where(User.id.in_(list(user_ids)))).all()) if user_ids else {}
    for uid, role in roles.items():
        notify(db, [uid], alert_text(db, a, role, heading), "emergency", kind="emergency", ref=a.id)
    bump(db, "emergency")


def event(db, a, user, action, frm="", to="", note=""):
    db.add(EmergencyEvent(alert_id=a.id, user_id=user.id if user else None, action=action, from_value=frm,
                          to_value=to, note=note[:400]))
    a.updated_at = now()
    bump(db, "emergency")


def set_status(db, a, user, status, note=""):
    if status == a.status:
        return
    event(db, a, user, "status", a.status, status, note)
    a.status = status
    if status == "closed":
        a.closed_at = now()


def alert_out(db, a, user, detail=False):
    p = db.get(Patient, a.patient_id)
    full = user.role in FULL_DETAILS
    current = now()
    end = a.closed_at or current
    out = {
        "id": a.id, "ern": a.ern, "priority": a.priority, "triage_level": a.triage_level,
        "emergency_type": a.emergency_type, "location": a.location, "team": a.team,
        "status": a.status, "status_label": STATUS_LABEL[a.status], "arrival_at": iso(a.arrival_at),
        "created_at": iso(a.created_at), "received_at": iso(a.received_at), "acknowledged_at": iso(a.acknowledged_at),
        "acknowledged_by": uname(db, a.acknowledged_by), "closed_at": iso(a.closed_at),
        "escalation_level": a.escalation_level, "updated_at": iso(a.updated_at),
        "assigned_doctor": uname(db, a.assigned_doctor_id), "assigned_doctor_id": a.assigned_doctor_id,
        "created_by": uname(db, a.created_by),
        "elapsed_minutes": max(0, int((end - a.arrival_at).total_seconds() // 60)),
        "ack_seconds": int((a.acknowledged_at - a.created_at).total_seconds()) if a.acknowledged_at else None,
        "patient": {"pid": p.pid, "name": p.name if full else "Restricted",
                    **({"age": p.age, "gender": p.gender, "allergies": p.allergies, "blood_group": p.blood_group}
                       if full else {})},
        "description": a.description if full else "",
        "restricted": not full,
        "is_assigned": a.assigned_doctor_id == user.id,
        "can_ack": can_ack(db, a, user),
        "can_update": user.role in CLINICAL_UPDATE and a.status != "closed",
        "can_assign": user.role in ASSIGN and a.status != "closed",
        "visit_id": a.visit_id,
    }
    if detail:
        events = db.scalars(select(EmergencyEvent).where(EmergencyEvent.alert_id == a.id)
                            .order_by(EmergencyEvent.id)).all()
        out["events"] = [{"who": uname(db, e.user_id) or "System", "action": e.action, "from": e.from_value,
                          "to": e.to_value, "note": e.note, "at": iso(e.at)} for e in events]
        notes = db.scalars(select(Notification).where(Notification.kind == "emergency",
                                                      Notification.ref == str(a.id))
                           .order_by(Notification.id)).all()
        users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({n.user_id for n in notes})))}
        out["deliveries"] = [{"who": users[n.user_id].name if n.user_id in users else "",
                              "role": users[n.user_id].role if n.user_id in users else "",
                              "sent_at": iso(n.created_at), "delivered_at": iso(n.delivered_at),
                              "acked_at": iso(n.acked_at), "attempts": n.attempts,
                              "escalation": n.text.startswith("ESCALATED")} for n in notes]
    return out


def can_ack(db, a, user):
    if a.status not in AWAITING_ACK:
        return False
    if a.assigned_doctor_id:
        return a.assigned_doctor_id == user.id
    return user.role == "doctor" and user.department == (a.team or "Emergency")


def get_alert(db, alert_id, user):
    if user.role not in VIEW:
        raise HTTPException(403, "Your role does not have access to emergency alerts")
    a = db.get(EmergencyAlert, alert_id)
    if not a:
        raise HTTPException(404, "No such emergency alert")
    return a


class NewPatientIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    age: int = Field(ge=0, le=120)
    gender: str = Field(max_length=12)
    phone: str = Field(default="", max_length=20)


class AlertIn(BaseModel):
    idem_key: str = Field(min_length=8, max_length=64)
    pid: str = Field(default="", max_length=20)
    new_patient: NewPatientIn | None = None
    emergency_type: str = Field(max_length=60)
    description: str = Field(default="", max_length=600)
    priority: str = "critical"
    location: str = Field(default="", max_length=60)
    team: str = Field(default="Emergency", max_length=60)
    assigned_doctor_id: int | None = None
    arrival_at: str = ""


def pick_doctor(db, team):
    """Default assignment: an available doctor on the emergency team. Staff can change it at any time."""
    docs = db.scalars(select(User).where(User.role == "doctor", User.department == team, User.active == True)  # noqa: E712
                      .order_by(User.available.desc(), User.id)).all()
    return docs[0].id if docs else None


@router.post("")
def raise_alert(body: AlertIn, db=Depends(get_db), user=Depends(require(*RAISE))):
    from .main import DEPARTMENTS
    existing = db.scalar(select(EmergencyAlert).where(EmergencyAlert.idem_key == body.idem_key))
    if existing:  # the same form sent twice (double click, network retry): hand back the first alert
        return {"alert": alert_out(db, existing, user), "duplicate": True, "pin": None}
    if body.emergency_type not in TYPES:
        raise HTTPException(400, "Choose an emergency type")
    if body.priority not in ("critical", "urgent"):
        raise HTTPException(400, "An emergency alert is critical or urgent")
    if body.team not in DEPARTMENTS:
        raise HTTPException(400, "Unknown team")
    arrival = now()
    if body.arrival_at:
        try:
            arrival = dt.datetime.fromisoformat(body.arrival_at)
            if arrival.tzinfo:  # the browser sends its own offset; store it as server-local time like every other timestamp
                arrival = arrival.astimezone()
            arrival = arrival.replace(microsecond=0, tzinfo=None)
        except ValueError:
            raise HTTPException(400, "Arrival time is not valid")
        if arrival > now() + dt.timedelta(minutes=5) or arrival < now() - dt.timedelta(hours=24):
            raise HTTPException(400, "Arrival time must be within the last 24 hours")
    doctor_id = body.assigned_doctor_id
    if doctor_id:
        doc = db.get(User, doctor_id)
        if not doc or doc.role != "doctor" or not doc.active:
            raise HTTPException(400, "Choose an active doctor")
    else:
        doctor_id = pick_doctor(db, body.team)
    pin = None
    if body.pid.strip():
        p = find_patient(db, body.pid)
    elif body.new_patient:
        if user.role != "receptionist" and user.role not in CLINICAL:
            raise HTTPException(403, "You cannot register patients")
        n = body.new_patient
        p = Patient(name=n.name.strip(), age=n.age, gender=n.gender, phone=n.phone.strip())
        db.add(p)
        db.flush()
        p.pid = make_pid(p)
        pin = f"{secrets.randbelow(900000) + 100000}"
        db.add(make_user(p.pid, pin, p.name, "patient", patient_id=p.id))
        audit(db, user, "registered patient", p.pid + " (emergency)")
    else:
        raise HTTPException(400, "Choose the patient or enter their details")
    open_alert = db.scalar(select(EmergencyAlert).where(EmergencyAlert.patient_id == p.id,
                                                        EmergencyAlert.status.in_(OPEN)))
    if open_alert:
        raise HTTPException(409, f"{p.name} already has an open emergency alert ({open_alert.ern})")

    visit = db.scalar(select(Visit).where(Visit.patient_id == p.id, Visit.department == body.team,
                                          Visit.status.in_(["waiting", "in_consultation"]),
                                          Visit.checkin_at >= now().replace(hour=0, minute=0, second=0)))
    if visit:
        visit.priority = body.priority
    else:
        visit = new_visit(db, p, body.team, f"{body.emergency_type}: {body.description.strip()}"[:240],
                          priority=body.priority)
    a = EmergencyAlert(ern="tmp-" + secrets.token_hex(8), idem_key=body.idem_key, patient_id=p.id, visit_id=visit.id,
                       emergency_type=body.emergency_type, description=body.description.strip(),
                       priority=body.priority, location=body.location.strip(), team=body.team,
                       assigned_doctor_id=doctor_id, arrival_at=arrival, created_by=user.id)
    db.add(a)
    try:
        db.flush()
    except IntegrityError:  # a retry of the same form won the race
        db.rollback()
        existing = db.scalar(select(EmergencyAlert).where(EmergencyAlert.idem_key == body.idem_key))
        return {"alert": alert_out(db, existing, user), "duplicate": True, "pin": None}
    a.ern = f"ER-{a.created_at.year}-{a.id:04d}"
    event(db, a, user, "created", "", "alert_created", f"{body.priority} · {body.emergency_type}")
    if doctor_id:
        event(db, a, user, "assigned", "", uname(db, doctor_id))
    set_status(db, a, None, "notification_sent", "Saved notifications for the alert recipients")
    send(db, a, recipients(db, a))
    audit(db, user, "raised emergency alert", f"{a.ern} for {p.pid}")
    db.commit()
    return {"alert": alert_out(db, a, user), "duplicate": False, "pin": pin, "patient": patient_out(p)}


def visible_alerts(db, scope):
    q = select(EmergencyAlert)
    if scope == "open":
        q = q.where(EmergencyAlert.status.in_(OPEN))
    else:
        q = q.order_by(EmergencyAlert.id.desc()).limit(200)
    rows = db.scalars(q).all()
    if scope == "open":
        rows.sort(key=lambda a: (PRIORITY_RANK.get(a.priority, 2), a.arrival_at, a.id))
    return rows


@router.get("")
def list_alerts(scope: str = "open", db=Depends(get_db), user=Depends(current_user)):
    if user.role not in VIEW:
        raise HTTPException(403, "Your role does not have access to emergency alerts")
    return {"alerts": [alert_out(db, a, user) for a in visible_alerts(db, scope)],
            "types": TYPES, "statuses": [{"id": s, "label": STATUS_LABEL[s]} for s in STATUSES],
            "policy": policy(db), "can_raise": user.role in RAISE, "can_policy": user.role in POLICY_EDIT,
            "can_report": user.role in REPORT}


@router.get("/active")
def active_for_me(db=Depends(get_db), user=Depends(current_user)):
    """What the banner shows: open alerts this person must act on or has not yet dismissed."""
    if user.role not in VIEW:
        return {"alerts": []}
    open_rows = visible_alerts(db, "open")
    pending = set(db.scalars(select(Notification.ref).where(
        Notification.user_id == user.id, Notification.kind == "emergency", Notification.acked_at.is_(None))))
    out = []
    for a in open_rows:
        mine = can_ack(db, a, user) or (a.assigned_doctor_id == user.id and a.status in AWAITING_ACK)
        if mine or str(a.id) in pending:
            item = alert_out(db, a, user)
            item["must_ack"] = mine
            out.append(item)
    return {"alerts": out}


@router.get("/report")
def ack_report(db=Depends(get_db), user=Depends(require(*REPORT))):
    rows = db.scalars(select(EmergencyAlert).order_by(EmergencyAlert.id.desc()).limit(200)).all()
    pol = policy(db)
    acked = [a for a in rows if a.acknowledged_at]
    secs = [(a.acknowledged_at - a.created_at).total_seconds() for a in acked]
    return {
        "total": len(rows), "open": sum(1 for a in rows if a.status != "closed"),
        "acknowledged": len(acked), "escalated": sum(1 for a in rows if a.escalation_level),
        "avg_ack_seconds": round(sum(secs) / len(secs)) if secs else None,
        "within_policy": sum(1 for s in secs if s <= pol["ack_seconds"]),
        "policy": pol,
        "alerts": [alert_out(db, a, user) for a in rows],
    }


@router.get("/{alert_id}")
def alert_detail(alert_id: int, db=Depends(get_db), user=Depends(current_user)):
    a = get_alert(db, alert_id, user)
    if user.role in FULL_DETAILS:
        p = db.get(Patient, a.patient_id)
        audit(db, user, "viewed emergency record", f"{a.ern} {p.pid}")
        db.commit()
    return alert_out(db, a, user, detail=True)


@router.post("/{alert_id}/received")
def mark_received(alert_id: int, db=Depends(get_db), user=Depends(current_user)):
    """Called by the recipient's app after it has shown the alert. Delivery is recorded only here."""
    a = get_alert(db, alert_id, user)
    stamp = now()
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.kind == "emergency",
                                          Notification.ref == str(a.id), Notification.delivered_at.is_(None))
               .values(delivered_at=stamp).execution_options(synchronize_session=False))
    if a.assigned_doctor_id == user.id and not a.received_at:
        a.received_at = stamp
        event(db, a, user, "received", "", "", "Alert shown on the assigned doctor's screen")
    db.commit()
    return {"ok": True}


class NoteIn(BaseModel):
    note: str = Field(default="", max_length=400)


@router.post("/{alert_id}/ack")
def acknowledge(alert_id: int, body: NoteIn, db=Depends(get_db), user=Depends(current_user)):
    a = get_alert(db, alert_id, user)
    stamp = now()
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.kind == "emergency",
                                          Notification.ref == str(a.id))
               .values(acked_at=func.coalesce(Notification.acked_at, stamp),
                       delivered_at=func.coalesce(Notification.delivered_at, stamp))
               .execution_options(synchronize_session=False))
    if can_ack(db, a, user):
        a.acknowledged_at, a.acknowledged_by = stamp, user.id
        if not a.received_at and a.assigned_doctor_id == user.id:
            a.received_at = stamp
        if not a.assigned_doctor_id:
            a.assigned_doctor_id = user.id
            event(db, a, user, "assigned", "", user.name, "Took the alert")
        set_status(db, a, user, "acknowledged", body.note.strip())
        others = recipients(db, a) - {user.id}
        notify(db, others, f"{a.ern} acknowledged by {user.name} at {stamp.strftime('%H:%M')}", "emergency",
               kind="emergency_info", ref=a.id)
        audit(db, user, "acknowledged emergency", a.ern)
        result = "acknowledged"
    elif a.status in OPEN:
        event(db, a, user, "seen", "", "", "Notification acknowledged")
        result = "seen"
    else:
        result = "seen"
    bump(db, user.id, "emergency")
    db.commit()
    return {"result": result, "alert": alert_out(db, a, user)}


class StatusIn(BaseModel):
    status: str
    note: str = Field(default="", max_length=400)


@router.post("/{alert_id}/status")
def update_status(alert_id: int, body: StatusIn, db=Depends(get_db), user=Depends(current_user)):
    a = get_alert(db, alert_id, user)
    if user.role not in CLINICAL_UPDATE:
        raise HTTPException(403, "Only the clinical team can change the emergency status")
    if body.status not in STATUSES[2:]:
        raise HTTPException(400, "Unknown status")
    if a.status == "closed":
        raise HTTPException(409, "This emergency is already closed")
    if STATUSES.index(body.status) <= STATUSES.index(a.status):
        raise HTTPException(409, f"The emergency is already at '{STATUS_LABEL[a.status]}'")
    if body.status == "closed" and not body.note.strip():
        raise HTTPException(400, "Add a closing note")
    if not a.acknowledged_at:  # someone on the team responded before the assigned doctor acknowledged
        a.acknowledged_at, a.acknowledged_by = now(), user.id
    set_status(db, a, user, body.status, body.note.strip())
    if body.status == "closed":
        v = db.get(Visit, a.visit_id) if a.visit_id else None
        if v and v.status in ("waiting", "in_consultation"):
            v.status, v.end_at = "done", now()
            v.start_at = v.start_at or a.acknowledged_at
            v.diagnosis = v.diagnosis or "Emergency care, see emergency record " + a.ern
            v.notes = (v.notes + "\n" if v.notes else "") + "Closed through the emergency workflow: " + body.note.strip()
    notify(db, recipients(db, a) - {user.id}, f"{a.ern} is now {STATUS_LABEL[body.status]} ({user.name})",
           "emergency", kind="emergency_info", ref=a.id)
    audit(db, user, "emergency status", f"{a.ern} -> {body.status}")
    db.commit()
    return alert_out(db, a, user)


class TriageIn(BaseModel):
    priority: str
    triage_level: str = Field(default="", max_length=60)
    note: str = Field(default="", max_length=400)


@router.post("/{alert_id}/triage")
def update_triage(alert_id: int, body: TriageIn, db=Depends(get_db), user=Depends(current_user)):
    """The clinical team records the priority from the hospital's triage protocol. Nothing here infers it."""
    a = get_alert(db, alert_id, user)
    if user.role not in CLINICAL_UPDATE:
        raise HTTPException(403, "Only the clinical team can change triage priority")
    if body.priority not in TRIAGE_PRIORITIES:
        raise HTTPException(400, "Unknown priority")
    if a.status == "closed":
        raise HTTPException(409, "This emergency is already closed")
    if not body.note.strip():
        raise HTTPException(400, "Give the reason for the triage decision")
    before = f"{a.priority}{' / ' + a.triage_level if a.triage_level else ''}"
    a.priority, a.triage_level = body.priority, body.triage_level.strip()
    after = f"{a.priority}{' / ' + a.triage_level if a.triage_level else ''}"
    event(db, a, user, "triage", before, after, body.note.strip())
    v = db.get(Visit, a.visit_id) if a.visit_id else None
    if v and v.status != "done":
        v.priority = body.priority
    audit(db, user, "updated triage priority", f"{a.ern}: {before} -> {after}")
    db.commit()
    return alert_out(db, a, user)


class AssignIn(BaseModel):
    doctor_id: int
    note: str = Field(default="", max_length=400)


@router.post("/{alert_id}/assign")
def assign(alert_id: int, body: AssignIn, db=Depends(get_db), user=Depends(current_user)):
    a = get_alert(db, alert_id, user)
    if user.role not in ASSIGN:
        raise HTTPException(403, "Your role cannot reassign emergencies")
    if a.status == "closed":
        raise HTTPException(409, "This emergency is already closed")
    doc = db.get(User, body.doctor_id)
    if not doc or doc.role != "doctor" or not doc.active:
        raise HTTPException(400, "Choose an active doctor")
    if doc.id == a.assigned_doctor_id:
        raise HTTPException(409, f"{doc.name} is already assigned")
    before = uname(db, a.assigned_doctor_id)
    a.assigned_doctor_id = doc.id
    a.received_at = None
    event(db, a, user, "assigned", before, doc.name, body.note.strip() or "Backup clinician assigned")
    if a.status == "acknowledged":  # the new clinician has to acknowledge it themselves
        a.acknowledged_at = a.acknowledged_by = None
        set_status(db, a, user, "notification_sent", "Waiting for the newly assigned clinician")
    a.escalation_level, a.last_escalated_at = 0, None
    send(db, a, {doc.id}, "CRITICAL EMERGENCY ALERT · ASSIGNED TO YOU")
    audit(db, user, "assigned emergency", f"{a.ern} -> {doc.name}")
    db.commit()
    return alert_out(db, a, user)


@router.post("/{alert_id}/escalate")
def escalate_now(alert_id: int, body: NoteIn, db=Depends(get_db), user=Depends(current_user)):
    a = get_alert(db, alert_id, user)
    if user.role not in ASSIGN:
        raise HTTPException(403, "Your role cannot escalate emergencies")
    if a.status == "closed":
        raise HTTPException(409, "This emergency is already closed")
    escalate(db, a, user, body.note.strip() or "Escalated by staff")
    db.commit()
    return alert_out(db, a, user)


def escalation_targets(db, a, level):
    ids = set(active_ids(db, "doctor", a.team or "Emergency")) | set(active_ids(db, "dean")) | set(active_ids(db, "admin"))
    ids |= set(active_ids(db, "receptionist"))
    if level >= 2:
        ids |= set(db.scalars(select(User.id).where(User.role == "doctor", User.active == True,  # noqa: E712
                                                    User.available == True)))  # noqa: E712
        ids |= set(active_ids(db, "chairman"))
    if a.assigned_doctor_id:
        ids.add(a.assigned_doctor_id)
    return ids


def escalate(db, a, user, note):
    a.escalation_level += 1
    a.last_escalated_at = now()
    event(db, a, user, "escalated", str(a.escalation_level - 1), str(a.escalation_level), note)
    send(db, a, escalation_targets(db, a, a.escalation_level), f"ESCALATED (level {a.escalation_level}) EMERGENCY ALERT")


class PolicyIn(BaseModel):
    ack_seconds: int
    repeat_seconds: int
    max_level: int
    retry_seconds: int
    max_attempts: int


@router.get("/policy/current")
def get_policy(db=Depends(get_db), user=Depends(require(*VIEW))):
    return policy(db)


@router.post("/policy/current")
def save_policy(body: PolicyIn, db=Depends(get_db), user=Depends(require(*POLICY_EDIT))):
    values = body.model_dump()
    for key, value in values.items():
        lo, hi = POLICY_LIMITS[key]
        if not lo <= value <= hi:
            raise HTTPException(400, f"{key.replace('_', ' ')} must be between {lo} and {hi}")
        row = db.get(Setting, "emergency_" + key)
        if row:
            row.value = str(value)
        else:
            db.add(Setting(key="emergency_" + key, value=str(value)))
    audit(db, user, "updated emergency response policy", ", ".join(f"{k}={v}" for k, v in values.items()))
    db.commit()
    return policy(db)


def run_checks(db):
    """Background pass: escalate unacknowledged alerts and retry undelivered notifications."""
    pol = policy(db)
    current = now()
    changed = False
    for a in db.scalars(select(EmergencyAlert).where(EmergencyAlert.status.in_(AWAITING_ACK))).all():
        if a.escalation_level >= pol["max_level"]:
            continue
        since = a.last_escalated_at or a.created_at
        wait = pol["ack_seconds"] if a.escalation_level == 0 else pol["repeat_seconds"]
        if (current - since).total_seconds() >= wait:
            escalate(db, a, None, f"Not acknowledged within {wait} seconds (response policy)")
            changed = True
    open_ids = [str(i) for i in db.scalars(select(EmergencyAlert.id).where(EmergencyAlert.status.in_(OPEN)))]
    if open_ids:
        for n in db.scalars(select(Notification).where(Notification.kind == "emergency", Notification.ref.in_(open_ids),
                                                       Notification.delivered_at.is_(None),
                                                       Notification.attempts < pol["max_attempts"])).all():
            if (current - n.created_at).total_seconds() >= pol["retry_seconds"] * n.attempts:
                n.attempts += 1  # push it to the person's open app again
                bump(db, n.user_id, "emergency")
                changed = True
    if changed:
        db.commit()


def badge(db, user):
    if user.role not in VIEW:
        return 0
    return db.scalar(select(func.count()).select_from(EmergencyAlert).where(EmergencyAlert.status.in_(OPEN))) or 0
