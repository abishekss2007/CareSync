"""Equipment and medical supplies: requests, dean approval, sourcing, inventory, dispatch, delivery and maintenance.

Stock counts change only through move(), which runs a conditional UPDATE inside the request's transaction, so two
people acting at once can never push a count below zero or hand the same tagged asset to two requests.
"""
import base64
import datetime as dt
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from .db import (ROOT, Dispatch, EquipmentAsset, EquipmentCatalogItem, EquipmentEvent, EquipmentRequest,
                 InventoryItem, MaintenanceEvent, MaintenanceTicket, SourcingOrder, StockTransaction, Supplier, User,
                 get_db, now)
from .main import DEPARTMENTS, audit, bump, iso, notify, require, uname

router = APIRouter(prefix="/api/equipment")

# Roles. Every endpoint checks these on the server.
REQUESTERS = {"doctor"}
DEPT_STAFF = {"doctor", "nurse"}
DEAN = {"dean"}
OPS = {"coordinator", "admin"}  # stores and procurement work
VIEW_ALL = {"dean", "chairman", "admin", "coordinator"}
ANY = DEPT_STAFF | VIEW_ALL

REQUEST_TYPES = {"new": "New purchase", "repair": "Repair", "servicing": "Servicing / calibration",
                 "replacement": "Replacement", "consumable": "Consumable supply"}
URGENCY = ["critical", "urgent", "routine"]
STATUS_LABEL = {
    "pending_dean": "Awaiting dean approval", "clarification": "Clarification requested", "rejected": "Rejected",
    "approved": "Approved, awaiting sourcing", "sourcing_required": "Sourcing required", "sourcing": "Procurement in progress",
    "backorder": "Backordered", "ready_for_dispatch": "Ready for dispatch", "dispatched": "Dispatched",
    "partially_fulfilled": "Partially fulfilled", "fulfilled": "Fulfilled", "cancelled": "Cancelled",
    "servicing": "Service in progress",
}
STATES = ("available", "reserved", "in_service", "maintenance", "damaged")
OUTSIDE = "outside"  # arriving from a supplier, or consumed by a department
SERVICE_DAYS = 180
ATTACH_TYPES = {"pdf", "png", "jpg", "jpeg", "doc", "docx", "xls", "xlsx", "txt", "csv"}
ATTACH_DIR = ROOT / "uploads" / "equipment"


def today():
    return now().date().isoformat()


def ops_ids(db):
    return list(db.scalars(select(User.id).where(User.role == "coordinator", User.active == True)))  # noqa: E712


def role_active(db, role):
    return list(db.scalars(select(User.id).where(User.role == role, User.active == True)))  # noqa: E712


def tell(db, ids, text, ref):
    notify(db, ids, text, "equipment", kind="equipment", ref=ref)
    bump(db, "equipment")


def valid_date(value, label="Date"):
    if not value:
        return ""
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError:
        raise HTTPException(400, f"{label} is not a valid date")


def find_supplier(db, supplier_id=None, name=""):
    if supplier_id:
        s = db.get(Supplier, supplier_id)
        if not s:
            raise HTTPException(404, "No such supplier")
        return s
    name = name.strip()
    if not name:
        raise HTTPException(400, "Choose a supplier or service provider")
    s = db.scalar(select(Supplier).where(func.lower(Supplier.name) == name.lower()))
    if not s:
        s = Supplier(name=name[:120])
        db.add(s)
        db.flush()
    return s


# ---------- stock movements ----------

def check_low_stock(db, item):
    if item.min_stock and item.available < item.min_stock:
        if not item.low_notified:
            item.low_notified = True
            tell(db, ops_ids(db), f"Low stock: {item.name} ({item.code}) has {item.available} available, "
                                  f"minimum is {item.min_stock}", f"inv{item.id}")
    elif item.low_notified:
        item.low_notified = False


def move(db, item, frm, to, qty, user, kind, request=None, note="", department="", tags=None):
    """Move qty units of an item between stock states in one guarded step. Raises 409 if there are not enough."""
    if qty <= 0:
        raise HTTPException(400, "Quantity must be at least 1")
    db.flush()
    moved_tags = []
    if item.tracking == "asset":
        q = select(EquipmentAsset).where(EquipmentAsset.inventory_id == item.id)
        if frm != OUTSIDE:
            q = q.where(EquipmentAsset.state == frm)
            if frm in ("reserved", "in_service") and request is not None:
                q = q.where(EquipmentAsset.request_id == request.id)
            if tags:
                q = q.where(EquipmentAsset.asset_tag.in_(tags))
            assets = db.scalars(q.order_by(EquipmentAsset.id).limit(qty)).all()
            if len(assets) < qty:
                raise HTTPException(409, f"Only {len(assets)} tagged {item.name} can be moved from {frm.replace('_', ' ')}")
            for a in assets:
                values = {"state": to if to != OUTSIDE else "disposed", "updated_at": now()}
                if to == "reserved":
                    values["request_id"] = request.id if request else None
                elif to == "available":
                    values.update(request_id=None, department="")
                elif to == "in_service":
                    values["department"] = department or a.department
                res = db.execute(update(EquipmentAsset).where(EquipmentAsset.id == a.id, EquipmentAsset.state == frm)
                                 .values(**values).execution_options(synchronize_session=False))
                if res.rowcount != 1:  # someone else took this unit a moment ago
                    raise HTTPException(409, f"{a.asset_tag} was just allocated elsewhere. Try again")
                moved_tags.append(a.asset_tag)
        else:
            tags = [t.strip().upper() for t in (tags or []) if t.strip()]
            if len(tags) != qty or len(set(tags)) != qty:
                raise HTTPException(400, f"Enter {qty} distinct asset tags for {item.name}")
            taken = db.scalars(select(EquipmentAsset.asset_tag).where(EquipmentAsset.asset_tag.in_(tags))).all()
            if taken:
                raise HTTPException(409, "Asset tag already in use: " + ", ".join(taken))
            for t in tags:
                db.add(EquipmentAsset(inventory_id=item.id, asset_tag=t, state=to,
                                      request_id=request.id if request and to == "reserved" else None,
                                      department=department if to == "in_service" else "",
                                      next_maintenance=item.next_maintenance))
            moved_tags = tags
    values = {}
    cond = [InventoryItem.id == item.id]
    if frm != OUTSIDE:
        col = getattr(InventoryItem, frm)
        values[frm] = col - qty
        cond.append(col >= qty)
    else:
        values["total"] = InventoryItem.total + qty
    if to != OUTSIDE:
        values[to] = getattr(InventoryItem, to) + qty
    else:
        values["total"] = InventoryItem.total - qty
    values["updated_at"] = now()
    res = db.execute(update(InventoryItem).where(*cond).values(**values).execution_options(synchronize_session=False))
    if res.rowcount != 1:
        db.refresh(item)
        have = getattr(item, frm) if frm != OUTSIDE else 0
        raise HTTPException(409, f"Not enough {item.name}: {have} {frm.replace('_', ' ')}, {qty} needed")
    db.refresh(item)
    db.add(StockTransaction(inventory_id=item.id, request_id=request.id if request else None, kind=kind, qty=qty,
                            from_state=frm, to_state=to, asset_tags=",".join(moved_tags)[:600],
                            user_id=user.id if user else None, note=note[:300]))
    check_low_stock(db, item)
    return moved_tags


# ---------- request status ----------

def log(db, r, user, action, note="", qty=None, before=None):
    db.add(EquipmentEvent(request_id=r.id, user_id=user.id if user else None, action=action,
                          from_status=before if before is not None else r.status, to_status=r.status, qty=qty,
                          note=note[:400]))
    r.updated_at = now()
    bump(db, "equipment")


def recompute(db, r):
    """Derive the overall, procurement and dispatch status from the recorded quantities."""
    if r.status in ("rejected", "cancelled"):
        return
    if r.dean_status == "pending":
        r.status = "pending_dean"
        return
    if r.dean_status == "clarification":
        r.status = "clarification"
        return
    approved = r.qty_approved
    outstanding = approved - r.qty_dispatched
    orders = db.scalars(select(SourcingOrder).where(SourcingOrder.request_id == r.id)).all()
    open_orders = [o for o in orders if o.status in ("ordered", "delayed", "arrived")]
    if r.request_type in ("repair", "servicing"):
        tickets = db.scalars(select(MaintenanceTicket).where(MaintenanceTicket.request_id == r.id)).all()
        done = [t for t in tickets if t.status == "completed"]
        if tickets and len(done) == len(tickets):
            r.status, r.procurement_status, r.dispatch_status = "fulfilled", "complete", "delivered"
            r.closed_at = r.closed_at or now()
        elif tickets:
            r.status, r.procurement_status = "servicing", "service_scheduled"
        else:
            r.status = "approved"
        return
    if r.qty_delivered >= approved > 0:
        r.status = "fulfilled"
        r.closed_at = r.closed_at or now()
    elif r.qty_delivered > 0:
        r.status = "partially_fulfilled"
    elif r.qty_dispatched > r.qty_delivered:
        r.status = "dispatched"
    elif outstanding > 0 and r.qty_reserved >= outstanding:
        r.status = "ready_for_dispatch"
    elif r.procurement_status == "backorder":
        r.status = "backorder"
    elif open_orders:
        r.status = "sourcing"
    elif r.procurement_status == "sourcing_required":
        r.status = "sourcing_required"
    else:
        r.status = "approved"
    if r.status != "fulfilled":
        r.closed_at = None
    if r.qty_delivered >= approved > 0:
        r.dispatch_status = "delivered"
    elif r.qty_delivered:
        r.dispatch_status = "partially_delivered"
    elif r.qty_dispatched:
        r.dispatch_status = "in_transit"
    elif outstanding > 0 and r.qty_reserved >= outstanding:
        r.dispatch_status = "ready"
    else:
        r.dispatch_status = "not_dispatched"
    if r.status == "fulfilled":
        r.procurement_status = "complete"
    elif r.procurement_status != "backorder":
        if open_orders:
            r.procurement_status = "sourcing"
        elif r.qty_reserved + r.qty_dispatched >= approved:
            r.procurement_status = "reserved"
        elif r.qty_received:
            r.procurement_status = "received"


def request_out(db, r, user, detail=False):
    creator = db.get(User, r.created_by)
    supplier = db.get(Supplier, r.supplier_id) if r.supplier_id else None
    out = {
        "id": r.id, "ref": r.ref, "created_at": iso(r.created_at), "updated_at": iso(r.updated_at),
        "closed_at": iso(r.closed_at),
        "doctor": creator.name if creator else "", "doctor_id": r.created_by, "department": r.department,
        "location": r.location, "item_name": r.item_name, "category": r.category, "catalog_id": r.catalog_id,
        "request_type": r.request_type, "request_type_label": REQUEST_TYPES.get(r.request_type, r.request_type),
        "quantity": r.quantity, "qty_approved": r.qty_approved, "qty_reserved": r.qty_reserved,
        "qty_sourced": r.qty_sourced, "qty_received": r.qty_received, "qty_dispatched": r.qty_dispatched,
        "qty_delivered": r.qty_delivered, "qty_returned": r.qty_returned,
        "outstanding": max(0, r.qty_approved - r.qty_delivered) if r.dean_status == "approved" else 0,
        "urgency": r.urgency, "justification": r.justification, "attachment": r.attachment_name,
        "status": r.status, "status_label": STATUS_LABEL.get(r.status, r.status), "dean_status": r.dean_status,
        "procurement_status": r.procurement_status, "dispatch_status": r.dispatch_status,
        "expected_date": r.expected_date, "supplier": supplier.name if supplier else "",
        "inventory_id": r.inventory_id, "emergency_policy": r.emergency_policy,
        "decided_by": uname(db, r.decided_by), "decision_note": r.decision_note,
        "awaiting_my_answer": r.status == "clarification" and r.created_by == user.id
        or (r.clarification_from is not None and r.created_by == user.id and r.dean_status == "approved"),
        "can_decide": user.role in DEAN and r.dean_status == "pending" and r.status == "pending_dean",
        "can_operate": user.role in OPS and r.dean_status == "approved" and r.status not in ("fulfilled", "cancelled"),
        "can_cancel": r.status not in ("fulfilled", "cancelled", "rejected") and (
            (r.created_by == user.id and r.dean_status != "approved") or user.role in OPS | DEAN),
    }
    if detail:
        events = db.scalars(select(EquipmentEvent).where(EquipmentEvent.request_id == r.id)
                            .order_by(EquipmentEvent.id)).all()
        out["history"] = [{"who": uname(db, e.user_id) or "System", "action": e.action, "from": e.from_status,
                           "to": e.to_status, "qty": e.qty, "note": e.note, "at": iso(e.at)} for e in events]
        out["sourcing"] = [sourcing_out(db, o) for o in db.scalars(
            select(SourcingOrder).where(SourcingOrder.request_id == r.id).order_by(SourcingOrder.id))]
        out["dispatches"] = [dispatch_out(db, d, user) for d in db.scalars(
            select(Dispatch).where(Dispatch.request_id == r.id).order_by(Dispatch.id))]
        out["tickets"] = [ticket_out(db, t, user) for t in db.scalars(
            select(MaintenanceTicket).where(MaintenanceTicket.request_id == r.id).order_by(MaintenanceTicket.id))]
        out["reserved_tags"] = list(db.scalars(select(EquipmentAsset.asset_tag).where(
            EquipmentAsset.request_id == r.id, EquipmentAsset.state == "reserved")))
    return out


def sourcing_out(db, o):
    s = db.get(Supplier, o.supplier_id)
    return {"id": o.id, "supplier": s.name if s else "", "reference": o.reference, "qty_ordered": o.qty_ordered,
            "qty_arrived": o.qty_arrived, "qty_accepted": o.qty_accepted, "qty_rejected": o.qty_rejected,
            "status": o.status, "expected_date": o.expected_date, "inspection_note": o.inspection_note,
            "created_at": iso(o.created_at), "updated_at": iso(o.updated_at),
            "overdue": bool(o.expected_date and o.expected_date < today() and o.status in ("ordered", "delayed"))}


def dispatch_out(db, d, user):
    r = db.get(EquipmentRequest, d.request_id)
    return {"id": d.id, "request_id": d.request_id, "ref": r.ref if r else "", "item_name": r.item_name if r else "",
            "qty": d.qty, "asset_tags": d.asset_tags, "destination": d.destination, "handled_by": d.handled_by,
            "dispatched_by": uname(db, d.dispatched_by), "dispatched_at": iso(d.dispatched_at), "status": d.status,
            "qty_delivered": d.qty_delivered, "received_by": d.received_by, "confirmed_by": uname(db, d.confirmed_by),
            "delivered_at": iso(d.delivered_at), "can_confirm": d.status == "in_transit" and can_receive(user, r)}


def can_receive(user, r):
    if not r:
        return False
    return user.role in OPS or (user.role in DEPT_STAFF and user.department == r.department)


def get_request(db, request_id, user):
    r = db.get(EquipmentRequest, request_id)
    if not r:
        raise HTTPException(404, "No such equipment request")
    if user.role in VIEW_ALL or r.created_by == user.id or (user.role in DEPT_STAFF and user.department == r.department):
        return r
    raise HTTPException(404, "No such equipment request")


def ops_request(db, request_id, user):
    if user.role not in OPS:
        raise HTTPException(403, "Only the equipment coordinator or administrator can do this")
    r = get_request(db, request_id, user)
    if r.dean_status != "approved":
        raise HTTPException(409, "Only approved requests move to sourcing and dispatch")
    if r.status in ("fulfilled", "cancelled", "rejected"):
        raise HTTPException(409, f"This request is {STATUS_LABEL[r.status].lower()}")
    return r


def ready_to_send(r):
    outstanding = r.qty_approved - r.qty_dispatched
    return r.dean_status == "approved" and outstanding > 0 and r.qty_reserved >= outstanding


def finish(db, r, user, action, note="", qty=None):
    before, was_ready = r.status, ready_to_send(r) and action not in ("reserved", "inspected")
    recompute(db, r)
    log(db, r, user, action, note, qty, before)
    if r.status != before:
        announce(db, r, before)
    if ready_to_send(r) and not was_ready and r.status != "ready_for_dispatch":  # e.g. the rest of a partial order
        tell(db, ops_ids(db), f"Dispatch ready: {r.ref} {r.item_name} for {r.department} ({r.qty_reserved} reserved)", r.id)


def announce(db, r, before):
    """Tell the doctor, dean and coordinator about the changes they care about."""
    label = STATUS_LABEL[r.status]
    head = f"{r.ref} {r.item_name}"
    if r.status in ("approved", "rejected", "clarification", "dispatched", "partially_fulfilled", "fulfilled",
                    "backorder", "ready_for_dispatch", "servicing"):
        tell(db, [r.created_by], f"{head}: {label}" + (f" ({r.qty_delivered} of {r.qty_approved} delivered)"
                                                        if r.status == "partially_fulfilled" else ""), r.id)
    if r.decided_by and r.status in ("dispatched", "partially_fulfilled", "fulfilled", "backorder"):
        tell(db, [r.decided_by], f"{head} for {r.department}: {label}", r.id)
    if r.status == "ready_for_dispatch":
        tell(db, ops_ids(db), f"Dispatch ready: {head} for {r.department} ({r.qty_reserved} reserved)", r.id)
    if r.status == "sourcing_required":
        tell(db, ops_ids(db), f"New sourcing task: {head} for {r.department}", r.id)


# ---------- catalogue and suppliers ----------

@router.get("/catalog")
def catalog(db=Depends(get_db), user=Depends(require(*ANY))):
    sections = {}
    for c in db.scalars(select(EquipmentCatalogItem).order_by(EquipmentCatalogItem.id)):
        depts = [d for d in c.departments.split(",") if d]
        s = sections.setdefault(c.section, {"section": c.section, "departments": depts, "categories": {}})
        s["categories"].setdefault(c.category, []).append(
            {"id": c.id, "name": c.name, "tracking": c.tracking, "unit": c.unit, "needs_service": c.needs_service})
    out = []
    for s in sections.values():
        mine = bool(user.department) and (user.department in s["departments"] or "*" in s["departments"])
        out.append({"section": s["section"], "departments": s["departments"], "for_me": mine,
                    "shared": "*" in s["departments"],
                    "categories": [{"category": k, "items": v} for k, v in s["categories"].items()]})
    return {"sections": out, "request_types": [{"id": k, "label": v} for k, v in REQUEST_TYPES.items()],
            "urgency": URGENCY, "statuses": [{"id": k, "label": v} for k, v in STATUS_LABEL.items()],
            "departments": DEPARTMENTS}


@router.get("/suppliers")
def suppliers(db=Depends(get_db), user=Depends(require(*VIEW_ALL))):
    return [{"id": s.id, "name": s.name, "kind": s.kind, "contact": s.contact, "phone": s.phone, "email": s.email}
            for s in db.scalars(select(Supplier).order_by(Supplier.name))]


class SupplierIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    kind: str = "supplier"
    contact: str = Field(default="", max_length=120)
    phone: str = Field(default="", max_length=30)
    email: str = Field(default="", max_length=120)


@router.post("/suppliers")
def add_supplier(body: SupplierIn, db=Depends(get_db), user=Depends(require(*OPS))):
    if body.kind not in ("supplier", "service"):
        raise HTTPException(400, "Choose supplier or service provider")
    if db.scalar(select(Supplier).where(func.lower(Supplier.name) == body.name.strip().lower())):
        raise HTTPException(409, "That supplier already exists")
    s = Supplier(name=body.name.strip(), kind=body.kind, contact=body.contact.strip(), phone=body.phone.strip(),
                 email=body.email.strip())
    db.add(s)
    audit(db, user, "added supplier", s.name)
    db.commit()
    return {"id": s.id, "name": s.name}


# ---------- requests ----------

class AttachmentIn(BaseModel):
    name: str = Field(max_length=160)
    data: str = Field(max_length=4_200_000)  # base64, about 3 MB


class RequestIn(BaseModel):
    idem_key: str = Field(min_length=8, max_length=64)
    catalog_id: int | None = None
    item_name: str = Field(default="", max_length=120)
    category: str = Field(default="", max_length=60)
    request_type: str = "new"
    quantity: int = Field(ge=1, le=10000)
    urgency: str = "routine"
    justification: str = Field(min_length=5, max_length=2000)
    location: str = Field(default="", max_length=80)
    attachment: AttachmentIn | None = None


def save_attachment(ref, att):
    ext = att.name.rsplit(".", 1)[-1].lower() if "." in att.name else ""
    if ext not in ATTACH_TYPES:
        raise HTTPException(400, "Attach a PDF, image, Word, Excel or text file")
    try:
        raw = base64.b64decode(att.data, validate=True)
    except ValueError:
        raise HTTPException(400, "The attachment could not be read")
    if len(raw) > 3 * 1024 * 1024:
        raise HTTPException(400, "Attachments can be up to 3 MB")
    ATTACH_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", att.name)[-80:]
    path = ATTACH_DIR / f"{ref}-{secrets.token_hex(4)}-{safe}"
    path.write_bytes(raw)
    return att.name[:160], path.relative_to(ROOT).as_posix()


@router.post("/requests")
def create_request(body: RequestIn, db=Depends(get_db), user=Depends(require(*REQUESTERS))):
    existing = db.scalar(select(EquipmentRequest).where(EquipmentRequest.idem_key == body.idem_key))
    if existing:
        if existing.created_by != user.id:
            raise HTTPException(409, "Duplicate request key")
        return {"request": request_out(db, existing, user), "duplicate": True}
    if body.request_type not in REQUEST_TYPES:
        raise HTTPException(400, "Unknown request type")
    if body.urgency not in URGENCY:
        raise HTTPException(400, "Unknown urgency")
    if not user.department:
        raise HTTPException(400, "Your account has no department")
    name, category = body.item_name.strip(), body.category.strip()
    if body.catalog_id:
        c = db.get(EquipmentCatalogItem, body.catalog_id)
        if not c:
            raise HTTPException(400, "Unknown catalogue item")
        name, category = c.name, c.category
    if len(name) < 2:
        raise HTTPException(400, "Choose an item from the catalogue or describe it")
    r = EquipmentRequest(ref="tmp-" + secrets.token_hex(8), idem_key=body.idem_key, created_by=user.id,
                         department=user.department, location=body.location.strip() or user.department,
                         catalog_id=body.catalog_id, item_name=name, category=category or "Other",
                         request_type=body.request_type, quantity=body.quantity, urgency=body.urgency,
                         justification=body.justification.strip())
    db.add(r)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(EquipmentRequest).where(EquipmentRequest.idem_key == body.idem_key))
        return {"request": request_out(db, existing, user), "duplicate": True}
    r.ref = f"EQ-{r.created_at.year}-{r.id:04d}"
    if body.attachment:
        r.attachment_name, r.attachment_path = save_attachment(r.ref, body.attachment)
    log(db, r, user, "created", f"{body.quantity} x {name} ({REQUEST_TYPES[r.request_type]}, {r.urgency})", r.quantity, "")
    from .db import Setting
    policy = db.get(Setting, "equipment_emergency_procurement")
    if r.urgency == "critical" and policy and policy.value == "1":
        r.dean_status, r.qty_approved, r.emergency_policy = "approved", r.quantity, True
        finish(db, r, None, "auto-approved", "Critical request approved under the emergency procurement policy")
        tell(db, ops_ids(db), f"Emergency procurement: {r.ref} {r.item_name} for {r.department}", r.id)
        tell(db, role_active(db, "dean"), f"{r.ref} was approved automatically under the emergency procurement "
                                          f"policy: {r.quantity} x {r.item_name} for {r.department}", r.id)
    else:
        tell(db, role_active(db, "dean"), f"Equipment request {r.ref} from {user.name} ({r.department}): "
                                          f"{r.quantity} x {r.item_name}, {r.urgency}", r.id)
    audit(db, user, "raised equipment request", f"{r.ref} {r.item_name}")
    db.commit()
    return {"request": request_out(db, r, user), "duplicate": False}


SORTS = {"created_at": EquipmentRequest.created_at, "updated_at": EquipmentRequest.updated_at,
         "ref": EquipmentRequest.id, "department": EquipmentRequest.department,
         "item_name": EquipmentRequest.item_name, "urgency": EquipmentRequest.urgency,
         "status": EquipmentRequest.status, "quantity": EquipmentRequest.quantity,
         "expected_date": EquipmentRequest.expected_date}


@router.get("/requests")
def list_requests(scope: str = "", q: str = "", status: str = "", department: str = "", urgency: str = "",
                  category: str = "", request_type: str = "", date_from: str = "", date_to: str = "",
                  open_only: bool = False, sort: str = "created_at", dir: str = "desc", page: int = 1, size: int = 20,
                  db=Depends(get_db), user=Depends(require(*ANY))):
    query = select(EquipmentRequest)
    if user.role in DEPT_STAFF:
        query = query.where(EquipmentRequest.created_by == user.id) if scope == "mine" else \
            query.where(EquipmentRequest.department == user.department)
    if q.strip():
        term = f"%{q.strip().lower()}%"
        query = query.where(or_(func.lower(EquipmentRequest.ref).like(term), func.lower(EquipmentRequest.item_name).like(term),
                                func.lower(EquipmentRequest.category).like(term)))
    for value, col in ((status, EquipmentRequest.status), (department, EquipmentRequest.department),
                       (urgency, EquipmentRequest.urgency), (category, EquipmentRequest.category),
                       (request_type, EquipmentRequest.request_type)):
        if value:
            query = query.where(col.in_(value.split(",")))
    if open_only:
        query = query.where(EquipmentRequest.status.not_in(["fulfilled", "cancelled", "rejected"]))
    if date_from:
        query = query.where(EquipmentRequest.created_at >= dt.datetime.fromisoformat(valid_date(date_from)))
    if date_to:
        query = query.where(EquipmentRequest.created_at < dt.datetime.fromisoformat(valid_date(date_to)) + dt.timedelta(days=1))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    col = SORTS.get(sort, EquipmentRequest.created_at)
    size = max(5, min(size, 100))
    page = max(1, page)
    rows = db.scalars(query.order_by(col.asc() if dir == "asc" else col.desc(), EquipmentRequest.id.desc())
                      .offset((page - 1) * size).limit(size)).all()
    return {"rows": [request_out(db, r, user) for r in rows], "total": total, "page": page, "size": size}


@router.get("/requests/{request_id}")
def request_detail(request_id: int, db=Depends(get_db), user=Depends(require(*ANY))):
    return request_out(db, get_request(db, request_id, user), user, detail=True)


@router.get("/requests/{request_id}/attachment")
def attachment(request_id: int, db=Depends(get_db), user=Depends(require(*ANY))):
    r = get_request(db, request_id, user)
    if not r.attachment_path or not (ROOT / r.attachment_path).exists():
        raise HTTPException(404, "No attachment")
    return FileResponse(ROOT / r.attachment_path, filename=r.attachment_name)


class DecideIn(BaseModel):
    action: str
    qty_approved: int | None = Field(default=None, ge=1, le=10000)
    note: str = Field(default="", max_length=400)


@router.post("/requests/{request_id}/decide")
def decide(request_id: int, body: DecideIn, db=Depends(get_db), user=Depends(require(*DEAN))):
    r = get_request(db, request_id, user)
    if r.status != "pending_dean":
        raise HTTPException(409, f"This request is {STATUS_LABEL.get(r.status, r.status).lower()}, not waiting for approval")
    note = body.note.strip()
    r.decided_by = user.id
    if body.action == "approve":
        qty = body.qty_approved or r.quantity
        if qty > r.quantity and not note:
            raise HTTPException(400, "Give a reason when approving more than was requested")
        r.dean_status, r.qty_approved, r.decision_note = "approved", qty, note
        finish(db, r, user, "approved", note or f"Approved {qty} of {r.quantity}", qty)
        log(db, r, user, "forwarded", "Forwarded to the equipment coordinator")
        tell(db, ops_ids(db), f"Approved by the dean: {r.ref} {qty} x {r.item_name} for {r.department}"
                              f" ({r.urgency})", r.id)
    elif body.action == "reject":
        if not note:
            raise HTTPException(400, "Give the reason for rejecting")
        before = r.status
        r.dean_status, r.status, r.decision_note, r.closed_at = "rejected", "rejected", note, now()
        log(db, r, user, "rejected", note, None, before)
        announce(db, r, before)
    elif body.action == "clarify":
        if not note:
            raise HTTPException(400, "Write the question for the doctor")
        r.dean_status, r.clarification_from = "clarification", user.id
        finish(db, r, user, "clarification requested", note)
    else:
        raise HTTPException(400, "Unknown action")
    audit(db, user, f"equipment request {body.action}", r.ref)
    db.commit()
    return request_out(db, r, user)


class RespondIn(BaseModel):
    note: str = Field(min_length=2, max_length=400)
    quantity: int | None = Field(default=None, ge=1, le=10000)


@router.post("/requests/{request_id}/respond")
def respond(request_id: int, body: RespondIn, db=Depends(get_db), user=Depends(require(*REQUESTERS))):
    r = get_request(db, request_id, user)
    if r.created_by != user.id or r.clarification_from is None:
        raise HTTPException(409, "No question is waiting on you for this request")
    asker = r.clarification_from
    if r.dean_status == "clarification":
        if body.quantity:
            r.quantity = body.quantity
        r.justification += f"\n\nClarification: {body.note.strip()}"
        r.dean_status = "pending"
    r.clarification_from = None
    finish(db, r, user, "clarified", body.note.strip(), body.quantity)
    tell(db, [asker], f"{user.name} answered your question on {r.ref}: {body.note.strip()[:120]}", r.id)
    db.commit()
    return request_out(db, r, user)


@router.post("/requests/{request_id}/clarify")
def ask_doctor(request_id: int, body: RespondIn, db=Depends(get_db), user=Depends(require(*OPS))):
    r = ops_request(db, request_id, user)
    r.clarification_from = user.id
    log(db, r, user, "clarification requested", body.note.strip())
    tell(db, [r.created_by], f"{user.name} needs clarification on {r.ref} {r.item_name}: {body.note.strip()[:120]}", r.id)
    db.commit()
    return request_out(db, r, user)


def stock_matches(db, r):
    q = select(InventoryItem)
    if r.catalog_id:
        q = q.where(or_(InventoryItem.catalog_id == r.catalog_id, func.lower(InventoryItem.name) == r.item_name.lower()))
    else:
        q = q.where(func.lower(InventoryItem.name).like(f"%{r.item_name.lower()[:40]}%"))
    return db.scalars(q.order_by(InventoryItem.available.desc())).all()


@router.post("/requests/{request_id}/check-stock")
def check_stock(request_id: int, db=Depends(get_db), user=Depends(require(*OPS))):
    r = ops_request(db, request_id, user)
    items = stock_matches(db, r)
    needed = max(0, r.qty_approved - r.qty_reserved - r.qty_dispatched)
    available = sum(i.available for i in items)
    if needed and available < needed and r.procurement_status in ("not_started", "stock_checked"):
        r.procurement_status = "sourcing_required"
        finish(db, r, user, "stock checked", f"{available} available, {needed} needed: shortage of {needed - available}")
    else:
        if r.procurement_status == "not_started":
            r.procurement_status = "stock_checked"
        log(db, r, user, "stock checked", f"{available} available, {needed} still needed")
    db.commit()
    return {"needed": needed, "available": available, "request": request_out(db, r, user),
            "items": [inventory_out(db, i) for i in items]}


class ReserveIn(BaseModel):
    inventory_id: int
    qty: int = Field(ge=1, le=10000)
    asset_tags: list[str] = Field(default_factory=list, max_length=200)


@router.post("/requests/{request_id}/reserve")
def reserve(request_id: int, body: ReserveIn, db=Depends(get_db), user=Depends(require(*OPS))):
    r = ops_request(db, request_id, user)
    item = db.get(InventoryItem, body.inventory_id)
    if not item:
        raise HTTPException(404, "No such inventory item")
    if item.condition == "unsafe":
        raise HTTPException(409, "This item is marked unsafe and cannot be allocated")
    if r.inventory_id and r.inventory_id != item.id:
        raise HTTPException(409, "This request already draws from another stock item. Release it first")
    room = r.qty_approved - r.qty_reserved - r.qty_dispatched
    if body.qty > room:
        raise HTTPException(409, f"Only {room} more can be reserved for this request")
    move(db, item, "available", "reserved", body.qty, user, "reserve", r, f"Reserved for {r.ref}",
         tags=[t.strip().upper() for t in body.asset_tags if t.strip()] or None)
    r.inventory_id = item.id
    r.qty_reserved += body.qty
    finish(db, r, user, "reserved", f"{body.qty} from {item.code} ({item.location})", body.qty)
    db.commit()
    return request_out(db, r, user, detail=True)


class QtyNoteIn(BaseModel):
    qty: int = Field(ge=1, le=10000)
    reason: str = Field(min_length=3, max_length=400)


@router.post("/requests/{request_id}/release")
def release(request_id: int, body: QtyNoteIn, db=Depends(get_db), user=Depends(require(*OPS))):
    r = ops_request(db, request_id, user)
    if body.qty > r.qty_reserved:
        raise HTTPException(409, f"Only {r.qty_reserved} reserved")
    item = db.get(InventoryItem, r.inventory_id)
    move(db, item, "reserved", "available", body.qty, user, "release", r, body.reason)
    r.qty_reserved -= body.qty
    if r.qty_reserved == 0 and r.qty_dispatched == 0:
        r.inventory_id = None
    finish(db, r, user, "reservation released", body.reason, body.qty)
    db.commit()
    return request_out(db, r, user, detail=True)


class SourceIn(BaseModel):
    supplier_id: int | None = None
    supplier_name: str = Field(default="", max_length=120)
    reference: str = Field(default="", max_length=60)
    qty: int = Field(ge=1, le=10000)
    expected_date: str = ""


@router.post("/requests/{request_id}/source")
def source(request_id: int, body: SourceIn, db=Depends(get_db), user=Depends(require(*OPS))):
    r = ops_request(db, request_id, user)
    open_qty = sum(o.qty_ordered - o.qty_accepted - o.qty_rejected for o in db.scalars(
        select(SourcingOrder).where(SourcingOrder.request_id == r.id, SourcingOrder.status.in_(["ordered", "delayed", "arrived"]))))
    room = r.qty_approved - r.qty_reserved - r.qty_dispatched - open_qty
    if body.qty > room:
        raise HTTPException(409, f"Only {max(0, room)} more need sourcing for this request")
    s = find_supplier(db, body.supplier_id, body.supplier_name)
    o = SourcingOrder(request_id=r.id, supplier_id=s.id, reference=body.reference.strip(), qty_ordered=body.qty,
                      expected_date=valid_date(body.expected_date, "Expected date"), created_by=user.id)
    db.add(o)
    db.flush()
    r.qty_sourced += body.qty
    r.supplier_id, r.expected_date = s.id, o.expected_date or r.expected_date
    if r.procurement_status == "backorder":
        r.procurement_status = "sourcing"
    finish(db, r, user, "sourcing", f"{body.qty} from {s.name}" + (f", ref {o.reference}" if o.reference else "")
           + (f", expected {o.expected_date}" if o.expected_date else ""), body.qty)
    audit(db, user, "placed sourcing order", f"{r.ref} {s.name}")
    db.commit()
    return request_out(db, r, user, detail=True)


def get_order(db, order_id):
    o = db.get(SourcingOrder, order_id)
    if not o:
        raise HTTPException(404, "No such sourcing order")
    return o


class OrderUpdateIn(BaseModel):
    expected_date: str = ""
    status: str = ""
    note: str = Field(default="", max_length=400)


@router.post("/sourcing/{order_id}/update")
def update_order(order_id: int, body: OrderUpdateIn, db=Depends(get_db), user=Depends(require(*OPS))):
    o = get_order(db, order_id)
    r = ops_request(db, o.request_id, user)
    if o.status in ("received", "cancelled"):
        raise HTTPException(409, "This order is closed")
    notes = []
    if body.expected_date:
        o.expected_date = r.expected_date = valid_date(body.expected_date, "Expected date")
        o.delay_notified = False
        notes.append(f"expected {o.expected_date}")
    if body.status:
        if body.status not in ("delayed", "cancelled", "ordered"):
            raise HTTPException(400, "Unknown order status")
        if body.status == "cancelled":
            if not body.note.strip():
                raise HTTPException(400, "Give the reason for cancelling the order")
            if o.qty_arrived > o.qty_accepted + o.qty_rejected:
                raise HTTPException(409, "Inspect the items that already arrived first")
            r.qty_sourced -= o.qty_ordered - o.qty_accepted - o.qty_rejected
        o.status = body.status
        notes.append(body.status)
        if body.status == "delayed":
            tell(db, [r.created_by] + ([r.decided_by] if r.decided_by else []),
                 f"{r.ref} {r.item_name} is delayed" + (f", now expected {o.expected_date}" if o.expected_date else ""), r.id)
    o.updated_at = now()
    finish(db, r, user, "sourcing updated", ", ".join(notes) + (f": {body.note.strip()}" if body.note.strip() else ""))
    db.commit()
    return request_out(db, r, user, detail=True)


class ArriveIn(BaseModel):
    qty: int = Field(ge=1, le=10000)
    note: str = Field(default="", max_length=400)


@router.post("/sourcing/{order_id}/arrive")
def mark_arrived(order_id: int, body: ArriveIn, db=Depends(get_db), user=Depends(require(*OPS))):
    o = get_order(db, order_id)
    r = ops_request(db, o.request_id, user)
    if o.status not in ("ordered", "delayed", "arrived"):
        raise HTTPException(409, "This order is closed")
    if o.qty_arrived + body.qty > o.qty_ordered:
        raise HTTPException(409, f"Only {o.qty_ordered - o.qty_arrived} more are expected on this order")
    o.qty_arrived += body.qty
    o.status, o.updated_at = "arrived", now()
    log(db, r, user, "arrived", f"{body.qty} arrived from the supplier, awaiting inspection. {body.note}".strip(), body.qty)
    tell(db, ops_ids(db), f"Arrived, needs inspection: {body.qty} x {r.item_name} for {r.ref}", r.id)
    db.commit()
    return request_out(db, r, user, detail=True)


class InspectIn(BaseModel):
    accepted: int = Field(ge=0, le=10000)
    rejected: int = Field(default=0, ge=0, le=10000)
    note: str = Field(min_length=2, max_length=400)
    asset_tags: list[str] = Field(default_factory=list, max_length=200)
    inventory_id: int | None = None


@router.post("/sourcing/{order_id}/inspect")
def inspect(order_id: int, body: InspectIn, db=Depends(get_db), user=Depends(require(*OPS))):
    """Record the inspection. Accepted units enter stock and are held for this request; rejected ones are not stocked."""
    o = get_order(db, order_id)
    r = ops_request(db, o.request_id, user)
    pending = o.qty_arrived - o.qty_accepted - o.qty_rejected
    if body.accepted + body.rejected == 0 or body.accepted + body.rejected > pending:
        raise HTTPException(409, f"{pending} arrived item(s) are waiting for inspection")
    if body.accepted:
        item = db.get(InventoryItem, body.inventory_id or r.inventory_id) if (body.inventory_id or r.inventory_id) else None
        if not item:
            matches = stock_matches(db, r)
            item = matches[0] if matches else None
        if not item:  # first time this item is stocked
            c = db.get(EquipmentCatalogItem, r.catalog_id) if r.catalog_id else None
            item = InventoryItem(code="tmp-" + secrets.token_hex(6), catalog_id=r.catalog_id, name=r.item_name,
                                 category=r.category, tracking=c.tracking if c else "quantity",
                                 unit=c.unit if c else "unit", supplier_id=o.supplier_id)
            db.add(item)
            db.flush()
            item.code = f"INV-{item.id:04d}"
        if r.inventory_id and r.inventory_id != item.id:
            raise HTTPException(409, "This request draws from another stock item")
        move(db, item, OUTSIDE, "reserved", body.accepted, user, "receive", r,
             f"Received from supplier for {r.ref}: {body.note}", tags=body.asset_tags or None)
        r.inventory_id = item.id
        r.qty_reserved += body.accepted
        r.qty_received += body.accepted
    o.qty_accepted += body.accepted
    o.qty_rejected += body.rejected
    o.inspection_note = body.note.strip()
    if body.rejected:
        r.qty_sourced -= body.rejected  # needs sourcing again
    if o.qty_accepted + o.qty_rejected >= o.qty_ordered:
        o.status = "received"
    elif o.qty_arrived == o.qty_accepted + o.qty_rejected:
        o.status = "ordered"
    o.updated_at = now()
    finish(db, r, user, "inspected", f"{body.accepted} accepted, {body.rejected} rejected: {body.note.strip()}",
           body.accepted)
    db.commit()
    return request_out(db, r, user, detail=True)


class DispatchIn(BaseModel):
    idem_key: str = Field(min_length=8, max_length=64)
    qty: int = Field(ge=1, le=10000)
    destination: str = Field(min_length=2, max_length=120)
    handled_by: str = Field(min_length=2, max_length=120)


@router.post("/requests/{request_id}/dispatch")
def dispatch(request_id: int, body: DispatchIn, db=Depends(get_db), user=Depends(require(*OPS))):
    existing = db.scalar(select(Dispatch).where(Dispatch.idem_key == body.idem_key))
    if existing:
        return {"dispatch": dispatch_out(db, existing, user), "duplicate": True}
    r = ops_request(db, request_id, user)
    if body.qty > r.qty_reserved:
        raise HTTPException(409, f"Only {r.qty_reserved} reserved and ready to dispatch")
    item = db.get(InventoryItem, r.inventory_id)
    if item.condition == "unsafe":
        raise HTTPException(409, "This item is marked unsafe and cannot be dispatched")
    to = "in_service" if item.tracking == "asset" else OUTSIDE  # consumables leave stores for the department
    tags = move(db, item, "reserved", to, body.qty, user, "dispatch", r, f"To {body.destination}", department=r.department)
    d = Dispatch(idem_key=body.idem_key, request_id=r.id, inventory_id=item.id, qty=body.qty,
                 asset_tags=",".join(tags), destination=body.destination.strip(), handled_by=body.handled_by.strip(),
                 dispatched_by=user.id)
    db.add(d)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Dispatch).where(Dispatch.idem_key == body.idem_key))
        return {"dispatch": dispatch_out(db, existing, user), "duplicate": True}
    r.qty_reserved -= body.qty
    r.qty_dispatched += body.qty
    finish(db, r, user, "dispatched", f"{body.qty} to {d.destination}, carried by {d.handled_by}"
           + (f" ({d.asset_tags})" if d.asset_tags else ""), body.qty)
    audit(db, user, "dispatched equipment", f"{r.ref} x{body.qty}")
    db.commit()
    return {"dispatch": dispatch_out(db, d, user), "duplicate": False, "request": request_out(db, r, user)}


class ConfirmIn(BaseModel):
    qty_delivered: int = Field(ge=1, le=10000)
    received_by: str = Field(min_length=2, max_length=120)
    note: str = Field(default="", max_length=400)


@router.post("/dispatches/{dispatch_id}/confirm")
def confirm_delivery(dispatch_id: int, body: ConfirmIn, db=Depends(get_db), user=Depends(require(*ANY))):
    d = db.get(Dispatch, dispatch_id)
    r = db.get(EquipmentRequest, d.request_id) if d else None
    if not d or not can_receive(user, r):
        raise HTTPException(404, "No such dispatch for your department")
    if d.status != "in_transit":
        raise HTTPException(409, "This dispatch is already confirmed")
    if body.qty_delivered > d.qty:
        raise HTTPException(400, f"This dispatch carried {d.qty}")
    d.qty_delivered, d.received_by, d.confirmed_by = body.qty_delivered, body.received_by.strip(), user.id
    d.delivered_at, d.status = now(), "delivered" if body.qty_delivered == d.qty else "short"
    short = d.qty - body.qty_delivered
    r.qty_delivered += body.qty_delivered
    if short:  # units that did not arrive are counted as dispatched but not delivered; stores must follow up
        tell(db, ops_ids(db), f"Short delivery on {r.ref}: {short} of {d.qty} not received", r.id)
    finish(db, r, user, "delivery confirmed", f"{body.qty_delivered} of {d.qty} received by {d.received_by}"
           + (f". {body.note.strip()}" if body.note.strip() else ""), body.qty_delivered)
    db.commit()
    return request_out(db, r, user, detail=True)


class ReturnIn(BaseModel):
    qty: int = Field(ge=1, le=10000)
    reason: str = Field(min_length=3, max_length=400)
    condition: str = "good"


@router.post("/requests/{request_id}/return")
def return_items(request_id: int, body: ReturnIn, db=Depends(get_db), user=Depends(require(*ANY))):
    r = get_request(db, request_id, user)
    if not can_receive(user, r):
        raise HTTPException(403, "Only the department or stores can record a return")
    if body.condition not in ("good", "damaged"):
        raise HTTPException(400, "Condition is good or damaged")
    if body.qty > r.qty_delivered:
        raise HTTPException(409, f"Only {r.qty_delivered} were delivered")
    item = db.get(InventoryItem, r.inventory_id)
    frm = "in_service" if item.tracking == "asset" else OUTSIDE
    to = "available" if body.condition == "good" else "damaged"
    move(db, item, frm, to, body.qty, user, "return", r, body.reason)
    r.qty_delivered -= body.qty
    r.qty_dispatched -= body.qty
    r.qty_returned += body.qty
    finish(db, r, user, "returned", f"{body.qty} returned ({body.condition}): {body.reason}", body.qty)
    tell(db, ops_ids(db) + [r.created_by], f"{r.ref}: {body.qty} x {r.item_name} returned to stores", r.id)
    db.commit()
    return request_out(db, r, user, detail=True)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=400)
    expected_date: str = ""


@router.post("/requests/{request_id}/cancel")
def cancel(request_id: int, body: ReasonIn, db=Depends(get_db), user=Depends(require(*ANY))):
    r = get_request(db, request_id, user)
    allowed = (r.created_by == user.id and r.dean_status != "approved") or user.role in OPS | DEAN
    if not allowed or r.status in ("fulfilled", "cancelled", "rejected"):
        raise HTTPException(403, "You cannot cancel this request")
    if r.qty_dispatched > r.qty_delivered:
        raise HTTPException(409, "Confirm or return the items in transit first")
    if r.qty_reserved:
        move(db, db.get(InventoryItem, r.inventory_id), "reserved", "available", r.qty_reserved, user, "release", r,
             "Request cancelled")
        r.qty_reserved = 0
    for o in db.scalars(select(SourcingOrder).where(SourcingOrder.request_id == r.id,
                                                    SourcingOrder.status.in_(["ordered", "delayed"]))):
        o.status = "cancelled"
    before = r.status
    r.status, r.closed_at = "cancelled", now()
    log(db, r, user, "cancelled", body.reason, None, before)
    tell(db, {r.created_by, r.decided_by, *ops_ids(db)} - {user.id, None}, f"{r.ref} {r.item_name} was cancelled: {body.reason}", r.id)
    db.commit()
    return request_out(db, r, user, detail=True)


@router.post("/requests/{request_id}/backorder")
def backorder(request_id: int, body: ReasonIn, db=Depends(get_db), user=Depends(require(*OPS))):
    r = ops_request(db, request_id, user)
    r.procurement_status = "backorder"
    if body.expected_date:
        r.expected_date = valid_date(body.expected_date, "Expected date")
    finish(db, r, user, "backordered", body.reason + (f", expected {r.expected_date}" if r.expected_date else ""))
    db.commit()
    return request_out(db, r, user, detail=True)


# ---------- inventory ----------

def inventory_out(db, i, detail=False):
    s = db.get(Supplier, i.supplier_id) if i.supplier_id else None
    out = {"id": i.id, "code": i.code, "name": i.name, "category": i.category, "model": i.model, "tracking": i.tracking,
           "unit": i.unit, "total": i.total, "available": i.available, "reserved": i.reserved,
           "in_service": i.in_service, "maintenance": i.maintenance, "damaged": i.damaged, "min_stock": i.min_stock,
           "low": bool(i.min_stock and i.available < i.min_stock), "location": i.location, "department": i.department,
           "supplier": s.name if s else "", "supplier_id": i.supplier_id, "warranty": i.warranty,
           "last_maintenance": i.last_maintenance, "next_maintenance": i.next_maintenance, "condition": i.condition,
           "service_due": bool(i.next_maintenance and i.next_maintenance <= (now().date() + dt.timedelta(days=7)).isoformat()),
           "clinical_use": i.condition != "unsafe" and i.available > 0}
    if detail:
        out["assets"] = [{"id": a.id, "asset_tag": a.asset_tag, "serial": a.serial, "state": a.state,
                          "department": a.department, "request": a.request_id, "condition": a.condition,
                          "warranty_until": a.warranty_until, "next_maintenance": a.next_maintenance}
                         for a in db.scalars(select(EquipmentAsset).where(EquipmentAsset.inventory_id == i.id)
                                             .order_by(EquipmentAsset.asset_tag))]
        out["transactions"] = [{"kind": t.kind, "qty": t.qty, "from": t.from_state, "to": t.to_state,
                                "tags": t.asset_tags, "who": uname(db, t.user_id), "note": t.note, "at": iso(t.at),
                                "request_id": t.request_id}
                               for t in db.scalars(select(StockTransaction).where(StockTransaction.inventory_id == i.id)
                                                   .order_by(StockTransaction.id.desc()).limit(100))]
    return out


@router.get("/inventory")
def inventory(q: str = "", category: str = "", low: bool = False, db=Depends(get_db), user=Depends(require(*VIEW_ALL))):
    query = select(InventoryItem)
    if q.strip():
        term = f"%{q.strip().lower()}%"
        query = query.where(or_(func.lower(InventoryItem.name).like(term), func.lower(InventoryItem.code).like(term),
                                func.lower(InventoryItem.model).like(term)))
    if category:
        query = query.where(InventoryItem.category == category)
    rows = db.scalars(query.order_by(InventoryItem.name)).all()
    if low:
        rows = [i for i in rows if i.min_stock and i.available < i.min_stock]
    return [inventory_out(db, i) for i in rows]


@router.get("/inventory/{item_id}")
def inventory_detail(item_id: int, db=Depends(get_db), user=Depends(require(*VIEW_ALL))):
    i = db.get(InventoryItem, item_id)
    if not i:
        raise HTTPException(404, "No such inventory item")
    return inventory_out(db, i, detail=True)


class InventoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    catalog_id: int | None = None
    category: str = Field(default="", max_length=60)
    model: str = Field(default="", max_length=80)
    tracking: str = "quantity"
    unit: str = Field(default="unit", max_length=20)
    min_stock: int = Field(default=0, ge=0, le=100000)
    location: str = Field(default="Central stores", max_length=80)
    department: str = Field(default="", max_length=60)
    supplier_id: int | None = None
    warranty: str = Field(default="", max_length=120)
    next_maintenance: str = ""
    initial_qty: int = Field(default=0, ge=0, le=100000)
    asset_tags: list[str] = Field(default_factory=list, max_length=500)


@router.post("/inventory")
def add_inventory(body: InventoryIn, db=Depends(get_db), user=Depends(require(*OPS))):
    if body.tracking not in ("asset", "quantity"):
        raise HTTPException(400, "Tracking is asset or quantity")
    i = InventoryItem(code="tmp-" + secrets.token_hex(6), catalog_id=body.catalog_id, name=body.name.strip(),
                      category=body.category.strip(), model=body.model.strip(), tracking=body.tracking,
                      unit=body.unit.strip() or "unit", min_stock=body.min_stock, location=body.location.strip(),
                      department=body.department.strip(), supplier_id=body.supplier_id, warranty=body.warranty.strip(),
                      next_maintenance=valid_date(body.next_maintenance, "Next maintenance"))
    db.add(i)
    db.flush()
    i.code = f"INV-{i.id:04d}"
    if body.initial_qty:
        move(db, i, OUTSIDE, "available", body.initial_qty, user, "receive", None, "Opening stock",
             tags=body.asset_tags or None)
    audit(db, user, "added inventory item", f"{i.code} {i.name}")
    bump(db, "equipment")
    db.commit()
    return inventory_out(db, i, detail=True)


class InventoryUpdateIn(BaseModel):
    model: str | None = Field(default=None, max_length=80)
    min_stock: int | None = Field(default=None, ge=0, le=100000)
    location: str | None = Field(default=None, max_length=80)
    department: str | None = Field(default=None, max_length=60)
    supplier_id: int | None = None
    warranty: str | None = Field(default=None, max_length=120)
    next_maintenance: str | None = None


@router.post("/inventory/{item_id}")
def update_inventory(item_id: int, body: InventoryUpdateIn, db=Depends(get_db), user=Depends(require(*OPS))):
    i = db.get(InventoryItem, item_id)
    if not i:
        raise HTTPException(404, "No such inventory item")
    for key, value in body.model_dump(exclude_unset=True).items():
        if key == "next_maintenance":
            value = valid_date(value or "", "Next maintenance")
            i.service_notified_for = ""
        setattr(i, key, value.strip() if isinstance(value, str) else value)
    i.updated_at = now()
    check_low_stock(db, i)
    audit(db, user, "updated inventory item", i.code)
    bump(db, "equipment")
    db.commit()
    return inventory_out(db, i, detail=True)


class AdjustIn(BaseModel):
    kind: str  # receive, damage, write_off, repair
    qty: int = Field(ge=1, le=100000)
    note: str = Field(min_length=3, max_length=300)
    asset_tags: list[str] = Field(default_factory=list, max_length=500)


ADJUST = {"receive": (OUTSIDE, "available"), "damage": ("available", "damaged"), "write_off": ("damaged", OUTSIDE),
          "repair": ("damaged", "maintenance")}


@router.post("/inventory/{item_id}/adjust")
def adjust(item_id: int, body: AdjustIn, db=Depends(get_db), user=Depends(require(*OPS))):
    i = db.get(InventoryItem, item_id)
    if not i:
        raise HTTPException(404, "No such inventory item")
    if body.kind not in ADJUST:
        raise HTTPException(400, "Unknown stock adjustment")
    frm, to = ADJUST[body.kind]
    move(db, i, frm, to, body.qty, user, body.kind, None, body.note, tags=body.asset_tags or None)
    audit(db, user, f"stock {body.kind}", f"{i.code} x{body.qty}")
    bump(db, "equipment")
    db.commit()
    return inventory_out(db, i, detail=True)


@router.get("/transactions")
def transactions(db=Depends(get_db), user=Depends(require(*VIEW_ALL))):
    items = {i.id: i for i in db.scalars(select(InventoryItem))}
    rows = db.scalars(select(StockTransaction).order_by(StockTransaction.id.desc()).limit(150)).all()
    return [{"item": items[t.inventory_id].name if t.inventory_id in items else "", "code": items[t.inventory_id].code
             if t.inventory_id in items else "", "kind": t.kind, "qty": t.qty, "from": t.from_state, "to": t.to_state,
             "tags": t.asset_tags, "who": uname(db, t.user_id), "note": t.note, "at": iso(t.at)} for t in rows]


# ---------- maintenance ----------

TICKET_STEPS = ["reported", "assigned", "scheduled", "in_progress", "awaiting_verification", "completed"]
TICKET_LABEL = {"reported": "Reported", "assigned": "Technician assigned", "scheduled": "Scheduled",
                "in_progress": "Repair in progress", "awaiting_verification": "Awaiting verification",
                "completed": "Back in service", "cancelled": "Cancelled"}


def ticket_out(db, t, user):
    s = db.get(Supplier, t.supplier_id) if t.supplier_id else None
    item = db.get(InventoryItem, t.inventory_id) if t.inventory_id else None
    asset = db.get(EquipmentAsset, t.asset_id) if t.asset_id else None
    events = db.scalars(select(MaintenanceEvent).where(MaintenanceEvent.ticket_id == t.id).order_by(MaintenanceEvent.id))
    show_cost = user.role in OPS | {"dean", "chairman"}
    return {"id": t.id, "ref": t.ref, "item_name": t.item_name, "inventory_code": item.code if item else "",
            "asset_tag": asset.asset_tag if asset else "", "qty": t.qty, "qty_held": t.qty_held, "department": t.department,
            "reported_by": uname(db, t.reported_by), "issue": t.issue, "unsafe": t.unsafe, "kind": t.kind,
            "status": t.status, "status_label": TICKET_LABEL.get(t.status, t.status), "technician": t.technician,
            "provider": s.name if s else "", "scheduled_for": t.scheduled_for, "findings": t.findings,
            "parts_used": t.parts_used, "cost": t.cost if show_cost else None, "created_at": iso(t.created_at),
            "updated_at": iso(t.updated_at), "completed_at": iso(t.completed_at), "request_id": t.request_id,
            "verification_note": t.verification_note, "verified_by": uname(db, t.verified_by),
            "can_manage": user.role in OPS and t.status not in ("completed", "cancelled"),
            "history": [{"who": uname(db, e.user_id) or "System", "action": e.action, "note": e.note, "at": iso(e.at)}
                        for e in events]}


def hold_for_service(db, t, item, user):
    """Take the units out of use while they are serviced. Unsafe equipment is never left as available."""
    if not item or t.qty_held >= t.qty:
        return
    need = t.qty - t.qty_held
    tags = None
    if t.asset_id:
        a = db.get(EquipmentAsset, t.asset_id)
        tags = [a.asset_tag]
        frm = a.state
    else:
        frm = "in_service" if item.in_service >= need and t.department else "available"
        if getattr(item, frm) < need:
            frm = "available" if frm == "in_service" else "in_service"
    if frm not in ("available", "in_service", "reserved") or getattr(item, frm) < need:
        return
    move(db, item, frm, "maintenance", need, user, "maintenance_out", None, f"{t.ref}: {t.issue[:120]}", tags=tags)
    t.qty_held += need
    t.held_from = frm if frm != "reserved" else "available"


class TicketIn(BaseModel):
    idem_key: str = Field(min_length=8, max_length=64)
    inventory_id: int | None = None
    asset_tag: str = Field(default="", max_length=40)
    item_name: str = Field(default="", max_length=120)
    qty: int = Field(default=1, ge=1, le=1000)
    issue: str = Field(min_length=5, max_length=600)
    unsafe: bool = False
    kind: str = "repair"


@router.post("/maintenance")
def report_issue(body: TicketIn, db=Depends(get_db), user=Depends(require(*(DEPT_STAFF | OPS)))):
    existing = db.scalar(select(MaintenanceTicket).where(MaintenanceTicket.idem_key == body.idem_key))
    if existing:
        return ticket_out(db, existing, user)
    if body.kind not in ("repair", "servicing", "calibration", "inspection"):
        raise HTTPException(400, "Unknown maintenance type")
    asset = item = None
    if body.asset_tag.strip():
        asset = db.scalar(select(EquipmentAsset).where(EquipmentAsset.asset_tag == body.asset_tag.strip().upper()))
        if not asset:
            raise HTTPException(404, "No equipment with that asset tag")
        item = db.get(InventoryItem, asset.inventory_id)
    elif body.inventory_id:
        item = db.get(InventoryItem, body.inventory_id)
        if not item:
            raise HTTPException(404, "No such inventory item")
    name = item.name if item else body.item_name.strip()
    if len(name) < 2:
        raise HTTPException(400, "Say which equipment needs attention")
    t = MaintenanceTicket(ref="tmp-" + secrets.token_hex(6), idem_key=body.idem_key, inventory_id=item.id if item else None,
                          asset_id=asset.id if asset else None, item_name=name, qty=1 if asset else body.qty,
                          department=user.department or (asset.department if asset else ""), reported_by=user.id,
                          issue=body.issue.strip(), unsafe=body.unsafe, kind=body.kind)
    db.add(t)
    db.flush()
    t.ref = f"MT-{t.created_at.year}-{t.id:04d}"
    db.add(MaintenanceEvent(ticket_id=t.id, user_id=user.id, action="reported",
                            note=("UNSAFE. " if body.unsafe else "") + t.issue))
    if body.unsafe and item:
        hold_for_service(db, t, item, user)
        if asset:
            asset.condition = "unsafe"
    tell(db, ops_ids(db), f"{'UNSAFE equipment' if body.unsafe else 'Maintenance request'} {t.ref}: {name}"
                          f"{' (' + t.department + ')' if t.department else ''}: {t.issue[:100]}", f"mt{t.id}")
    audit(db, user, "reported equipment issue", f"{t.ref} {name}")
    db.commit()
    return ticket_out(db, t, user)


@router.get("/maintenance")
def list_tickets(status: str = "", db=Depends(get_db), user=Depends(require(*ANY))):
    q = select(MaintenanceTicket)
    if user.role in DEPT_STAFF:
        q = q.where(or_(MaintenanceTicket.department == user.department, MaintenanceTicket.reported_by == user.id))
    if status == "open":
        q = q.where(MaintenanceTicket.status.not_in(["completed", "cancelled"]))
    elif status:
        q = q.where(MaintenanceTicket.status == status)
    rows = db.scalars(q.order_by(MaintenanceTicket.unsafe.desc(), MaintenanceTicket.id.desc()).limit(150)).all()
    return [ticket_out(db, t, user) for t in rows]


class TicketUpdateIn(BaseModel):
    action: str  # assign, schedule, start, findings, complete, verify, cancel
    technician: str = Field(default="", max_length=120)
    supplier_id: int | None = None
    provider_name: str = Field(default="", max_length=120)
    scheduled_for: str = ""
    findings: str = Field(default="", max_length=600)
    parts_used: str = Field(default="", max_length=300)
    cost: float | None = Field(default=None, ge=0, le=100_000_000)
    note: str = Field(default="", max_length=400)


@router.post("/maintenance/{ticket_id}/update")
def update_ticket(ticket_id: int, body: TicketUpdateIn, db=Depends(get_db), user=Depends(require(*OPS))):
    t = db.get(MaintenanceTicket, ticket_id)
    if not t:
        raise HTTPException(404, "No such maintenance ticket")
    if t.status in ("completed", "cancelled"):
        raise HTTPException(409, "This ticket is closed")
    item = db.get(InventoryItem, t.inventory_id) if t.inventory_id else None
    a = body.action
    note = body.note.strip()
    if a == "assign":
        if not body.technician.strip() and not (body.supplier_id or body.provider_name.strip()):
            raise HTTPException(400, "Name the technician or the service provider")
        t.technician = body.technician.strip() or t.technician
        if body.supplier_id or body.provider_name.strip():
            t.supplier_id = find_supplier(db, body.supplier_id, body.provider_name).id
        t.status = "assigned" if t.status == "reported" else t.status
        note = note or f"Assigned to {t.technician or db.get(Supplier, t.supplier_id).name}"
    elif a == "schedule":
        t.scheduled_for = valid_date(body.scheduled_for, "Scheduled date")
        if not t.scheduled_for:
            raise HTTPException(400, "Choose a date")
        t.status = "scheduled" if TICKET_STEPS.index(t.status) < 2 else t.status
        note = note or f"Scheduled for {t.scheduled_for}"
    elif a == "start":
        hold_for_service(db, t, item, user)
        t.status = "in_progress"
        note = note or "Work started; equipment marked unavailable"
    elif a == "findings":
        if not (body.findings.strip() or body.parts_used.strip() or body.cost is not None):
            raise HTTPException(400, "Record findings, parts or cost")
        if body.findings.strip():
            t.findings = body.findings.strip()
        if body.parts_used.strip():
            t.parts_used = body.parts_used.strip()
        if body.cost is not None:
            t.cost = body.cost
        note = note or "Inspection findings recorded"
    elif a == "complete":
        hold_for_service(db, t, item, user)
        if not (t.findings or body.findings.strip()):
            raise HTTPException(400, "Record the inspection findings before completing the repair")
        t.findings = body.findings.strip() or t.findings
        t.status = "awaiting_verification"
        note = note or "Repair finished; waiting for safety verification before return to service"
    elif a == "verify":
        if t.status != "awaiting_verification":
            raise HTTPException(409, "Finish the repair first")
        if len(note) < 5:
            raise HTTPException(400, "Describe the verification that was done")
        if item and t.qty_held:
            back = t.held_from or "available"
            tags = [db.get(EquipmentAsset, t.asset_id).asset_tag] if t.asset_id else None
            move(db, item, "maintenance", back, t.qty_held, user, "maintenance_in", None, f"{t.ref} verified: {note}",
                 department=t.department, tags=tags)
            t.qty_held = 0
        stamp = today()
        nxt = (now().date() + dt.timedelta(days=SERVICE_DAYS)).isoformat()
        if item:
            item.last_maintenance, item.next_maintenance, item.service_notified_for = stamp, nxt, ""
            if item.condition == "unsafe":
                item.condition = "good"
        if t.asset_id:
            asset = db.get(EquipmentAsset, t.asset_id)
            asset.condition, asset.last_maintenance, asset.next_maintenance = "good", stamp, nxt
        t.status, t.completed_at, t.verified_by, t.verification_note = "completed", now(), user.id, note
        tell(db, [t.reported_by], f"{t.ref} {t.item_name} is repaired, verified and back in service", f"mt{t.id}")
        if t.department:
            dept_staff = list(db.scalars(select(User.id).where(User.department == t.department, User.role.in_(DEPT_STAFF),
                                                               User.active == True)))  # noqa: E712
            tell(db, dept_staff, f"{t.item_name} is ready for use again ({t.ref})", f"mt{t.id}")
    elif a == "cancel":
        if len(note) < 3:
            raise HTTPException(400, "Give the reason for cancelling")
        if t.unsafe and t.qty_held:
            raise HTTPException(409, "Unsafe equipment can only return to service through verification")
        if item and t.qty_held:
            move(db, item, "maintenance", t.held_from or "available", t.qty_held, user, "maintenance_in", None,
                 f"{t.ref} cancelled: {note}", department=t.department)
            t.qty_held = 0
        t.status = "cancelled"
    else:
        raise HTTPException(400, "Unknown action")
    t.updated_at = now()
    db.add(MaintenanceEvent(ticket_id=t.id, user_id=user.id, action=a, note=note[:400]))
    if t.request_id:
        r = db.get(EquipmentRequest, t.request_id)
        finish(db, r, user, f"service {a}", f"{t.ref}: {note}")
    if a in ("schedule", "start") and t.reported_by:
        tell(db, [t.reported_by], f"{t.ref} {t.item_name}: {TICKET_LABEL[t.status]}"
                                  + (f" for {t.scheduled_for}" if a == "schedule" else ""), f"mt{t.id}")
    bump(db, "equipment")
    audit(db, user, f"maintenance {a}", t.ref)
    db.commit()
    return ticket_out(db, t, user)


@router.post("/requests/{request_id}/schedule-service")
def schedule_service(request_id: int, body: TicketUpdateIn, db=Depends(get_db), user=Depends(require(*OPS))):
    """Open a maintenance ticket for an approved repair or servicing request."""
    r = ops_request(db, request_id, user)
    if r.request_type not in ("repair", "servicing", "replacement"):
        raise HTTPException(409, "Service is scheduled for repair or servicing requests")
    t = MaintenanceTicket(ref="tmp-" + secrets.token_hex(6), idem_key=secrets.token_hex(16), request_id=r.id,
                          inventory_id=None, item_name=r.item_name, qty=r.qty_approved, department=r.department,
                          reported_by=r.created_by, issue=r.justification[:600],
                          kind="servicing" if r.request_type == "servicing" else "repair",
                          technician=body.technician.strip(), scheduled_for=valid_date(body.scheduled_for, "Scheduled date"))
    if body.supplier_id or body.provider_name.strip():
        t.supplier_id = find_supplier(db, body.supplier_id, body.provider_name).id
    t.status = "scheduled" if t.scheduled_for else ("assigned" if t.technician or t.supplier_id else "reported")
    db.add(t)
    db.flush()
    t.ref = f"MT-{t.created_at.year}-{t.id:04d}"
    db.add(MaintenanceEvent(ticket_id=t.id, user_id=user.id, action="scheduled from request",
                            note=f"{r.ref}" + (f" on {t.scheduled_for}" if t.scheduled_for else "")))
    finish(db, r, user, "service scheduled", f"{t.ref}" + (f" on {t.scheduled_for}" if t.scheduled_for else ""))
    db.commit()
    return request_out(db, r, user, detail=True)


# ---------- overview ----------

@router.get("/overview")
def overview(db=Depends(get_db), user=Depends(require(*VIEW_ALL))):
    rows = db.scalars(select(EquipmentRequest)).all()
    count = {}
    for r in rows:
        count[r.status] = count.get(r.status, 0) + 1
    open_rows = [r for r in rows if r.status not in ("fulfilled", "cancelled", "rejected")]
    by_dept = {}
    for r in open_rows:
        d = by_dept.setdefault(r.department, {"department": r.department, "open": 0, "units_outstanding": 0,
                                              "awaiting_dean": 0, "critical": 0})
        d["open"] += 1
        d["units_outstanding"] += max(0, (r.qty_approved or r.quantity) - r.qty_delivered)
        d["awaiting_dean"] += r.status == "pending_dean"
        d["critical"] += r.urgency == "critical"
    delayed = db.scalars(select(SourcingOrder).where(or_(SourcingOrder.status == "delayed", (
        (SourcingOrder.status == "ordered") & (SourcingOrder.expected_date != "") & (SourcingOrder.expected_date < today()))))).all()
    tickets = db.scalars(select(MaintenanceTicket).where(MaintenanceTicket.status.not_in(["completed", "cancelled"]))).all()
    items = db.scalars(select(InventoryItem)).all()
    soon = (now().date() + dt.timedelta(days=7)).isoformat()
    return {
        "stages": {
            "pending_dean": count.get("pending_dean", 0) + count.get("clarification", 0),
            "awaiting_sourcing": count.get("approved", 0) + count.get("sourcing_required", 0),
            "procurement": count.get("sourcing", 0) + count.get("backorder", 0),
            "ready_for_dispatch": count.get("ready_for_dispatch", 0),
            "in_transit": count.get("dispatched", 0),
            "partial": count.get("partially_fulfilled", 0),
            "delayed": len({o.request_id for o in delayed}),
            "completed": count.get("fulfilled", 0),
            "servicing": count.get("servicing", 0) + len(tickets),
        },
        "by_status": count,
        "by_department": sorted(by_dept.values(), key=lambda d: -d["units_outstanding"]),
        "delayed": [{**sourcing_out(db, o), "request": db.get(EquipmentRequest, o.request_id).ref} for o in delayed],
        "maintenance_open": len(tickets), "unsafe_open": sum(1 for t in tickets if t.unsafe),
        "low_stock": [inventory_out(db, i) for i in items if i.min_stock and i.available < i.min_stock],
        "service_due": [inventory_out(db, i) for i in items if i.next_maintenance and i.next_maintenance <= soon],
    }


def badge(db, user):
    def n(*where):
        return db.scalar(select(func.count()).select_from(EquipmentRequest).where(*where)) or 0
    if user.role == "dean":
        return n(EquipmentRequest.status == "pending_dean")
    if user.role in OPS:
        return n(EquipmentRequest.status.in_(["approved", "sourcing_required", "ready_for_dispatch"])) + (db.scalar(
            select(func.count()).select_from(SourcingOrder).where(SourcingOrder.status == "arrived")) or 0)
    if user.role == "doctor":
        return n(EquipmentRequest.created_by == user.id, or_(EquipmentRequest.status == "clarification",
                                                             EquipmentRequest.clarification_from.is_not(None))) + (db.scalar(
            select(func.count()).select_from(Dispatch).join(EquipmentRequest, Dispatch.request_id == EquipmentRequest.id)
            .where(Dispatch.status == "in_transit", EquipmentRequest.department == user.department)) or 0)
    if user.role == "nurse":
        return db.scalar(select(func.count()).select_from(Dispatch).join(EquipmentRequest, Dispatch.request_id == EquipmentRequest.id)
                         .where(Dispatch.status == "in_transit", EquipmentRequest.department == user.department)) or 0
    return 0


def run_checks(db):
    """Background pass: delayed deliveries and maintenance coming due."""
    current = today()
    changed = False
    for o in db.scalars(select(SourcingOrder).where(SourcingOrder.status.in_(["ordered", "delayed"]),
                                                    SourcingOrder.expected_date != "",
                                                    SourcingOrder.expected_date < current,
                                                    SourcingOrder.delay_notified == False)).all():  # noqa: E712
        r = db.get(EquipmentRequest, o.request_id)
        o.status, o.delay_notified = "delayed", True
        tell(db, ops_ids(db), f"Delivery overdue: {r.ref} {r.item_name} was expected {o.expected_date}", r.id)
        tell(db, [r.created_by], f"{r.ref} {r.item_name} is delayed past {o.expected_date}", r.id)
        log(db, r, None, "delayed", f"Expected {o.expected_date}, not received")
        changed = True
    soon = (now().date() + dt.timedelta(days=3)).isoformat()
    for i in db.scalars(select(InventoryItem).where(InventoryItem.next_maintenance != "",
                                                    InventoryItem.next_maintenance <= soon)).all():
        if i.service_notified_for != i.next_maintenance:
            i.service_notified_for = i.next_maintenance
            tell(db, ops_ids(db), f"Maintenance due {i.next_maintenance}: {i.name} ({i.code})", f"inv{i.id}")
            changed = True
    if changed:
        db.commit()
