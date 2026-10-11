"""Live updates and the background watchdog.

/api/stream is a server-sent event stream that tells a signed-in app when something it shows has changed
(new notification, emergency alert, equipment request). The app then reloads that part over the normal API,
and keeps its six-second polling as a fallback. The watchdog thread escalates unacknowledged emergencies,
retries undelivered alerts and raises equipment reminders.
"""
import asyncio
import datetime as dt
import json
import os
import threading

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from .db import BUS, SessionLocal, User, now
from .db import Session as AuthSession

router = APIRouter()
CHECK_SECONDS = float(os.environ.get("LIVE_CHECK_SECONDS", "10"))
_stop = threading.Event()
_thread = None


def stream_user(token):
    from .main import SESSION_HOURS
    with SessionLocal() as db:
        session = db.get(AuthSession, token) if token else None
        if not session or session.created_at < now() - dt.timedelta(hours=SESSION_HOURS):
            return None
        user = db.get(User, session.user_id)
        return (user.id, user.role) if user and user.active else None


def versions(user_id, role):
    out = {"me": BUS["users"].get(user_id, 0), "emergency": BUS["emergency"]}
    if role != "patient":
        out["equipment"] = BUS["equipment"]
    return out


@router.get("/api/stream")
async def stream(request: Request, authorization: str = Header(default="")):
    token = authorization[7:] if authorization.startswith("Bearer ") else ""
    who = stream_user(token)
    if not who:
        raise HTTPException(401, "Please sign in again")
    user_id, role = who

    async def events():
        last = versions(user_id, role)
        yield f"event: hello\ndata: {json.dumps(last)}\n\n"
        ticks = 0
        while not await request.is_disconnected():
            await asyncio.sleep(1)
            ticks += 1
            current = versions(user_id, role)
            if current != last:
                changed = [k for k in current if current[k] != last.get(k)]
                last = current
                yield f"event: change\ndata: {json.dumps({'changed': changed})}\n\n"
            elif ticks % 15 == 0:
                if not await asyncio.to_thread(stream_user, token):  # signed out or disabled meanwhile
                    yield "event: bye\ndata: {}\n\n"
                    return
                yield ": keep-alive\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


def _loop():
    from . import emergency, equipment
    while not _stop.wait(CHECK_SECONDS):
        for check in (emergency.run_checks, equipment.run_checks):
            try:
                with SessionLocal() as db:
                    check(db)
            except Exception as err:  # keep watching even if one pass fails
                print(f"watchdog: {check.__module__} failed: {err}")


def start_watchdog():
    global _thread
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="caresync-watchdog", daemon=True)
    _thread.start()


def stop_watchdog():
    _stop.set()
