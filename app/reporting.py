"""Reporting tables: the de-identified data that leaves the app, as CSV downloads and as the live analytics copy.

No names, phone numbers or logins are included. Patients appear only by their patient ID.
"""
from sqlalchemy import select

from .db import Appointment, Bed, Patient, Request, User, Visit

# table -> [(column, PostgreSQL type)]
TABLES = {
    "visits": [("visit_id", "integer primary key"), ("patient_id", "varchar(20)"), ("age", "integer"),
               ("gender", "varchar(12)"), ("department", "varchar(60)"), ("doctor", "varchar(120)"),
               ("status", "varchar(20)"), ("visit_date", "date"), ("weekday", "varchar(12)"),
               ("checkin_hour", "integer"), ("wait_minutes", "numeric(8,1)"), ("consult_minutes", "numeric(8,1)"),
               ("diagnosis", "varchar(240)"), ("referred_from", "varchar(60)"), ("is_referral", "varchar(3)")],
    "beds": [("ward", "varchar(40)"), ("bed", "varchar(12) primary key"), ("status", "varchar(12)")],
    "requests": [("request_id", "integer primary key"), ("type", "varchar(40)"), ("raised_by_role", "varchar(20)"),
                 ("department", "varchar(60)"), ("status", "varchar(12)"), ("created_date", "date"),
                 ("hours_to_close", "numeric(8,2)")],
    "appointments": [("appointment_id", "integer primary key"), ("department", "varchar(60)"),
                     ("appointment_date", "date"), ("slot", "varchar(5)"), ("status", "varchar(12)")],
}


def header(table):
    return [name for name, _ in TABLES[table]]


def visits(db):
    doctors = {u.id: u.name for u in db.scalars(select(User).where(User.role == "doctor"))}
    patients = {p.id: p for p in db.scalars(select(Patient))}
    rows = []
    for v in db.scalars(select(Visit).order_by(Visit.id)):
        p = patients[v.patient_id]
        wait = (v.start_at - v.checkin_at).total_seconds() / 60 if v.start_at else None
        consult = (v.end_at - v.start_at).total_seconds() / 60 if v.end_at and v.start_at else None
        rows.append([v.id, p.pid, p.age, p.gender, v.department, doctors.get(v.doctor_id, ""), v.status,
                     v.checkin_at.date().isoformat(), v.checkin_at.strftime("%A"), v.checkin_at.hour,
                     None if wait is None else round(wait, 1), None if consult is None else round(consult, 1),
                     v.diagnosis, v.referred_from, "Yes" if v.referred_from else "No"])
    return rows


def beds(db):
    return [[b.ward, b.label, b.status] for b in db.scalars(select(Bed).order_by(Bed.id))]


def requests(db):
    users = {u.id: u for u in db.scalars(select(User))}
    rows = []
    for r in db.scalars(select(Request).order_by(Request.id)):
        creator = users[r.created_by]
        hours = round((r.closed_at - r.created_at).total_seconds() / 3600, 2) if r.closed_at else None
        rows.append([r.id, r.kind, creator.role, creator.department or "", r.status,
                     r.created_at.date().isoformat(), hours])
    return rows


def appointments(db):
    return [[a.id, a.department, a.day, a.slot, a.status] for a in db.scalars(select(Appointment).order_by(Appointment.id))]


BUILDERS = {"visits": visits, "beds": beds, "requests": requests, "appointments": appointments}


def rows(db, table):
    return BUILDERS[table](db)
