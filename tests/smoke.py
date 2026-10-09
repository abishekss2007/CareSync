"""End-to-end check of the main flows and access rules. Run with the server up: python tests/smoke.py [base_url]"""
import json
import sys
import urllib.error
import urllib.request

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
        return err.code, json.loads(err.read().decode() or "{}")


def check(label, condition, detail=""):
    print(("PASS  " if condition else "FAIL  ") + label + (f"  -> {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def signin(username):
    code, out = call("POST", "/api/demo/login", body={"username": username})
    assert code == 200, (username, out)
    return out["token"]


accounts = call("GET", "/api/demo/accounts")[1]
patient_login = next(a["username"] for a in accounts if a["role"] == "patient")
tok = {name: signin(name) for name in ["chairman", "dean", "dr.arjun", "dr.kavya", "nurse.priya", "nurse.deepa",
                                       "reception.ravi", patient_login]}
pat = tok[patient_login]

check("no token is rejected", call("GET", "/api/status")[0] == 401)
check("wrong password is rejected", call("POST", "/api/login", body={"username": "dean", "password": "nope"})[0] == 401)

# Patient: sees status and own record only
check("patient sees hospital status", call("GET", "/api/status", pat)[0] == 200)
code, mine = call("GET", "/api/my/record", pat)
check("patient sees own record with live token", code == 200 and mine["active"] is not None, mine.get("active"))
for path in ["/api/patients", "/api/queue", "/api/beds", "/api/requests", "/api/tasks", "/api/messages",
             "/api/staff", "/api/analytics", "/api/audit", "/api/export/visits", "/api/settings"]:
    check(f"patient blocked from {path}", call("GET", path, pat)[0] == 403)

# Role walls between staff
check("nurse blocked from analytics", call("GET", "/api/analytics", tok["nurse.priya"])[0] == 403)
check("doctor blocked from audit log", call("GET", "/api/audit", tok["dr.arjun"])[0] == 403)
check("dean blocked from audit log", call("GET", "/api/audit", tok["dean"])[0] == 403)
check("dean cannot change settings", call("POST", "/api/settings", tok["dean"], {"cognos_url": ""})[0] == 403)
check("doctor cannot register patients", call("POST", "/api/patients", tok["dr.arjun"],
                                              {"name": "X Y", "age": 30, "gender": "Male"})[0] == 403)

# Reception: register, issue token; receptionist gets no clinical data
code, reg = call("POST", "/api/patients", tok["reception.ravi"],
                 {"name": "Test Patient", "age": 44, "gender": "Male", "allergies": "Penicillin"})
check("receptionist registers patient with ID and PIN", code == 200 and reg["patient"]["pid"].startswith("CS-"))
pid = reg["patient"]["pid"]
code, login = call("POST", "/api/login", body={"username": pid, "password": reg["pin"]})
check("new patient can sign in with ID and PIN", code == 200 and login["user"]["role"] == "patient")
code, tk = call("POST", "/api/visits", tok["reception.ravi"], {"pid": pid, "department": "Orthopedics", "complaint": "Knee pain"})
check("receptionist issues token", code == 200 and tk["token"].startswith("ORT-"), tk)
check("duplicate token is refused", call("POST", "/api/visits", tok["reception.ravi"],
                                         {"pid": pid, "department": "Orthopedics"})[0] == 409)
code, rec = call("GET", f"/api/patients/{pid}", tok["reception.ravi"])
check("receptionist record has no clinical fields", code == 200 and not rec["clinical"] and "diagnosis" not in rec["visits"][0])

code, tri = call("POST", "/api/triage", tok["reception.ravi"], {"complaint": "Knee pain after a fall"})
check("receptionist gets a department suggestion", code == 200 and tri["department"] in ("Orthopedics", "Emergency"), tri)
check("doctor cannot use the front-desk suggestion", call("POST", "/api/triage", tok["dr.arjun"], {"complaint": "Knee pain"})[0] == 403)

# Nurse vitals, doctor consult, cross-department referral
code, q = call("GET", "/api/queue", tok["nurse.deepa"])
check("nurse queue is limited to own department", code == 200 and all(v["department"] == "Orthopedics" for v in q["visits"]))
visit = next(v for v in q["visits"] if v["patient"]["pid"] == pid)
check("nurse records vitals", call("POST", f"/api/visits/{visit['id']}/vitals", tok["nurse.deepa"],
                                   {"bp": "128/82", "temp": "98.4", "pulse": "78", "spo2": "98"})[0] == 200)
check("other department's doctor cannot start it", call("POST", f"/api/visits/{visit['id']}/start", tok["dr.arjun"])[0] == 404)
check("doctor starts consultation", call("POST", f"/api/visits/{visit['id']}/start", tok["dr.kavya"])[0] == 200)
code, done = call("POST", f"/api/visits/{visit['id']}/complete", tok["dr.kavya"], {
    "diagnosis": "Osteoarthritis of knee", "notes": "Breathless on exertion.",
    "prescriptions": [{"medicine": "Aceclofenac 100mg", "dosage": "1-0-1", "duration": "7 days"}],
    "refer_to": "Cardiology", "refer_reason": "Breathlessness on exertion"})
check("doctor completes and refers to Cardiology", code == 200 and done["referral"]["department"] == "Cardiology", done)
code, rec = call("GET", f"/api/patients/{pid}", tok["dr.arjun"])
ortho = next(v for v in rec["visits"] if v["department"] == "Orthopedics")
check("cardiologist sees the Orthopedics visit, vitals and medicines",
      code == 200 and ortho["diagnosis"] and ortho["vitals"]["bp"] == "128/82" and ortho["prescriptions"])
code, cq = call("GET", "/api/queue", tok["dr.arjun"])
check("referred patient is in the Cardiology queue", any(v["patient"]["pid"] == pid and v["referred_from"] == "Orthopedics" for v in cq["visits"]))
check("history summary works", call("GET", f"/api/patients/{pid}/summary", tok["dr.arjun"])[0] == 200)
check("nurse cannot generate summary", call("GET", f"/api/patients/{pid}/summary", tok["nurse.priya"])[0] == 403)

# Approval chain: nurse -> doctor -> dean
doctors = [u for u in call("GET", "/api/staff", tok["nurse.priya"])[1] if u["name"] == "Dr. Arjun Menon"]
code, r = call("POST", "/api/requests", tok["nurse.priya"],
               {"kind": "Supplies", "title": "Smoke test request", "doctor_id": doctors[0]["id"]})
check("nurse raises request to a doctor", code == 200 and r["status"] == "pending")
rid = r["id"]
check("another doctor cannot decide it", call("POST", f"/api/requests/{rid}/decide", tok["dr.kavya"], {"action": "approve"})[0] == 403)
check("nurse cannot approve own request", call("POST", f"/api/requests/{rid}/decide", tok["nurse.priya"], {"action": "approve"})[0] == 403)
code, r = call("POST", f"/api/requests/{rid}/decide", tok["dr.arjun"], {"action": "forward", "note": "Needs dean sign-off"})
check("doctor forwards to dean", code == 200 and r["waiting_on"] == "Dean")
inbox = call("GET", "/api/requests", tok["dean"])[1]["inbox"]
check("request reaches the dean's inbox", any(x["id"] == rid for x in inbox))
code, r = call("POST", f"/api/requests/{rid}/decide", tok["dean"], {"action": "approve", "note": "OK"})
check("dean approves", code == 200 and r["status"] == "approved" and len(r["trail"]) == 3)
notes = call("GET", "/api/notifications", tok["nurse.priya"])[1]
check("nurse is notified of the decision", any("approved" in n["text"] for n in notes["items"]))

# Tasks follow the hierarchy
staff = call("GET", "/api/staff", tok["dean"])[1]
ids = {u["name"]: u["id"] for u in staff}
check("doctor assigns task to nurse", call("POST", "/api/tasks", tok["dr.arjun"],
                                           {"title": "Smoke task", "assigned_to": ids["Priya Thomas"]})[0] == 200)
check("nurse cannot assign task to doctor", call("POST", "/api/tasks", tok["nurse.priya"],
                                                 {"title": "Smoke task", "assigned_to": ids["Dr. Arjun Menon"]})[0] == 403)
check("nurse cannot assign task to dean", call("POST", "/api/tasks", tok["nurse.priya"],
                                               {"title": "Smoke task", "assigned_to": ids["Dr. Meera Nair"]})[0] == 403)

# Messaging
check("staff message is sent", call("POST", "/api/messages", tok["nurse.priya"],
                                    {"to": ids["Dr. Arjun Menon"], "body": "Smoke test message"})[0] == 200)
thread = call("GET", f"/api/messages/{ids['Priya Thomas']}", tok["dr.arjun"])[1]
check("recipient reads the message", thread and thread[-1]["body"] == "Smoke test message")

# Appointments
import datetime
tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
code, slots = call("GET", f"/api/appointments/slots?department=Neurology&day={tomorrow}", pat)
check("patient sees free appointment times", code == 200 and len(slots) > 3, slots)
code, booked = call("POST", "/api/my/appointments", pat, {"department": "Neurology", "day": tomorrow, "slot": slots[0]["slot"], "reason": "Headache"})
check("patient books an appointment", code == 200 and booked["status"] == "booked", booked)
check("same slot is no longer offered", slots[0]["slot"] not in [s["slot"] for s in call("GET", f"/api/appointments/slots?department=Neurology&day={tomorrow}", pat)[1]])
check("second booking the same day is refused", call("POST", "/api/my/appointments", pat, {"department": "Neurology", "day": tomorrow, "slot": slots[1]["slot"]})[0] == 409)
check("booking too far ahead is refused", call("POST", "/api/my/appointments", pat, {"department": "Neurology", "day": (datetime.date.today() + datetime.timedelta(days=40)).isoformat(), "slot": "09:00"})[0] == 400)
check("emergency cannot be booked", call("POST", "/api/my/appointments", pat, {"department": "Emergency", "day": tomorrow, "slot": "09:00"})[0] == 400)
check("staff cannot book as a patient", call("POST", "/api/my/appointments", tok["dr.arjun"], {"department": "Neurology", "day": tomorrow, "slot": slots[2]["slot"]})[0] == 403)
check("patient lists own appointments", any(a["id"] == booked["id"] for a in call("GET", "/api/my/appointments", pat)[1]))
check("patient cancels the appointment", call("POST", f"/api/my/appointments/{booked['id']}/cancel", pat)[0] == 200)
check("patient blocked from the reception list", call("GET", "/api/appointments", pat)[0] == 403)
code, todays = call("GET", "/api/appointments", tok["reception.ravi"])
check("receptionist sees today's appointments", code == 200 and len(todays) >= 1, todays)
waiting = [a for a in todays if a["status"] == "booked"]
code, arrived = call("POST", f"/api/appointments/{waiting[0]['id']}/checkin", tok["reception.ravi"])
check("receptionist checks in an appointment and gets a token", code == 200 and "-" in arrived["token"], arrived)
check("an appointment cannot be checked in twice", call("POST", f"/api/appointments/{waiting[0]['id']}/checkin", tok["reception.ravi"])[0] == 409)
check("nurse cannot check in appointments", call("POST", f"/api/appointments/{waiting[-1]['id']}/checkin", tok["nurse.priya"])[0] == 403)

# Staff accounts
check("nurse blocked from staff admin", call("GET", "/api/admin/staff", tok["nurse.priya"])[0] == 403)
check("dean cannot create another dean", call("POST", "/api/admin/staff", tok["dean"],
                                              {"name": "X Y", "username": "smoke.dean", "role": "dean"})[0] == 403)
code, made = call("POST", "/api/admin/staff", tok["dean"],
                  {"name": "Smoke Nurse", "username": "smoke.nurse", "role": "nurse", "department": "Neurology"})
check("dean creates a nurse account", code == 200 and len(made["password"]) >= 8, made)
check("duplicate username is refused", call("POST", "/api/admin/staff", tok["dean"],
                                            {"name": "Smoke Nurse", "username": "SMOKE.NURSE", "role": "nurse", "department": "Neurology"})[0] == 409)
code, new_login = call("POST", "/api/login", body={"username": "smoke.nurse", "password": made["password"]})
check("new staff member signs in with the temporary password", code == 200 and new_login["user"]["department"] == "Neurology")
new_tok = new_login["token"]
check("new staff member changes own password", call("POST", "/api/password", new_tok,
                                                    {"current": made["password"], "new": "smoke-pass-123"})[0] == 200)
check("wrong current password is refused", call("POST", "/api/password", new_tok,
                                                {"current": "nope", "new": "smoke-pass-456"})[0] == 400)
new_id = made["user"]["id"]
check("dean cannot disable the chairman", call("POST", f"/api/admin/staff/{ids['Dr. R. Venkataraman']}/active", tok["dean"], {"active": False})[0] == 403)
check("dean disables the account", call("POST", f"/api/admin/staff/{new_id}/active", tok["dean"], {"active": False})[0] == 200)
check("disabled account is signed out", call("GET", "/api/me", new_tok)[0] == 401)
check("disabled account cannot sign in", call("POST", "/api/login", body={"username": "smoke.nurse", "password": "smoke-pass-123"})[0] == 403)
check("dean re-enables the account", call("POST", f"/api/admin/staff/{new_id}/active", tok["dean"], {"active": True})[0] == 200)
code, reset = call("POST", f"/api/admin/staff/{new_id}/reset-password", tok["chairman"])
check("chairman resets the password", code == 200 and call("POST", "/api/login", body={"username": "smoke.nurse", "password": reset["password"]})[0] == 200)
check("old password stops working after reset", call("POST", "/api/login", body={"username": "smoke.nurse", "password": "smoke-pass-123"})[0] == 401)

# Beds, analytics, export, audit
beds = call("GET", "/api/beds", tok["nurse.priya"])[1]
free = next(b for b in beds if b["status"] == "free")
check("nurse assigns a bed", call("POST", f"/api/beds/{free['id']}", tok["nurse.priya"], {"status": "occupied", "pid": pid})[0] == 200)
check("same patient cannot hold two beds", call("POST", f"/api/beds/{[b for b in beds if b['status'] == 'free'][1]['id']}",
                                                tok["nurse.priya"], {"status": "occupied", "pid": pid})[0] == 409)
check("doctor cannot change beds", call("POST", f"/api/beds/{free['id']}", tok["dr.arjun"], {"status": "free"})[0] == 403)
code, a = call("GET", "/api/analytics", tok["dean"])
check("dean sees analytics", code == 200 and a["kpis"]["patients_today"] > 0 and len(a["daily"]) == 15)
code, text = call("GET", "/api/export/visits", tok["chairman"])
check("chairman exports visits CSV for Cognos", code == 200 and text.startswith("visit_id,patient_id"))
code, log = call("GET", "/api/audit", tok["chairman"])
check("audit log records record views", code == 200 and any(x["action"] == "viewed patient record" for x in log))

print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
sys.exit(1 if failures else 0)
