"""Application tracker — CRUD for tracking job applications (SQLite)."""

import json
import os
import sqlite3
from contextlib import contextmanager

from .models import Application, NetworkMatch

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "tracker.db")
_JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "applications.json")


def _ensure_data_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def _init_db():
    """Create the applications table if it doesn't exist."""
    _ensure_data_dir()
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id TEXT PRIMARY KEY,
                job_title TEXT NOT NULL DEFAULT '',
                company TEXT NOT NULL DEFAULT '',
                location TEXT DEFAULT '',
                url TEXT DEFAULT '',
                source TEXT DEFAULT '',
                date_posted TEXT DEFAULT '',
                date_generated TEXT DEFAULT '',
                status TEXT DEFAULT 'generated',
                resume_path TEXT DEFAULT '',
                cover_letter_path TEXT DEFAULT '',
                ats_score INTEGER DEFAULT 0,
                description TEXT DEFAULT '',
                referrals TEXT DEFAULT '[]',
                notes TEXT DEFAULT ''
            )
        """)
    _migrate_json_if_needed()


def _migrate_json_if_needed():
    """One-time migration: import applications.json into SQLite."""
    if not os.path.exists(_JSON_PATH):
        return
    with _get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        if count > 0:
            return  # already migrated
    try:
        with open(_JSON_PATH, "r") as f:
            data = json.load(f)
        apps = [Application(**a) for a in data]
        with _get_conn() as conn:
            for app in apps:
                _insert_app(conn, app)
        # Rename old file so migration doesn't re-run
        os.rename(_JSON_PATH, _JSON_PATH + ".migrated")
    except Exception as e:
        print(f"JSON migration error: {e}")


@contextmanager
def _get_conn():
    """Yield a SQLite connection with WAL mode for better concurrency."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row_to_app(row: sqlite3.Row) -> Application:
    """Convert a database row to an Application model."""
    d = dict(row)
    d["referrals"] = json.loads(d.get("referrals") or "[]")
    return Application(**d)


def _insert_app(conn: sqlite3.Connection, app: Application):
    """Insert or replace an application."""
    conn.execute("""
        INSERT OR REPLACE INTO applications
        (id, job_title, company, location, url, source, date_posted,
         date_generated, status, resume_path, cover_letter_path,
         ats_score, description, referrals, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        app.id, app.job_title, app.company, app.location, app.url,
        app.source, app.date_posted, app.date_generated, app.status,
        app.resume_path, app.cover_letter_path, app.ats_score,
        app.description, json.dumps([r.model_dump() for r in app.referrals]),
        app.notes,
    ))


# Initialize DB on module import
_init_db()


def load_applications() -> list[Application]:
    with _get_conn() as conn:
        rows = conn.execute("SELECT * FROM applications ORDER BY date_generated DESC").fetchall()
        return [_row_to_app(r) for r in rows]


def get_application(app_id: str) -> Application | None:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        return _row_to_app(row) if row else None


def save_application(app: Application):
    with _get_conn() as conn:
        _insert_app(conn, app)


def update_status(app_id: str, status: str, notes: str | None = None):
    with _get_conn() as conn:
        if notes is not None:
            conn.execute("UPDATE applications SET status = ?, notes = ? WHERE id = ?", (status, notes, app_id))
        else:
            conn.execute("UPDATE applications SET status = ? WHERE id = ?", (status, app_id))
        return conn.total_changes > 0


def update_notes(app_id: str, notes: str):
    with _get_conn() as conn:
        conn.execute("UPDATE applications SET notes = ? WHERE id = ?", (notes, app_id))
        return conn.total_changes > 0


def update_referrals(app_id: str, referrals: list[NetworkMatch]):
    with _get_conn() as conn:
        data = json.dumps([r.model_dump() for r in referrals])
        conn.execute("UPDATE applications SET referrals = ? WHERE id = ?", (data, app_id))
        return conn.total_changes > 0


def delete_application(app_id: str) -> bool:
    with _get_conn() as conn:
        conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
        return conn.total_changes > 0
