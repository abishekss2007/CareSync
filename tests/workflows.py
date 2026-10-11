"""End-to-end checks for the emergency and equipment workflows. Run against freshly seeded demo data:

    LIVE_CHECK_SECONDS=2 python -m uvicorn app.main:app --port 8000
    python tests/workflows.py [base_url]

It sets a short emergency response policy so escalation and retries can be observed, then restores it.
"""
import json
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
failures = []


def call(method, path, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as res:
            raw = res.read().decode()
            return res.status, json.loads(raw) if raw.startswith(("{", "[")) else raw
    except urllib.error.HTTPError as err:
        raw = err.read().decode() or "{}"
        return err.code, json.loads(raw) if raw.startswith("{") else raw


def check(label, condition, detail=""):
    print(("PASS  " if condition else "FAIL  ") + label + (f"  -> {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def signin(username):
    code, out = call("POST", "/api/demo/login", body={"username": username})
    assert code == 200, (username, out)
    return out["token"]


def key():
    return uuid.uuid4().hex


def wait_for(fn, seconds=30, step=1):
    end = time.time() + seconds
    while time.time() < end:
        out = fn()
        if out:
            return out
        time.sleep(step)
    return None


names = ["chairman", "dean", "admin", "stores.thomas", "dr.arjun", "dr.joseph", "dr.kavya", "dr.rahul", "nurse.priya",
         "nurse.deepa", "reception.ravi"]
tok = {n: signin(n) for n in names}
accounts = call("GET", "/api/demo/accounts")[1]
patient_login = next(a["username"] for a in accounts if a["role"] == "patient")
tok["patient"] = signin(patient_login)
me = {n: call("GET", "/api/me", tok[n])[1]["user"] for n in names}
ER = "/api/emergencies"
EQ = "/api/equipment"

# Shorter policy so escalation and retry can be observed within the test.
code, old_policy = call("GET", ER + "/policy/current", tok["chairman"])
check("dean cannot change the emergency policy",
      call("POST", ER + "/policy/current", tok["dean"], {**old_policy, "ack_seconds": 15})[0] == 403)
code, _ = call("POST", ER + "/policy/current", tok["admin"],
               {"ack_seconds": 15, "repeat_seconds": 600, "max_level": 2, "retry_seconds": 5, "max_attempts": 3})
check("administrator sets the response policy", code == 200)

print("\n-- Emergency workflow --")
# 1. A routine patient still follows the normal workflow
code, reg = call("POST", "/api/patients", tok["reception.ravi"], {"name": "Routine Patient", "age": 40, "gender": "Male"})
routine_pid = reg["patient"]["pid"]
code, tk = call("POST", "/api/visits", tok["reception.ravi"], {"pid": routine_pid, "department": "Cardiology",
                                                               "complaint": "Check-up"})
check("routine patient gets an ordinary token", code == 200 and tk["priority"] == "normal" and tk["token"].startswith("CAR-"))
code, urg = call("POST", "/api/patients", tok["reception.ravi"], {"name": "Urgent Patient", "age": 52, "gender": "Female"})
code, tk2 = call("POST", "/api/visits", tok["reception.ravi"], {"pid": urg["patient"]["pid"], "department": "Cardiology",
                                                                "complaint": "Chest tightness", "priority": "urgent"})
check("urgent token is accepted", code == 200 and tk2["priority"] == "urgent")
check("critical cannot be issued as an ordinary token", call("POST", "/api/visits", tok["reception.ravi"], {
    "pid": routine_pid, "department": "General Medicine", "priority": "critical"})[0] == 400)
q = call("GET", "/api/queue", tok["dr.arjun"])[1]["visits"]
waiting = [v for v in q if v["status"] == "waiting"]
check("urgent patient is ahead of routine patients in the queue", waiting and waiting[0]["priority"] == "urgent",
      [v["priority"] for v in waiting][:4])

# 4 (setup). Dr. Arjun starts a consultation and saves a draft before the emergency
first = waiting[0]
check("doctor starts a consultation", call("POST", f"/api/visits/{first['id']}/start", tok["dr.arjun"])[0] == 200)
draft = json.dumps({"diagnosis": "Unstable angina?", "notes": "ECG pending"})
check("doctor's consultation draft is saved", call("POST", f"/api/visits/{first['id']}/draft", tok["dr.arjun"],
                                                   {"draft": draft})[0] == 200)

# 2. Critical emergency, assigned to the doctor who is busy with that consultation
k = key()
body = {"idem_key": k, "new_patient": {"name": "Unknown Male", "age": 35, "gender": "Male"},
        "emergency_type": "Road traffic accident", "description": "Unconscious after bike crash, bleeding from scalp",
        "priority": "critical", "location": "Emergency bay 1", "team": "Emergency",
        "assigned_doctor_id": me["dr.arjun"]["id"]}
check("patient cannot raise an alert", call("POST", ER, tok["patient"], body)[0] == 403)
check("coordinator cannot raise an alert", call("POST", ER, tok["stores.thomas"], body)[0] == 403)
code, out = call("POST", ER, tok["reception.ravi"], body)
alert = out["alert"]
check("receptionist raises a critical emergency alert", code == 200 and alert["ern"].startswith("ER-") and out["pin"])
check("alert status moved to notification sent", alert["status"] == "notification_sent")

# 9. Duplicate clicks / network retries
code, again = call("POST", ER, tok["reception.ravi"], body)
check("repeated submit returns the same alert", code == 200 and again["duplicate"] and again["alert"]["id"] == alert["id"])
results = []
threads = [threading.Thread(target=lambda: results.append(call("POST", ER, tok["reception.ravi"], body))) for _ in range(5)]
[t.start() for t in threads]
[t.join() for t in threads]
check("five simultaneous retries create no new alert", all(r[0] == 200 and r[1]["alert"]["id"] == alert["id"] for r in results))
pid = alert["patient"]["pid"]
code, dup = call("POST", ER, tok["reception.ravi"], {**body, "idem_key": key(), "new_patient": None, "pid": pid})
check("second open alert for the same patient is refused", code == 409)
code, hist = call("GET", ER + "?scope=history", tok["chairman"])
check("only one alert exists for the patient", sum(1 for a in hist["alerts"] if a["patient"]["pid"] == pid) == 1)

# 3. Persisted notifications for every recipient group
def has_alert(name):
    n = call("GET", "/api/notifications", tok[name])[1]
    return any(i["kind"] == "emergency" and i["ref"] == str(alert["id"]) for i in n["items"])


for name in ["chairman", "dean", "admin", "reception.ravi", "dr.arjun", "dr.joseph"]:
    check(f"{name} has a persisted emergency notification", has_alert(name))
check("coordinator is not sent patient alerts", not has_alert("stores.thomas"))
check("unrelated department nurse is not alerted", not has_alert("nurse.deepa"))
admin_note = next(i for i in call("GET", "/api/notifications", tok["admin"])[1]["items"] if i["kind"] == "emergency")
check("administrator's notification hides the patient's name", "Unknown Male" not in admin_note["text"]
      and pid in admin_note["text"] and "CRITICAL EMERGENCY ALERT" in admin_note["text"])
dean_note = next(i for i in call("GET", "/api/notifications", tok["dean"])[1]["items"] if i["kind"] == "emergency")
check("notification carries type, arrival, doctor, location and status",
      all(x in dean_note["text"] for x in ["Road traffic accident", "arrived", "Dr. Arjun Menon", "Emergency bay 1",
                                          "Notification sent"]))

# 4. The busy doctor sees it on the dashboard banner
code, active = call("GET", ER + "/active", tok["dr.arjun"])
mine = next((a for a in active["alerts"] if a["id"] == alert["id"]), None)
check("assigned doctor's banner shows the alert while consulting", mine is not None and mine["must_ack"])
code, detail = call("GET", f"{ER}/{alert['id']}", tok["chairman"])
check("delivery is not claimed before the doctor's screen shows it",
      all(d["delivered_at"] is None for d in detail["deliveries"] if d["who"] == "Dr. Arjun Menon"))
check("doctor's app records the alert as received", call("POST", f"{ER}/{alert['id']}/received", tok["dr.arjun"])[0] == 200)
detail = call("GET", f"{ER}/{alert['id']}", tok["chairman"])[1]
check("receipt time is recorded for the assigned doctor", detail["received_at"] is not None and any(
    d["delivered_at"] for d in detail["deliveries"] if d["who"] == "Dr. Arjun Menon"))

# 10. Notification failure and recovery: the dean's app is offline, so delivery stays pending and is retried
def dean_attempts():
    d = call("GET", f"{ER}/{alert['id']}", tok["chairman"])[1]
    rows = [x for x in d["deliveries"] if x["who"] == "Dr. Meera Nair"]
    return rows and rows[0]["attempts"] > 1 and rows[0]["delivered_at"] is None
check("undelivered alert is retried while the recipient is offline", wait_for(dean_attempts, 20))
call("POST", f"{ER}/{alert['id']}/received", tok["dean"])
d = call("GET", f"{ER}/{alert['id']}", tok["chairman"])[1]
check("delivery is recorded once the recipient's app is back",
      all(x["delivered_at"] for x in d["deliveries"] if x["who"] == "Dr. Meera Nair"))

# 5. Escalation when nobody acknowledges within the policy
def escalated():
    d = call("GET", f"{ER}/{alert['id']}", tok["chairman"])[1]
    return d if d["escalation_level"] >= 1 else None
d = wait_for(escalated, 40)
check("unacknowledged alert escalates under the policy", d is not None and any(e["action"] == "escalated" for e in d["events"]))
check("escalation is tracked separately from delivery", d is not None and any(x["escalation"] for x in d["deliveries"]))

# 7. Acknowledging keeps the interrupted consultation
check("another doctor cannot acknowledge for the assigned doctor",
      call("POST", f"{ER}/{alert['id']}/ack", tok["dr.kavya"], {})[1].get("result") != "acknowledged")
code, ack = call("POST", f"{ER}/{alert['id']}/ack", tok["dr.arjun"], {"note": "On my way"})
check("assigned doctor acknowledges", code == 200 and ack["result"] == "acknowledged" and ack["alert"]["acknowledged_at"])
code, v = call("GET", f"/api/visits/{first['id']}", tok["dr.arjun"])
check("interrupted consultation is still open with its draft", code == 200 and v["status"] == "in_consultation"
      and v["draft"] == draft)
check("acknowledging twice changes nothing", call("POST", f"{ER}/{alert['id']}/ack", tok["dr.arjun"], {})[1]["result"] == "seen")

# Respond / assign backup and status tracking
code, re_assigned = call("POST", f"{ER}/{alert['id']}/assign", tok["reception.ravi"],
                         {"doctor_id": me["dr.joseph"]["id"], "note": "Dr. Arjun is mid-procedure"})
check("staff assign a backup emergency clinician", code == 200 and re_assigned["assigned_doctor"] == "Dr. Joseph Mathew"
      and re_assigned["status"] == "notification_sent")
check("backup clinician acknowledges", call("POST", f"{ER}/{alert['id']}/ack", tok["dr.joseph"], {})[1]["result"] == "acknowledged")
check("receptionist cannot change clinical status",
      call("POST", f"{ER}/{alert['id']}/status", tok["reception.ravi"], {"status": "response_started"})[0] == 403)
check("receptionist cannot change triage",
      call("POST", f"{ER}/{alert['id']}/triage", tok["reception.ravi"], {"priority": "urgent", "note": "x"})[0] == 403)
for s in ["response_started", "under_care"]:
    check(f"clinical team moves status to {s}", call("POST", f"{ER}/{alert['id']}/status", tok["dr.joseph"], {"status": s})[0] == 200)
check("status cannot go backwards", call("POST", f"{ER}/{alert['id']}/status", tok["dr.joseph"], {"status": "acknowledged"})[0] == 409)
code, tri = call("POST", f"{ER}/{alert['id']}/triage", tok["dr.joseph"],
                 {"priority": "critical", "triage_level": "Level 1 - Resuscitation", "note": "GCS 8, airway secured"})
check("clinician records the triage level from protocol", code == 200 and tri["triage_level"] == "Level 1 - Resuscitation")

# 6. Prioritisation in queues
eq = call("GET", "/api/queue", tok["dr.joseph"])[1]["visits"]
check("critical emergency is first in the emergency queue", eq and eq[0]["priority"] == "critical"
      and eq[0]["patient"]["pid"] == pid, [x["priority"] for x in eq][:3])
code, opened = call("GET", ER, tok["dean"])
check("open emergencies list puts critical first", opened["alerts"][0]["priority"] == "critical")

# 8. Restricted details
code, adm = call("GET", f"{ER}/{alert['id']}", tok["admin"])
check("administrator sees status but not the patient's name or clinical note",
      code == 200 and adm["patient"]["name"] == "Restricted" and adm["description"] == "")
check("coordinator cannot open emergency records", call("GET", f"{ER}/{alert['id']}", tok["stores.thomas"])[0] == 403)
check("patient cannot open emergency records", call("GET", ER, tok["patient"])[0] == 403)
code, full = call("GET", f"{ER}/{alert['id']}", tok["dr.joseph"])
check("clinician sees full details and the audit trail", code == 200 and full["patient"]["name"] == "Unknown Male"
      and len(full["events"]) >= 8)

check("closing needs a note", call("POST", f"{ER}/{alert['id']}/status", tok["dr.joseph"], {"status": "closed"})[0] == 400)
call("POST", f"{ER}/{alert['id']}/status", tok["dr.joseph"], {"status": "admitted", "note": "ICU bed 2"})
code, closed = call("POST", f"{ER}/{alert['id']}/status", tok["dr.joseph"], {"status": "closed", "note": "Handed to ICU"})
check("emergency is closed with timestamps", code == 200 and closed["closed_at"])
code, rep = call("GET", ER + "/report", tok["chairman"])
check("acknowledgement report lists the alert", code == 200 and any(a["id"] == alert["id"] and a["ack_seconds"] is not None
                                                                     for a in rep["alerts"]))
check("doctor cannot open the acknowledgement report", call("GET", ER + "/report", tok["dr.arjun"])[0] == 403)
call("POST", ER + "/policy/current", tok["admin"], old_policy)

print("\n-- Equipment workflow --")
code, cat = call("GET", EQ + "/catalog", tok["dr.joseph"])
sections = {s["section"]: s for s in cat["sections"]}
check("catalogue is grouped by department and category", "Ambulance and patient transport services" in sections
      and len(sections) >= 15 and all(s["categories"] for s in cat["sections"]))
check("ambulance services are offered to Emergency first", sections["Ambulance and patient transport services"]["for_me"])
check("patient cannot read the catalogue", call("GET", EQ + "/catalog", tok["patient"])[0] == 403)
monitor = next(i for s in cat["sections"] for c in s["categories"] for i in c["items"] if i["name"] == "Multiparameter patient monitor")

k = key()
req = {"idem_key": k, "catalog_id": monitor["id"], "quantity": 10, "urgency": "urgent", "request_type": "new",
       "justification": "New 10-bed step-down unit opens next week", "location": "Cardiology step-down",
       "attachment": {"name": "plan.txt", "data": "VW5pdCBsYXlvdXQ="}}
check("nurse cannot raise an equipment purchase", call("POST", EQ + "/requests", tok["nurse.priya"], req)[0] == 403)
check("coordinator cannot raise an equipment purchase", call("POST", EQ + "/requests", tok["stores.thomas"], req)[0] == 403)
code, out = call("POST", EQ + "/requests", tok["dr.arjun"], req)
r = out["request"]
check("doctor raises an equipment request", code == 200 and r["ref"].startswith("EQ-") and r["status"] == "pending_dean"
      and r["department"] == "Cardiology" and r["attachment"] == "plan.txt")
code, again = call("POST", EQ + "/requests", tok["dr.arjun"], req)
check("repeated submit does not duplicate the request", again["duplicate"] and again["request"]["id"] == r["id"])
check("dean was notified", any(i["kind"] == "equipment" and i["ref"] == str(r["id"])
                               for i in call("GET", "/api/notifications", tok["dean"])[1]["items"]))
check("other department's doctor cannot see it", call("GET", f"{EQ}/requests/{r['id']}", tok["dr.kavya"])[0] == 404)
check("doctor downloads own attachment", call("GET", f"{EQ}/requests/{r['id']}/attachment", tok["dr.arjun"])[0] == 200)

check("coordinator cannot act before dean approval", call("POST", f"{EQ}/requests/{r['id']}/check-stock", tok["stores.thomas"])[0] == 409)
check("chairman cannot approve equipment", call("POST", f"{EQ}/requests/{r['id']}/decide", tok["chairman"], {"action": "approve"})[0] == 403)
check("administrator cannot approve equipment", call("POST", f"{EQ}/requests/{r['id']}/decide", tok["admin"], {"action": "approve"})[0] == 403)
check("doctor cannot approve own request", call("POST", f"{EQ}/requests/{r['id']}/decide", tok["dr.arjun"], {"action": "approve"})[0] == 403)
code, filt = call("GET", f"{EQ}/requests?department=Cardiology&urgency=urgent&status=pending_dean", tok["dean"])
check("dean filters by department, urgency and status", code == 200 and any(x["id"] == r["id"] for x in filt["rows"]))
check("rejecting needs a reason", call("POST", f"{EQ}/requests/{r['id']}/decide", tok["dean"], {"action": "reject"})[0] == 400)
code, cl = call("POST", f"{EQ}/requests/{r['id']}/decide", tok["dean"], {"action": "clarify", "note": "Is 10 for all beds?"})
check("dean requests clarification", code == 200 and cl["status"] == "clarification")
check("doctor is told about the question", any("Clarification" in i["text"] for i in call("GET", "/api/notifications", tok["dr.arjun"])[1]["items"]))
code, ans = call("POST", f"{EQ}/requests/{r['id']}/respond", tok["dr.arjun"], {"note": "Yes, one per bed", "quantity": 10})
check("doctor answers and it returns to the dean", code == 200 and ans["status"] == "pending_dean")
code, ap = call("POST", f"{EQ}/requests/{r['id']}/decide", tok["dean"], {"action": "approve", "qty_approved": 10, "note": "Approved"})
check("dean approves the quantity and forwards to the coordinator", code == 200 and ap["status"] == "approved" and ap["qty_approved"] == 10)
check("coordinator is notified of the approval", any(i["ref"] == str(r["id"]) and "Approved by the dean" in i["text"]
                                                     for i in call("GET", "/api/notifications", tok["stores.thomas"])[1]["items"]))

check("doctor cannot touch stock", call("POST", f"{EQ}/requests/{r['id']}/check-stock", tok["dr.arjun"])[0] == 403)
code, stock = call("POST", f"{EQ}/requests/{r['id']}/check-stock", tok["stores.thomas"])
inv = stock["items"][0]
check("stock check finds the shortage", code == 200 and stock["needed"] == 10 and stock["available"] < 10
      and stock["request"]["status"] == "sourcing_required")
avail = inv["available"]
check("cannot reserve more than is available", call("POST", f"{EQ}/requests/{r['id']}/reserve", tok["stores.thomas"],
                                                    {"inventory_id": inv["id"], "qty": avail + 1})[0] == 409)

# Two coordinators reserve at the same moment: stock must not go negative or be double allocated
outs = []
ts = [threading.Thread(target=lambda n=n: outs.append(call("POST", f"{EQ}/requests/{r['id']}/reserve", tok[n],
                                                          {"inventory_id": inv["id"], "qty": avail})))
      for n in ("stores.thomas", "admin")]
[t.start() for t in ts]
[t.join() for t in ts]
check("concurrent reservations: exactly one succeeds", sorted(o[0] for o in outs) == [200, 409], [o[0] for o in outs])
item = call("GET", f"{EQ}/inventory/{inv['id']}", tok["stores.thomas"])[1]
check("stock never goes negative", item["available"] == 0 and item["reserved"] == avail)
tags = [a["asset_tag"] for a in item["assets"] if a["state"] == "reserved" and a["request"] == r["id"]]
check("each reserved asset is allocated once", len(tags) == avail == len(set(tags)))
check("counts add up", item["total"] == sum(item[s] for s in ("available", "reserved", "in_service", "maintenance", "damaged")))

need = 10 - avail
code, src = call("POST", f"{EQ}/requests/{r['id']}/source", tok["stores.thomas"],
                 {"supplier_name": "MedEquip Distributors", "reference": "PO-TEST-1", "qty": need, "expected_date": "2030-01-01"})
check("coordinator records the supplier and order", code == 200 and src["status"] == "sourcing" and src["qty_sourced"] == need)
check("cannot over-source", call("POST", f"{EQ}/requests/{r['id']}/source", tok["stores.thomas"],
                                 {"supplier_name": "MedEquip Distributors", "qty": 1})[0] == 409)
order = src["sourcing"][0]
code, dsp = call("POST", f"{EQ}/requests/{r['id']}/dispatch", tok["stores.thomas"],
                 {"idem_key": key(), "qty": avail + 1, "destination": "Cardiology step-down", "handled_by": "Ajith"})
check("cannot dispatch more than is reserved", code == 409)
dk = key()
code, dsp = call("POST", f"{EQ}/requests/{r['id']}/dispatch", tok["stores.thomas"],
                 {"idem_key": dk, "qty": avail, "destination": "Cardiology step-down", "handled_by": "Ajith"})
check("partial dispatch from stock", code == 200 and dsp["request"]["qty_dispatched"] == avail)
code, dsp2 = call("POST", f"{EQ}/requests/{r['id']}/dispatch", tok["stores.thomas"],
                  {"idem_key": dk, "qty": avail, "destination": "Cardiology step-down", "handled_by": "Ajith"})
check("repeated dispatch does not dispatch twice", dsp2["duplicate"] and dsp2["dispatch"]["id"] == dsp["dispatch"]["id"])
check("nurse in another department cannot confirm", call("POST", f"{EQ}/dispatches/{dsp['dispatch']['id']}/confirm",
                                                         tok["nurse.deepa"], {"qty_delivered": avail, "received_by": "x y"})[0] == 404)
code, conf = call("POST", f"{EQ}/dispatches/{dsp['dispatch']['id']}/confirm", tok["nurse.priya"],
                  {"qty_delivered": avail, "received_by": "Priya Thomas"})
check(f"{avail} of 10 delivered is partial, not fulfilled", code == 200 and conf["status"] == "partially_fulfilled"
      and conf["qty_delivered"] == avail)

code, arr = call("POST", f"{EQ}/sourcing/{order['id']}/arrive", tok["stores.thomas"], {"qty": need})
check("arrival is recorded and awaits inspection", code == 200 and arr["sourcing"][0]["status"] == "arrived")
check("coordinator is asked to inspect", any("needs inspection" in i["text"] for i in call("GET", "/api/notifications", tok["stores.thomas"])[1]["items"]))
new_tags = [f"CS-MON-T{n:02d}" for n in range(need)]
code, ins = call("POST", f"{EQ}/sourcing/{order['id']}/inspect", tok["stores.thomas"],
                 {"accepted": need - 1, "rejected": 1, "note": "One unit had a cracked screen", "asset_tags": new_tags[:need - 1]})
check("inspection accepts good units into stock for the request", code == 200 and ins["qty_reserved"] == need - 1
      and ins["qty_received"] == need - 1)
code, src2 = call("POST", f"{EQ}/requests/{r['id']}/source", tok["stores.thomas"],
                  {"supplier_name": "MedEquip Distributors", "reference": "PO-TEST-2", "qty": 1})
check("rejected unit is sourced again", code == 200)
o2 = src2["sourcing"][-1]
call("POST", f"{EQ}/sourcing/{o2['id']}/arrive", tok["stores.thomas"], {"qty": 1})
code, ins2 = call("POST", f"{EQ}/sourcing/{o2['id']}/inspect", tok["stores.thomas"],
                  {"accepted": 1, "note": "OK", "asset_tags": [new_tags[-1]]})
check("all remaining units are reserved and ready to send", code == 200 and ins2["qty_reserved"] == need
      and ins2["status"] == "partially_fulfilled")
code, d3 = call("POST", f"{EQ}/requests/{r['id']}/dispatch", tok["admin"],
                {"idem_key": key(), "qty": need, "destination": "Cardiology step-down", "handled_by": "Ajith"})
check("administrator can dispatch within the workflow", code == 200)
code, c3 = call("POST", f"{EQ}/dispatches/{d3['dispatch']['id']}/confirm", tok["dr.arjun"],
                {"qty_delivered": need, "received_by": "Dr. Arjun Menon"})
check("request is fulfilled only when all 10 are delivered", code == 200 and c3["status"] == "fulfilled"
      and c3["qty_delivered"] == 10)
detail = call("GET", f"{EQ}/requests/{r['id']}", tok["dean"])[1]
check("history records every status and quantity change", len(detail["history"]) >= 12
      and any(h["action"] == "inspected" for h in detail["history"]))
item = call("GET", f"{EQ}/inventory/{inv['id']}", tok["stores.thomas"])[1]
check("delivered monitors are counted in service", item["reserved"] == 0 and
      item["total"] == sum(item[s] for s in ("available", "reserved", "in_service", "maintenance", "damaged")))
check("notifications reached the doctor at each stage", sum(1 for i in call("GET", "/api/notifications", tok["dr.arjun"])[1]["items"]
                                                            if i["ref"] == str(r["id"])) >= 3)

# Consumables, returns and cancellation
code, cat_items = call("GET", EQ + "/inventory?q=gloves", tok["stores.thomas"])
gloves = cat_items[0]
gl = next(i for s in cat["sections"] for c in s["categories"] for i in c["items"] if i["name"] == "Surgical gloves")
code, g = call("POST", EQ + "/requests", tok["dr.rahul"], {"idem_key": key(), "catalog_id": gl["id"], "quantity": 20,
                                                           "urgency": "routine", "request_type": "consumable",
                                                           "justification": "Monthly ward supply"})
gid = g["request"]["id"]
call("POST", f"{EQ}/requests/{gid}/decide", tok["dean"], {"action": "approve"})
call("POST", f"{EQ}/requests/{gid}/reserve", tok["stores.thomas"], {"inventory_id": gloves["id"], "qty": 20})
code, gd = call("POST", f"{EQ}/requests/{gid}/dispatch", tok["stores.thomas"],
                {"idem_key": key(), "qty": 20, "destination": "General Medicine", "handled_by": "Ajith"})
after = call("GET", f"{EQ}/inventory/{gloves['id']}", tok["stores.thomas"])[1]
check("consumables leave stock when dispatched", after["total"] == gloves["total"] - 20)
call("POST", f"{EQ}/dispatches/{gd['dispatch']['id']}/confirm", tok["dr.rahul"], {"qty_delivered": 20, "received_by": "Latha"})
code, ret = call("POST", f"{EQ}/requests/{gid}/return", tok["dr.rahul"], {"qty": 5, "reason": "Wrong size", "condition": "good"})
back = call("GET", f"{EQ}/inventory/{gloves['id']}", tok["stores.thomas"])[1]
check("returns go back into stock and reopen the request", code == 200 and back["available"] == after["available"] + 5
      and ret["status"] == "partially_fulfilled")
code, cc = call("POST", f"{EQ}/requests/{gid}/cancel", tok["stores.thomas"], {"reason": "Ward will use the 15 delivered"})
check("cancellation is recorded with a reason", code == 200 and cc["status"] == "cancelled")

# Low stock notification
code, masks = call("GET", EQ + "/inventory?q=face%20masks", tok["stores.thomas"])
check("low stock is flagged", masks[0]["low"])

# Maintenance: unsafe equipment is taken out of clinical use until verified
mon = call("GET", f"{EQ}/inventory/{inv['id']}", tok["stores.thomas"])[1]
in_use = next(a for a in mon["assets"] if a["state"] == "in_service")
code, t = call("POST", EQ + "/maintenance", tok["nurse.priya"], {"idem_key": key(), "asset_tag": in_use["asset_tag"],
                                                                 "issue": "Screen flickers and SpO2 reading drops out", "unsafe": True})
check("department reports unsafe equipment", code == 200 and t["unsafe"] and t["qty_held"] == 1)
mon2 = call("GET", f"{EQ}/inventory/{inv['id']}", tok["stores.thomas"])[1]
asset = next(a for a in mon2["assets"] if a["asset_tag"] == in_use["asset_tag"])
check("unsafe unit is no longer available for clinical use", asset["state"] == "maintenance" and asset["condition"] == "unsafe")
check("nurse cannot manage the repair", call("POST", f"{EQ}/maintenance/{t['id']}/update", tok["nurse.priya"], {"action": "start"})[0] == 403)
call("POST", f"{EQ}/maintenance/{t['id']}/update", tok["stores.thomas"], {"action": "assign", "provider_name": "BioCare Service Engineers", "technician": "Vinod"})
call("POST", f"{EQ}/maintenance/{t['id']}/update", tok["stores.thomas"], {"action": "schedule", "scheduled_for": "2030-01-02"})
call("POST", f"{EQ}/maintenance/{t['id']}/update", tok["stores.thomas"], {"action": "start"})
check("cannot verify before repair is finished", call("POST", f"{EQ}/maintenance/{t['id']}/update", tok["stores.thomas"],
                                                       {"action": "verify", "note": "Checked"})[0] == 409)
check("cannot cancel an unsafe repair back into service", call("POST", f"{EQ}/maintenance/{t['id']}/update", tok["stores.thomas"],
                                                               {"action": "cancel", "note": "never mind"})[0] == 409)
call("POST", f"{EQ}/maintenance/{t['id']}/update", tok["stores.thomas"],
     {"action": "findings", "findings": "Display ribbon loose; SpO2 board replaced", "parts_used": "SpO2 board", "cost": 4200})
call("POST", f"{EQ}/maintenance/{t['id']}/update", tok["stores.thomas"], {"action": "complete"})
code, done = call("POST", f"{EQ}/maintenance/{t['id']}/update", tok["stores.thomas"],
                  {"action": "verify", "note": "Electrical safety and SpO2 simulator test passed"})
check("verified repair returns the unit to service", code == 200 and done["status"] == "completed")
mon3 = call("GET", f"{EQ}/inventory/{inv['id']}", tok["stores.thomas"])[1]
asset = next(a for a in mon3["assets"] if a["asset_tag"] == in_use["asset_tag"])
check("unit is back with its department and marked good", asset["state"] == "in_service" and asset["condition"] == "good")
check("reporter is told it is ready", any("back in service" in i["text"] for i in call("GET", "/api/notifications", tok["nurse.priya"])[1]["items"]))
check("doctor sees the department's tickets but not costs",
      all(x["cost"] is None for x in call("GET", EQ + "/maintenance", tok["dr.arjun"])[1]))

# Overviews and access
code, ov = call("GET", EQ + "/overview", tok["chairman"])
check("chairman sees the procurement overview", code == 200 and "stages" in ov and ov["by_department"])
check("administrator sees the procurement overview", call("GET", EQ + "/overview", tok["admin"])[0] == 200)
check("doctor cannot see the hospital-wide overview", call("GET", EQ + "/overview", tok["dr.arjun"])[0] == 403)
check("doctor cannot see the inventory ledger", call("GET", EQ + "/inventory", tok["dr.arjun"])[0] == 403)
code, page = call("GET", EQ + "/requests?size=5&page=1&sort=urgency&dir=asc", tok["stores.thomas"])
check("coordinator table is paginated and sortable", code == 200 and len(page["rows"]) <= 5 and page["total"] >= 7)
code, b = call("GET", "/api/badges", tok["dean"])
check("badges include emergency and equipment counts", code == 200 and "equipment" in b and "emergency" in b)

print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
sys.exit(1 if failures else 0)
