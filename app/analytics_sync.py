"""Keeps a live copy of the reporting tables in a cloud PostgreSQL database for IBM Cognos Analytics.

The app keeps running on its own database. A background thread pushes the de-identified reporting tables
to the database named by ANALYTICS_DATABASE_URL whenever they change, so a Cognos dashboard connected to
that database shows current data without anyone uploading files.
"""
import datetime as dt
import hashlib
import json
import os
import threading
import time

from . import reporting
from .db import SessionLocal

SCHEMA = "caresync"
INTERVAL = int(os.environ.get("ANALYTICS_SYNC_SECONDS", "15"))
STATE = {"enabled": False, "last_ok": None, "last_error": "", "rows": {}, "pushes": 0}
_stop = threading.Event()
_wake = threading.Event()


def url():
    return os.environ.get("ANALYTICS_DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://")


def snapshot():
    with SessionLocal() as db:
        return {table: reporting.rows(db, table) for table in reporting.TABLES}


def ddl():
    parts = [f"create schema if not exists {SCHEMA}"]
    for table, columns in reporting.TABLES.items():
        cols = ", ".join(f"{name} {kind}" for name, kind in columns)
        parts.append(f"create table if not exists {SCHEMA}.{table} ({cols})")
    parts.append(f"create table if not exists {SCHEMA}.sync_info (id integer primary key, last_synced timestamp, visits integer)")
    return "; ".join(parts)


def push(con, data):
    """Replace every reporting table in one transaction, so Cognos never sees a half-written state."""
    with con.cursor() as cur:
        cur.execute(ddl() + "; " + "; ".join(f"truncate {SCHEMA}.{t}" for t in reporting.TABLES))
        for table, rows in data.items():
            columns = ", ".join(reporting.header(table))
            with cur.copy(f"copy {SCHEMA}.{table} ({columns}) from stdin") as copy:
                for row in rows:
                    copy.write_row(row)
        cur.execute(
            f"insert into {SCHEMA}.sync_info (id, last_synced, visits) values (1, %s, %s) "
            "on conflict (id) do update set last_synced = excluded.last_synced, visits = excluded.visits",
            (dt.datetime.now().replace(microsecond=0), len(data["visits"])))
    con.commit()


def sync_once(con=None):
    import psycopg
    data = snapshot()
    own = con is None
    if own:
        con = psycopg.connect(url(), connect_timeout=15)
    try:
        push(con, data)
    finally:
        if own:
            con.close()
    return data


def _loop():
    import psycopg
    con, last_hash, last_push = None, None, 0.0
    while not _stop.is_set():
        try:
            data = snapshot()
            digest = hashlib.sha1(json.dumps(data, default=str).encode()).hexdigest()
            if digest != last_hash or time.time() - last_push > 300:
                if con is None or con.closed:
                    con = psycopg.connect(url(), connect_timeout=15)
                push(con, data)
                last_hash, last_push = digest, time.time()
                STATE.update(last_ok=dt.datetime.now().replace(microsecond=0), last_error="",
                             rows={t: len(r) for t, r in data.items()}, pushes=STATE["pushes"] + 1)
        except Exception as exc:  # keep the app running if the cloud database is unreachable
            STATE["last_error"] = str(exc).splitlines()[0][:200] if str(exc) else type(exc).__name__
            try:
                if con is not None:
                    con.close()
            except Exception:
                pass
            con = None
        _wake.wait(INTERVAL)
        _wake.clear()


def start():
    if not url():
        return
    STATE["enabled"] = True
    threading.Thread(target=_loop, name="analytics-sync", daemon=True).start()


def stop():
    _stop.set()
    _wake.set()


def nudge():
    """Ask for a sync now instead of waiting for the next interval."""
    _wake.set()


def status():
    return {"enabled": STATE["enabled"], "last_ok": STATE["last_ok"].isoformat() if STATE["last_ok"] else None,
            "error": STATE["last_error"], "rows": STATE["rows"], "interval": INTERVAL}
