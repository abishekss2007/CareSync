"""Database models. Runs on SQLite by default; set DATABASE_URL to point at Db2 on Cloud."""
import datetime as dt
import os
from pathlib import Path

from sqlalchemy import (Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint, create_engine, event)
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
    priority: Mapped[str] = mapped_column(String(10), default="normal", index=True)  # normal, urgent, critical
    draft: Mapped[str] = mapped_column(Text, default="")  # unsaved consultation notes kept while a doctor is interrupted


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
    kind: Mapped[str] = mapped_column(String(20), default="", index=True)  # "" for ordinary, "emergency", "equipment"
    ref: Mapped[str] = mapped_column(String(40), default="")  # id of the record the notification links to
    delivered_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)  # the recipient's app showed it
    acked_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)


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


# ---------- emergencies ----------

class EmergencyAlert(Base):
    __tablename__ = "emergency_alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ern: Mapped[str] = mapped_column(String(24), unique=True, index=True)  # emergency registration number
    idem_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # stops repeated clicks creating twins
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    visit_id: Mapped[int | None] = mapped_column(ForeignKey("visits.id"), nullable=True)
    emergency_type: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(600), default="")
    priority: Mapped[str] = mapped_column(String(10), default="critical", index=True)  # critical, urgent, normal
    triage_level: Mapped[str] = mapped_column(String(60), default="")  # set by the clinical team, never inferred
    location: Mapped[str] = mapped_column(String(60), default="")
    team: Mapped[str] = mapped_column(String(60), default="Emergency")
    assigned_doctor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="alert_created", index=True)
    arrival_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    received_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)  # assigned doctor's screen showed it
    acknowledged_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    last_escalated_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class EmergencyEvent(Base):
    __tablename__ = "emergency_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("emergency_alerts.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # empty for automatic escalation
    action: Mapped[str] = mapped_column(String(30))
    from_value: Mapped[str] = mapped_column(String(60), default="")
    to_value: Mapped[str] = mapped_column(String(60), default="")
    note: Mapped[str] = mapped_column(String(400), default="")
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


# ---------- equipment and supplies ----------

class EquipmentCatalogItem(Base):
    """Reference catalogue: what can be requested, grouped by department and category."""
    __tablename__ = "equipment_catalog"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section: Mapped[str] = mapped_column(String(80), index=True)  # catalogue department, e.g. Laundry and linen services
    category: Mapped[str] = mapped_column(String(60), index=True)
    name: Mapped[str] = mapped_column(String(120))
    tracking: Mapped[str] = mapped_column(String(10), default="asset")  # asset (individually tagged) or quantity
    unit: Mapped[str] = mapped_column(String(20), default="unit")
    departments: Mapped[str] = mapped_column(String(200), default="")  # hospital departments that usually request it
    needs_service: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("section", "name", name="uq_catalog_section_name"),)


class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    kind: Mapped[str] = mapped_column(String(20), default="supplier")  # supplier or service
    contact: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class InventoryItem(Base):
    """Stock of one kind of item. total = available + reserved + in_service + maintenance + damaged, always."""
    __tablename__ = "inventory_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    catalog_id: Mapped[int | None] = mapped_column(ForeignKey("equipment_catalog.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(60), default="", index=True)
    model: Mapped[str] = mapped_column(String(80), default="")
    tracking: Mapped[str] = mapped_column(String(10), default="quantity")
    unit: Mapped[str] = mapped_column(String(20), default="unit")
    total: Mapped[int] = mapped_column(Integer, default=0)
    available: Mapped[int] = mapped_column(Integer, default=0)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    in_service: Mapped[int] = mapped_column(Integer, default=0)
    maintenance: Mapped[int] = mapped_column(Integer, default=0)
    damaged: Mapped[int] = mapped_column(Integer, default=0)
    min_stock: Mapped[int] = mapped_column(Integer, default=0)
    location: Mapped[str] = mapped_column(String(80), default="Central stores")
    department: Mapped[str] = mapped_column(String(60), default="")
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    warranty: Mapped[str] = mapped_column(String(120), default="")
    last_maintenance: Mapped[str] = mapped_column(String(10), default="")
    next_maintenance: Mapped[str] = mapped_column(String(10), default="", index=True)
    condition: Mapped[str] = mapped_column(String(20), default="good")
    low_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    service_notified_for: Mapped[str] = mapped_column(String(10), default="")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    __table_args__ = (
        CheckConstraint("available >= 0 AND reserved >= 0 AND in_service >= 0 AND maintenance >= 0 AND damaged >= 0",
                        name="ck_inventory_not_negative"),
    )


class EquipmentAsset(Base):
    """One tagged unit of high-value equipment."""
    __tablename__ = "equipment_assets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inventory_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    asset_tag: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    serial: Mapped[str] = mapped_column(String(60), default="")
    state: Mapped[str] = mapped_column(String(14), default="available", index=True)
    request_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # the request it is allocated to
    department: Mapped[str] = mapped_column(String(60), default="")
    condition: Mapped[str] = mapped_column(String(20), default="good")
    warranty_until: Mapped[str] = mapped_column(String(10), default="")
    last_maintenance: Mapped[str] = mapped_column(String(10), default="")
    next_maintenance: Mapped[str] = mapped_column(String(10), default="")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class EquipmentRequest(Base):
    __tablename__ = "equipment_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    idem_key: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    department: Mapped[str] = mapped_column(String(60), index=True)
    location: Mapped[str] = mapped_column(String(80), default="")
    catalog_id: Mapped[int | None] = mapped_column(ForeignKey("equipment_catalog.id"), nullable=True)
    item_name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60), default="", index=True)
    request_type: Mapped[str] = mapped_column(String(14), default="new")  # new, repair, servicing, replacement, consumable
    quantity: Mapped[int] = mapped_column(Integer)
    qty_approved: Mapped[int] = mapped_column(Integer, default=0)
    qty_reserved: Mapped[int] = mapped_column(Integer, default=0)  # held in stores for this request, not yet dispatched
    qty_sourced: Mapped[int] = mapped_column(Integer, default=0)  # ordered from outside suppliers
    qty_received: Mapped[int] = mapped_column(Integer, default=0)  # arrived from suppliers and passed inspection
    qty_dispatched: Mapped[int] = mapped_column(Integer, default=0)
    qty_delivered: Mapped[int] = mapped_column(Integer, default=0)
    qty_returned: Mapped[int] = mapped_column(Integer, default=0)
    urgency: Mapped[str] = mapped_column(String(10), default="routine", index=True)  # routine, urgent, critical
    justification: Mapped[str] = mapped_column(Text, default="")
    attachment_name: Mapped[str] = mapped_column(String(160), default="")
    attachment_path: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(24), default="pending_dean", index=True)
    dean_status: Mapped[str] = mapped_column(String(14), default="pending", index=True)
    procurement_status: Mapped[str] = mapped_column(String(20), default="not_started", index=True)
    dispatch_status: Mapped[str] = mapped_column(String(20), default="not_dispatched", index=True)
    clarification_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inventory_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_items.id"), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    expected_date: Mapped[str] = mapped_column(String(10), default="")
    emergency_policy: Mapped[bool] = mapped_column(Boolean, default=False)
    decided_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decision_note: Mapped[str] = mapped_column(String(400), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now, index=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (
        CheckConstraint("quantity > 0 AND qty_approved >= 0 AND qty_reserved >= 0 AND qty_dispatched >= 0 "
                        "AND qty_delivered >= 0 AND qty_delivered <= qty_dispatched", name="ck_equipment_qty"),
    )


class EquipmentEvent(Base):
    __tablename__ = "equipment_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("equipment_requests.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(30))
    from_status: Mapped[str] = mapped_column(String(24), default="")
    to_status: Mapped[str] = mapped_column(String(24), default="")
    qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(String(400), default="")
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class SourcingOrder(Base):
    __tablename__ = "sourcing_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("equipment_requests.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    reference: Mapped[str] = mapped_column(String(60), default="")  # purchase order or sourcing reference
    qty_ordered: Mapped[int] = mapped_column(Integer)
    qty_arrived: Mapped[int] = mapped_column(Integer, default=0)
    qty_accepted: Mapped[int] = mapped_column(Integer, default=0)
    qty_rejected: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="ordered", index=True)
    expected_date: Mapped[str] = mapped_column(String(10), default="")
    delay_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    inspection_note: Mapped[str] = mapped_column(String(400), default="")
    created_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class Dispatch(Base):
    __tablename__ = "dispatches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idem_key: Mapped[str] = mapped_column(String(64), unique=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("equipment_requests.id"), index=True)
    inventory_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"))
    qty: Mapped[int] = mapped_column(Integer)
    asset_tags: Mapped[str] = mapped_column(String(600), default="")
    destination: Mapped[str] = mapped_column(String(120))
    handled_by: Mapped[str] = mapped_column(String(120), default="")  # staff member carrying it
    dispatched_by: Mapped[int] = mapped_column(Integer)
    dispatched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    status: Mapped[str] = mapped_column(String(14), default="in_transit", index=True)
    qty_delivered: Mapped[int] = mapped_column(Integer, default=0)
    received_by: Mapped[str] = mapped_column(String(120), default="")
    confirmed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivered_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (CheckConstraint("qty > 0 AND qty_delivered >= 0 AND qty_delivered <= qty", name="ck_dispatch_qty"),)


class StockTransaction(Base):
    __tablename__ = "stock_transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inventory_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    request_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(20))
    qty: Mapped[int] = mapped_column(Integer)
    from_state: Mapped[str] = mapped_column(String(14), default="")
    to_state: Mapped[str] = mapped_column(String(14), default="")
    asset_tags: Mapped[str] = mapped_column(String(600), default="")
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(String(300), default="")
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=now, index=True)


class MaintenanceTicket(Base):
    __tablename__ = "maintenance_tickets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    idem_key: Mapped[str] = mapped_column(String(64), unique=True)
    inventory_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_items.id"), nullable=True, index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("equipment_assets.id"), nullable=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("equipment_requests.id"), nullable=True)
    item_name: Mapped[str] = mapped_column(String(120))
    qty: Mapped[int] = mapped_column(Integer, default=1)
    qty_held: Mapped[int] = mapped_column(Integer, default=0)  # units moved into the maintenance count
    held_from: Mapped[str] = mapped_column(String(14), default="")
    department: Mapped[str] = mapped_column(String(60), default="")
    reported_by: Mapped[int] = mapped_column(Integer, index=True)
    issue: Mapped[str] = mapped_column(String(600))
    unsafe: Mapped[bool] = mapped_column(Boolean, default=False)
    kind: Mapped[str] = mapped_column(String(14), default="repair")  # repair, servicing, calibration, inspection
    status: Mapped[str] = mapped_column(String(22), default="reported", index=True)
    technician: Mapped[str] = mapped_column(String(120), default="")
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    scheduled_for: Mapped[str] = mapped_column(String(10), default="")
    findings: Mapped[str] = mapped_column(String(600), default="")
    parts_used: Mapped[str] = mapped_column(String(300), default="")
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    verified_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verification_note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class MaintenanceEvent(Base):
    __tablename__ = "maintenance_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("maintenance_tickets.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(String(400), default="")
    at: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


# Columns added to tables that existed before. Only ever ADD COLUMN: existing rows and tables are kept.
ADDED_COLUMNS = {
    "users": [("active", "BOOLEAN DEFAULT 1 NOT NULL")],
    "visits": [("priority", "VARCHAR(10) DEFAULT 'normal' NOT NULL"), ("draft", "TEXT DEFAULT '' NOT NULL")],
    "notifications": [("kind", "VARCHAR(20) DEFAULT '' NOT NULL"), ("ref", "VARCHAR(40) DEFAULT '' NOT NULL"),
                      ("delivered_at", "TIMESTAMP"), ("acked_at", "TIMESTAMP"),
                      ("attempts", "INTEGER DEFAULT 1 NOT NULL")],
}
ADDED_INDEXES = [("ix_visits_priority", "visits", "priority"), ("ix_notifications_kind", "notifications", "kind")]


def migrate():
    """Add columns introduced after a database was first created."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    for table, columns in ADDED_COLUMNS.items():
        if not inspector.has_table(table):
            continue
        have = {c["name"] for c in inspector.get_columns(table)}
        with engine.begin() as con:
            for name, ddl in columns:
                if name not in have:
                    con.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
    inspector = inspect(engine)
    for name, table, column in ADDED_INDEXES:
        if inspector.has_table(table) and name not in {i["name"] for i in inspector.get_indexes(table)}:
            with engine.begin() as con:
                con.execute(text(f"CREATE INDEX {name} ON {table} ({column})"))


# Live updates: code that changes data records which users should hear about in session.info["bump"].
# Once the transaction commits, those users' counters move on and their open event streams wake up.
BUS = {"emergency": 0, "equipment": 0, "users": {}}


@event.listens_for(SessionLocal, "after_commit")
def _publish(session):
    bump = session.info.pop("bump", None)
    if not bump:
        return
    for key in bump:
        if isinstance(key, int):
            BUS["users"][key] = BUS["users"].get(key, 0) + 1
        else:
            BUS[key] = BUS.get(key, 0) + 1


@event.listens_for(SessionLocal, "after_rollback")
def _drop(session):
    session.info.pop("bump", None)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
