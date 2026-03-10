"""Application tracker — CRUD for tracking job applications."""

import json
import os
from datetime import datetime

from .models import Application, NetworkMatch

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "applications.json")


def _ensure_data_dir():
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)


def load_applications() -> list[Application]:
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r") as f:
            data = json.load(f)
            return [Application(**a) for a in data]
    return []


def _save_all(apps: list[Application]):
    _ensure_data_dir()
    with open(DATA_PATH, "w") as f:
        json.dump([a.model_dump() for a in apps], f, indent=2)


def get_application(app_id: str) -> Application | None:
    for app in load_applications():
        if app.id == app_id:
            return app
    return None


def save_application(app: Application):
    apps = load_applications()
    # Update existing or append new
    for i, existing in enumerate(apps):
        if existing.id == app.id:
            apps[i] = app
            _save_all(apps)
            return
    apps.append(app)
    _save_all(apps)


def update_status(app_id: str, status: str, notes: str | None = None):
    apps = load_applications()
    for app in apps:
        if app.id == app_id:
            app.status = status
            if notes is not None:
                app.notes = notes
            _save_all(apps)
            return True
    return False


def update_notes(app_id: str, notes: str):
    apps = load_applications()
    for app in apps:
        if app.id == app_id:
            app.notes = notes
            _save_all(apps)
            return True
    return False


def update_referrals(app_id: str, referrals: list[NetworkMatch]):
    apps = load_applications()
    for app in apps:
        if app.id == app_id:
            app.referrals = referrals
            _save_all(apps)
            return True
    return False


def delete_application(app_id: str) -> bool:
    apps = load_applications()
    filtered = [a for a in apps if a.id != app_id]
    if len(filtered) < len(apps):
        _save_all(filtered)
        return True
    return False
