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
    """Create all tables if they don't exist."""
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS seen_jobs (
                job_id TEXT PRIMARY KEY,
                added_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS network_cache (
                cache_key TEXT PRIMARY KEY,
                matches TEXT DEFAULT '[]',
                timestamp TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS job_cache (
                id TEXT PRIMARY KEY,
                title TEXT DEFAULT '',
                company TEXT DEFAULT '',
                location TEXT DEFAULT '',
                url TEXT DEFAULT '',
                description TEXT DEFAULT '',
                date_posted TEXT DEFAULT '',
                source TEXT DEFAULT '',
                salary TEXT DEFAULT '',
                cached_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS resume_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT (datetime('now')),
                job_title TEXT DEFAULT '',
                company TEXT DEFAULT '',
                seniority_level TEXT DEFAULT '',
                ats_keywords TEXT DEFAULT '[]',
                hard_skills TEXT DEFAULT '[]',
                soft_skills TEXT DEFAULT '[]',
                ats_score INTEGER DEFAULT 0,
                matched_keywords TEXT DEFAULT '[]',
                resume_json_path TEXT DEFAULT '',
                docx_path TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cover_letter_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT (datetime('now')),
                job_title TEXT DEFAULT '',
                company TEXT DEFAULT '',
                seniority_level TEXT DEFAULT '',
                ats_keywords TEXT DEFAULT '[]',
                hard_skills TEXT DEFAULT '[]',
                text_path TEXT DEFAULT '',
                docx_path TEXT DEFAULT ''
            )
        """)
        # Add new columns if they don't exist (safe migration)
        _add_column_if_missing(conn, "applications", "fit_summary", "TEXT DEFAULT '[]'")
        _add_column_if_missing(conn, "applications", "gap_analysis", "TEXT DEFAULT '[]'")
    _migrate_json_if_needed()


def _add_column_if_missing(conn, table: str, column: str, col_type: str):
    """Add a column to a table if it doesn't already exist."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cursor.fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


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
    d["fit_summary"] = json.loads(d.get("fit_summary") or "[]")
    d["gap_analysis"] = json.loads(d.get("gap_analysis") or "[]")
    return Application(**d)


def _insert_app(conn: sqlite3.Connection, app: Application):
    """Insert or replace an application."""
    conn.execute("""
        INSERT OR REPLACE INTO applications
        (id, job_title, company, location, url, source, date_posted,
         date_generated, status, resume_path, cover_letter_path,
         ats_score, description, referrals, notes, fit_summary, gap_analysis)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        app.id, app.job_title, app.company, app.location, app.url,
        app.source, app.date_posted, app.date_generated, app.status,
        app.resume_path, app.cover_letter_path, app.ats_score,
        app.description, json.dumps([r.model_dump() for r in app.referrals]),
        app.notes,
        json.dumps(app.fit_summary),
        json.dumps(app.gap_analysis),
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


# ── Seen Jobs (scout) ────────────────────────────────────────────────────────

def load_seen_job_ids() -> set:
    with _get_conn() as conn:
        rows = conn.execute("SELECT job_id FROM seen_jobs").fetchall()
        return {r["job_id"] for r in rows}


def save_seen_job_ids(ids: set):
    with _get_conn() as conn:
        for job_id in ids:
            conn.execute(
                "INSERT OR IGNORE INTO seen_jobs (job_id) VALUES (?)", (job_id,)
            )


# ── Network Cache (linkedin) ─────────────────────────────────────────────────

def get_network_cache(cache_key: str, ttl_hours: int = 24) -> list[dict] | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT matches, timestamp FROM network_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if not row:
            return None
        from datetime import datetime, timedelta
        cached_time = datetime.fromisoformat(row["timestamp"])
        matches = json.loads(row["matches"])
        if not matches:
            return None  # don't use empty cache
        if datetime.now() - cached_time > timedelta(hours=ttl_hours):
            return None
        return matches


def save_network_cache(cache_key: str, matches: list[dict]):
    from datetime import datetime
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO network_cache (cache_key, matches, timestamp) VALUES (?, ?, ?)",
            (cache_key, json.dumps(matches), datetime.now().isoformat()),
        )


# ── Job Cache (scraper) ──────────────────────────────────────────────────────

def save_job_to_cache(job_data: dict):
    with _get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO job_cache
               (id, title, company, location, url, description, date_posted, source, salary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_data["id"], job_data.get("title", ""), job_data.get("company", ""),
                job_data.get("location", ""), job_data.get("url", ""),
                job_data.get("description", ""), job_data.get("date_posted", ""),
                job_data.get("source", ""), job_data.get("salary", ""),
            ),
        )


# ── Resume / Cover Letter Cache (generator) ──────────────────────────────────

def get_resume_cache_entries() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute("SELECT * FROM resume_cache ORDER BY timestamp DESC").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["ats_keywords"] = json.loads(d.get("ats_keywords") or "[]")
            d["hard_skills"] = json.loads(d.get("hard_skills") or "[]")
            d["soft_skills"] = json.loads(d.get("soft_skills") or "[]")
            d["matched_keywords"] = json.loads(d.get("matched_keywords") or "[]")
            result.append(d)
        return result


def save_resume_cache_entry(entry: dict):
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO resume_cache
               (timestamp, job_title, company, seniority_level, ats_keywords,
                hard_skills, soft_skills, ats_score, matched_keywords,
                resume_json_path, docx_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.get("timestamp", ""), entry.get("job_title", ""),
                entry.get("company", ""), entry.get("seniority_level", ""),
                json.dumps(entry.get("ats_keywords", [])),
                json.dumps(entry.get("hard_skills", [])),
                json.dumps(entry.get("soft_skills", [])),
                entry.get("ats_score", 0),
                json.dumps(entry.get("matched_keywords", [])),
                entry.get("resume_json_path", ""), entry.get("docx_path", ""),
            ),
        )


def get_cover_letter_cache_entries() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute("SELECT * FROM cover_letter_cache ORDER BY timestamp DESC").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["ats_keywords"] = json.loads(d.get("ats_keywords") or "[]")
            d["hard_skills"] = json.loads(d.get("hard_skills") or "[]")
            result.append(d)
        return result


def save_cover_letter_cache_entry(entry: dict):
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO cover_letter_cache
               (timestamp, job_title, company, seniority_level, ats_keywords,
                hard_skills, text_path, docx_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.get("timestamp", ""), entry.get("job_title", ""),
                entry.get("company", ""), entry.get("seniority_level", ""),
                json.dumps(entry.get("ats_keywords", [])),
                json.dumps(entry.get("hard_skills", [])),
                entry.get("text_path", ""), entry.get("docx_path", ""),
            ),
        )
