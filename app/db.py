"""Database models. Runs on SQLite by default; set DATABASE_URL to point at Db2 on Cloud."""
import datetime as dt
import os
from pathlib import Path

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

ROOT = Path(__file__).resolve().parent.parent


def load_env():
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()

DATABASE_URL = os.environ.get("DATABASE_URL") or f"sqlite:///{(ROOT / 'caresync.db').as_posix()}"
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def now():
    return dt.datetime.now().replace(microsecond=0)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    salt: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), index=True)
    department: Mapped[str | None] = mapped_column(String(60), nullable=True)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    patient_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Session(Base):
    __tablename__ = "sessions"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pid: Mapped[str | None] = mapped_column(String(20), unique=True, index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    age: Mapped[int] = mapped_column(Integer)
    gender: Mapped[str] = mapped_column(String(12))
    phone: Mapped[str] = mapped_column(String(20), default="")
    blood_group: Mapped[str] = mapped_column(String(6), default="")
    allergies: Mapped[str] = mapped_column(String(240), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class Visit(Base):
    __tablename__ = "visits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    department: Mapped[str] = mapped_column(String(60), index=True)
    doctor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(20), index=True, default="waiting")
    checkin_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now, index=True)
    start_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    end_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    complaint: Mapped[str] = mapped_column(String(240), default="")
    diagnosis: Mapped[str] = mapped_column(String(240), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    bp: Mapped[str] = mapped_column(String(12), default="")
    temp: Mapped[str] = mapped_column(String(8), default="")
    pulse: Mapped[str] = mapped_column(String(8), default="")
    spo2: Mapped[str] = mapped_column(String(8), default="")
    vitals_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    referred_from: Mapped[str] = mapped_column(String(60), default="")
    referred_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Prescription(Base):
    __tablename__ = "prescriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visits.id"), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    doctor_id: Mapped[int] = mapped_column(Integer)
    medicine: Mapped[str] = mapped_column(String(120))
    dosage: Mapped[str] = mapped_column(String(60), default="")
    duration: Mapped[str] = mapped_column(String(60), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class Bed(Base):
    __tablename__ = "beds"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ward: Mapped[str] = mapped_column(String(40), index=True)
    label: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(12), default="free")
    patient_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class Request(Base):
    __tablename__ = "requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(160))
    details: Mapped[str] = mapped_column(Text, default="")
    patient_pid: Mapped[str] = mapped_column(String(20), default="")
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    approver_role: Mapped[str] = mapped_column(String(20))
    approver_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class RequestEvent(Base):
    __tablename__ = "request_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(String(400), default="")
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    details: Mapped[str] = mapped_column(Text, default="")
    assigned_by: Mapped[int] = mapped_column(Integer, index=True)
    assigned_to: Mapped[int] = mapped_column(Integer, index=True)
    priority: Mapped[str] = mapped_column(String(10), default="normal")
    status: Mapped[str] = mapped_column(String(14), default="open")
    patient_pid: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    done_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_id: Mapped[int] = mapped_column(Integer, index=True)
    to_id: Mapped[int] = mapped_column(Integer, index=True)
    body: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    text: Mapped[str] = mapped_column(String(300))
    view: Mapped[str] = mapped_column(String(30), default="")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(60))
    target: Mapped[str] = mapped_column(String(160), default="")
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    department: Mapped[str] = mapped_column(String(60), index=True)
    day: Mapped[str] = mapped_column(String(10), index=True)
    slot: Mapped[str] = mapped_column(String(5))
    reason: Mapped[str] = mapped_column(String(240), default="")
    status: Mapped[str] = mapped_column(String(12), default="booked", index=True)
    visit_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


def migrate():
    """Add columns introduced after a database was first created."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if inspector.has_table("users") and "active" not in {c["name"] for c in inspector.get_columns("users")}:
        with engine.begin() as con:
            con.execute(text("ALTER TABLE users ADD COLUMN active BOOLEAN DEFAULT 1 NOT NULL"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
