"""Patient history summary. Uses IBM watsonx.ai when configured in .env, otherwise a rule-based summary."""
import json
import os
import urllib.parse
import urllib.request

IAM_URL = "https://iam.cloud.ibm.com/identity/token"


def configured():
    return bool(os.environ.get("WATSONX_APIKEY") and os.environ.get("WATSONX_PROJECT_ID"))


def _post(url, data, headers, timeout=25):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def _watsonx(prompt):
    body = urllib.parse.urlencode({
        "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
        "apikey": os.environ["WATSONX_APIKEY"],
    }).encode()
    token = _post(IAM_URL, body, {"Content-Type": "application/x-www-form-urlencoded"})["access_token"]
    base = os.environ.get("WATSONX_URL", "https://us-south.ml.cloud.ibm.com").rstrip("/")
    payload = json.dumps({
        "messages": [{"role": "user", "content": prompt}],
        "model_id": os.environ.get("WATSONX_MODEL", "ibm/granite-3-8b-instruct"),
        "project_id": os.environ["WATSONX_PROJECT_ID"],
        "max_tokens": 300,
        "temperature": 0,
    }).encode()
    out = _post(f"{base}/ml/v1/text/chat?version=2024-05-31", payload, {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    })
    return out["choices"][0]["message"]["content"].strip()


def _history_lines(visits):
    lines = []
    for v in visits:
        meds = ", ".join(f"{m['medicine']} {m['dosage']}".strip() for m in v["prescriptions"]) or "none"
        lines.append(
            f"- {v['checkin_at'][:10]} | {v['department']} | {v['doctor'] or 'unassigned'} | "
            f"complaint: {v['complaint'] or '-'} | diagnosis: {v['diagnosis'] or 'pending'} | medicines: {meds}"
        )
    return "\n".join(lines)


def _rule_based(patient, visits):
    done = [v for v in visits if v["status"] == "done"]
    if not done:
        return "No completed visits on record yet."
    depts = []
    for v in done:
        if v["department"] not in depts:
            depts.append(v["department"])
    meds = []
    for v in done:
        for m in v["prescriptions"]:
            if m["medicine"] not in meds:
                meds.append(m["medicine"])
    last = done[0]
    parts = [
        f"{patient['name']}, {patient['age']} years, has {len(done)} completed visit(s) across {', '.join(depts)}.",
        f"Most recent: {last['department']} on {last['checkin_at'][:10]} with {last['doctor'] or 'a doctor'}, "
        f"diagnosis: {last['diagnosis'] or 'not recorded'}.",
    ]
    if meds:
        parts.append(f"Medicines prescribed so far: {', '.join(meds[:8])}.")
    if patient["allergies"]:
        parts.append(f"Recorded allergies: {patient['allergies']}.")
    return " ".join(parts)


def summarize(patient, visits):
    if configured():
        prompt = (
            "You are assisting a hospital doctor. Summarise this patient's history in 4 short sentences. "
            "Mention departments visited, key diagnoses, current medicines and allergies. "
            "Use only the facts given. Do not give treatment advice.\n\n"
            f"Patient: {patient['name']}, {patient['age']} years, {patient['gender']}, "
            f"blood group {patient['blood_group'] or 'unknown'}, allergies: {patient['allergies'] or 'none recorded'}\n"
            f"Visits (newest first):\n{_history_lines(visits)}\n\n"
            "Write only the summary as plain text, with no heading or bullet points."
        )
        try:
            return {"source": "IBM watsonx.ai", "text": _watsonx(prompt)}
        except Exception as exc:  # fall back so the doctor's screen never breaks
            return {
                "source": "Rule-based summary (watsonx.ai call failed)",
                "text": _rule_based(patient, visits),
                "error": str(exc)[:200],
            }
    return {"source": "Rule-based summary (watsonx.ai not configured)", "text": _rule_based(patient, visits)}


KEYWORDS = {
    "Emergency": ["unconscious", "bleeding", "accident", "severe", "collapse", "seizure", "burn", "poison", "cannot breathe"],
    "Cardiology": ["chest", "heart", "palpitation", "blood pressure", "bp", "breathless"],
    "Orthopedics": ["knee", "bone", "joint", "fracture", "back pain", "wrist", "ankle", "shoulder", "sprain", "fall"],
    "Neurology": ["headache", "migraine", "numb", "dizzy", "dizziness", "tingling", "memory", "tremor"],
    "Pediatrics": ["child", "baby", "infant", "toddler", "year old boy", "year old girl", "kid"],
}


def _keyword_department(complaint, departments):
    text = complaint.lower()
    for dept, words in KEYWORDS.items():
        hit = next((w for w in words if w in text), None)
        if dept in departments and hit:
            return dept, f'Matched the word "{hit}".'
    return "General Medicine", "No specific match, so General Medicine is the starting point."


def suggest_department(complaint, departments):
    """Suggest where to send a patient from the reason for the visit. A suggestion for the front desk, not a diagnosis."""
    if configured():
        prompt = (
            "You help a hospital front desk route patients. Choose the single best department for the reason below. "
            f"Departments: {', '.join(departments)}. "
            "Use Emergency only for life-threatening situations. Use Pediatrics when the patient is a child. "
            'Reply with JSON only, in this form: {"department": "<one department from the list>", "reason": "<one short sentence>"} '
            f"Reason for visit: {complaint}"
        )
        try:
            raw = _watsonx(prompt)
            data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
            dept = next((d for d in departments if d.lower() == str(data.get("department", "")).strip().lower()), None)
            if dept:
                return {"source": "IBM watsonx.ai", "department": dept, "reason": str(data.get("reason", "")).strip()[:200]}
            error = "model named a department that is not in the list"
        except Exception as exc:
            error = str(exc)[:200]
        dept, reason = _keyword_department(complaint, departments)
        return {"source": "Keyword rules (watsonx.ai call failed)", "department": dept, "reason": reason, "error": error}
    dept, reason = _keyword_department(complaint, departments)
    return {"source": "Keyword rules (watsonx.ai not configured)", "department": dept, "reason": reason}
