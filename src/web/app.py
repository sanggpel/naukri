"""FastAPI web dashboard for tracking job applications."""

import os

from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..models import NetworkMatch
from ..tracker import (
    delete_application,
    get_application,
    load_applications,
    update_notes,
    update_referrals,
    update_status,
)
from ..network.linkedin import find_connections_at_company

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates", "web")
STATIC_DIR = os.path.join(BASE_DIR, "static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)


def create_app() -> FastAPI:
    app = FastAPI(title="Job Application Tracker")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(
        request: Request,
        status: str = "all",
        q: str = "",
        company: str = "",
        source: str = "",
        remote: str = "",
    ):
        all_apps = load_applications()

        # Build filter options from all data
        companies = sorted({a.company for a in all_apps if a.company})
        sources = sorted({a.source for a in all_apps if a.source})

        # Stats (before filtering)
        statuses = ["all", "discovered", "generated", "applied", "interviewing", "offered", "rejected", "not_relevant", "withdrawn"]
        stats = {}
        for s in statuses[1:]:
            stats[s] = sum(1 for a in all_apps if a.status == s)
        stats["all"] = len(all_apps)

        # Apply filters
        apps = list(all_apps)
        if status != "all":
            apps = [a for a in apps if a.status == status]
        if q:
            q_lower = q.lower()
            apps = [a for a in apps if q_lower in a.job_title.lower() or q_lower in a.company.lower() or q_lower in a.description.lower()]
        if company:
            apps = [a for a in apps if a.company == company]
        if source:
            apps = [a for a in apps if a.source == source]
        if remote == "yes":
            apps = [a for a in apps if any(kw in (a.location + " " + a.job_title).lower() for kw in ["remote", "hybrid", "anywhere", "work from home"])]

        # Sort by date descending
        apps.sort(key=lambda a: a.date_generated, reverse=True)

        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "applications": apps,
            "current_status": status,
            "statuses": statuses,
            "stats": stats,
            "companies": companies,
            "sources": sources,
            "filters": {"q": q, "company": company, "source": source, "remote": remote},
        })

    @app.get("/application/{app_id}", response_class=HTMLResponse)
    async def detail(request: Request, app_id: str):
        app_data = get_application(app_id)
        if not app_data:
            return RedirectResponse("/", status_code=302)

        statuses = ["discovered", "generated", "applied", "interviewing", "offered", "rejected", "not_relevant", "withdrawn"]
        return templates.TemplateResponse("detail.html", {
            "request": request,
            "app": app_data,
            "statuses": statuses,
        })

    @app.post("/application/{app_id}/status")
    async def update_app_status(app_id: str, status: str = Form(...)):
        update_status(app_id, status)
        return RedirectResponse(f"/application/{app_id}", status_code=302)

    @app.post("/bulk-status")
    async def bulk_update_status(request: Request):
        form = await request.form()
        new_status = form.get("bulk_status", "not_relevant")
        selected = form.getlist("selected")
        for app_id in selected:
            update_status(app_id, new_status)
        return RedirectResponse("/", status_code=302)

    @app.post("/application/{app_id}/notes")
    async def update_app_notes(app_id: str, notes: str = Form(...)):
        update_notes(app_id, notes)
        return RedirectResponse(f"/application/{app_id}", status_code=302)

    @app.post("/application/{app_id}/delete")
    async def delete_app(app_id: str):
        delete_application(app_id)
        return RedirectResponse("/", status_code=302)

    @app.post("/application/{app_id}/referrals")
    async def fetch_referrals(app_id: str):
        app_data = get_application(app_id)
        if app_data and app_data.company:
            matches = find_connections_at_company(app_data.company)
            update_referrals(app_id, matches)
        return RedirectResponse(f"/application/{app_id}", status_code=302)

    @app.get("/download/{filename:path}")
    async def download_file(filename: str):
        # Try absolute path first, then relative to project root
        if os.path.isabs(filename) and os.path.exists(filename):
            path = filename
        else:
            path = os.path.abspath(os.path.join(BASE_DIR, filename))

        if not os.path.exists(path):
            return HTMLResponse("File not found", status_code=404)
        return FileResponse(path, filename=os.path.basename(path))

    return app
