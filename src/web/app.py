"""FastAPI web dashboard for tracking job applications."""

import os

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..models import Application, NetworkMatch
from ..tracker import (
    delete_application,
    get_application,
    load_applications,
    save_application,
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
        scout_added: str = "",
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
            "scout_added": int(scout_added) if scout_added.isdigit() else None,
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

    @app.post("/application/{app_id}/generate")
    async def generate_docs(app_id: str):
        """Generate resume + cover letter for a tracked application."""
        app_data = get_application(app_id)
        if not app_data or not app_data.description:
            return RedirectResponse(f"/application/{app_id}", status_code=302)

        from ..generator.cache import (
            adapt_cover_letter,
            find_cached_cover_letter,
            find_cached_resume,
            save_cover_letter_to_cache,
            save_resume_to_cache,
        )
        from ..generator.cover_letter import generate_cover_letter
        from ..generator.keywords import extract_keywords
        from ..generator.renderer import render_cover_letter_pdf, render_resume_pdf
        from ..generator.resume import generate_resume
        from ..profile_loader import load_profile

        profile = load_profile()
        keywords = extract_keywords(app_data.description)
        job_title = app_data.job_title or keywords.job_title
        company = app_data.company or keywords.company_name

        # Resume: reuse cached or generate new
        cached_resume, cached_path, _ = find_cached_resume(keywords)
        if cached_resume and cached_path and os.path.exists(cached_path):
            resume = cached_resume
            resume_path = cached_path
        else:
            resume = generate_resume(profile, app_data.description, keywords)
            resume_path = render_resume_pdf(resume, profile.name)
            save_resume_to_cache(keywords, resume, resume_path, job_title, company)

        # Cover letter: reuse/adapt or generate new
        cached_cl_text, cached_cl_entry = find_cached_cover_letter(keywords)
        if cached_cl_text and cached_cl_entry:
            old_co = cached_cl_entry.get("company", "")
            old_title = cached_cl_entry.get("job_title", "")
            cover_letter = adapt_cover_letter(cached_cl_text, company, job_title, old_co, old_title)
            cl_path = render_cover_letter_pdf(cover_letter, profile.name)
        else:
            cover_letter = generate_cover_letter(profile, app_data.description, keywords)
            cl_path = render_cover_letter_pdf(cover_letter, profile.name)
            save_cover_letter_to_cache(keywords, cover_letter, cl_path, job_title, company)

        # Update application record
        app_data.resume_path = os.path.abspath(resume_path)
        app_data.cover_letter_path = os.path.abspath(cl_path)
        app_data.ats_score = resume.ats_score_estimate
        if app_data.status == "discovered":
            app_data.status = "generated"
        save_application(app_data)

        return RedirectResponse(f"/application/{app_id}", status_code=302)

    @app.post("/application/{app_id}/referrals")
    async def fetch_referrals(request: Request, app_id: str):
        app_data = get_application(app_id)
        error_msg = None
        if app_data and app_data.company:
            try:
                matches = find_connections_at_company(app_data.company)
                update_referrals(app_id, matches)
                if not matches:
                    error_msg = f"No connections found at {app_data.company} in your LinkedIn network."
            except Exception as e:
                error_msg = str(e)

        if error_msg:
            # Re-render detail page with the error shown
            app_data = get_application(app_id)
            statuses = ["discovered", "generated", "applied", "interviewing", "offered", "rejected", "not_relevant", "withdrawn"]
            return templates.TemplateResponse("detail.html", {
                "request": request,
                "app": app_data,
                "statuses": statuses,
                "referral_error": error_msg,
            })
        return RedirectResponse(f"/application/{app_id}", status_code=302)

    @app.post("/scout")
    async def run_scout(request: Request):
        """Run the job scout and add new relevant jobs to the tracker."""
        from datetime import datetime
        from ..discovery.scout import scout_jobs

        try:
            jobs = scout_jobs()
        except Exception as e:
            # Re-render dashboard with error banner
            all_apps = load_applications()
            statuses = ["all", "discovered", "generated", "applied", "interviewing", "offered", "rejected", "not_relevant", "withdrawn"]
            stats = {s: sum(1 for a in all_apps if a.status == s) for s in statuses[1:]}
            stats["all"] = len(all_apps)
            companies = sorted({a.company for a in all_apps if a.company})
            sources = sorted({a.source for a in all_apps if a.source})
            return templates.TemplateResponse("dashboard.html", {
                "request": request,
                "applications": all_apps,
                "current_status": "all",
                "statuses": statuses,
                "stats": stats,
                "companies": companies,
                "sources": sources,
                "filters": {"q": "", "company": "", "source": "", "remote": ""},
                "scout_error": str(e),
            })

        added = 0
        for job in jobs:
            existing = get_application(job.id)
            if existing:
                continue
            app_record = Application(
                id=job.id,
                job_title=job.title,
                company=job.company,
                location=job.location,
                url=job.url,
                source=job.source,
                date_posted=job.date_posted,
                date_generated=datetime.now().isoformat(),
                status="discovered",
                description=job.description,
            )
            save_application(app_record)
            added += 1

        return RedirectResponse(f"/?status=discovered&scout_added={added}", status_code=302)

    @app.get("/view/{filename:path}")
    async def view_file(filename: str):
        """Extract and return formatted HTML content from a DOCX or text file."""
        if os.path.isabs(filename) and os.path.exists(filename):
            path = filename
        else:
            path = os.path.abspath(os.path.join(BASE_DIR, filename))

        if not os.path.exists(path):
            return JSONResponse({"html": "<p>File not found.</p>", "text": "File not found."}, status_code=404)

        if path.endswith(".docx"):
            html, text = _docx_to_html(path)
        elif path.endswith(".txt"):
            with open(path, "r") as f:
                text = f.read()
            import html as html_mod
            html = f"<pre style='white-space:pre-wrap;font-family:inherit;'>{html_mod.escape(text)}</pre>"
        elif path.endswith(".pdf"):
            html = "<p>(PDF preview not supported — use the download link.)</p>"
            text = "(PDF preview not supported — use the download link.)"
        else:
            html = "<p>(Unsupported file format.)</p>"
            text = "(Unsupported file format.)"

        return JSONResponse({"html": html, "text": text})

    def _docx_to_html(path: str) -> tuple[str, str]:
        """Convert a DOCX file to styled HTML and plain text."""
        import html as html_mod
        from docx import Document
        from docx.shared import Pt

        doc = Document(path)
        html_parts = []
        text_parts = []

        for para in doc.paragraphs:
            raw = para.text.strip()
            if not raw:
                continue

            text_parts.append(raw)

            # Detect formatting from runs
            is_all_bold = all(r.bold for r in para.runs if r.text.strip()) if para.runs else False
            font_size = None
            for r in para.runs:
                if r.font.size:
                    font_size = r.font.size
                    break

            escaped = html_mod.escape(raw)

            # Large bold = name header (22pt)
            if is_all_bold and font_size and font_size >= Pt(18):
                html_parts.append(f'<div style="font-size:1.6rem;font-weight:700;letter-spacing:0.5px;margin-bottom:2px;">{escaped}</div>')
            # Contact line (small, gray)
            elif font_size and font_size <= Pt(10) and "|" in raw:
                html_parts.append(f'<div style="font-size:0.85rem;color:#555;margin-bottom:12px;">{escaped}</div>')
            # Section headings (bold uppercase with border)
            elif is_all_bold and raw == raw.upper() and len(raw) > 3 and not raw.startswith("\u2022"):
                html_parts.append(
                    f'<div style="font-size:0.9rem;font-weight:700;text-transform:uppercase;'
                    f'border-bottom:1.5px solid #1a1a2e;padding-bottom:4px;margin:16px 0 8px;color:#1a1a2e;">{escaped}</div>'
                )
            # Job title lines (bold, with em-dash)
            elif is_all_bold and ("\u2014" in raw or " — " in raw):
                html_parts.append(f'<div style="font-weight:600;margin-top:10px;margin-bottom:2px;">{escaped}</div>')
            # Mixed bold/normal (e.g. "Category: skill, skill")
            elif any(r.bold for r in para.runs if r.text.strip()) and not all(r.bold for r in para.runs if r.text.strip()):
                parts = []
                for r in para.runs:
                    t = html_mod.escape(r.text)
                    if r.bold:
                        parts.append(f"<strong>{t}</strong>")
                    else:
                        parts.append(t)
                html_parts.append(f'<div style="margin-bottom:3px;">{"".join(parts)}</div>')
            # Bullet points
            elif raw.startswith("\u2022"):
                bullet_text = escaped.lstrip("\u2022").strip()
                html_parts.append(
                    f'<div style="padding-left:20px;margin-bottom:3px;position:relative;">'
                    f'<span style="position:absolute;left:4px;">&bull;</span>{bullet_text}</div>'
                )
            # Bold paragraph (e.g. sign-off name)
            elif is_all_bold:
                html_parts.append(f'<div style="font-weight:600;margin:4px 0;">{escaped}</div>')
            # Regular paragraph
            else:
                html_parts.append(f'<div style="margin-bottom:6px;">{escaped}</div>')

        return "\n".join(html_parts), "\n".join(text_parts)

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

    @app.get("/pdf/{filename:path}")
    async def download_as_pdf(filename: str):
        """Serve file as PDF — converts DOCX to PDF on the fly if needed."""
        if os.path.isabs(filename) and os.path.exists(filename):
            path = filename
        else:
            path = os.path.abspath(os.path.join(BASE_DIR, filename))

        if not os.path.exists(path):
            return HTMLResponse("File not found", status_code=404)

        # Already a PDF — serve directly
        if path.endswith(".pdf"):
            stem = os.path.splitext(os.path.basename(path))[0]
            return FileResponse(path, filename=f"{stem}.pdf", media_type="application/pdf")

        # Convert DOCX → PDF via WeasyPrint (renders through HTML intermediate)
        if path.endswith(".docx"):
            pdf_path = path.replace(".docx", ".pdf")
            if not os.path.exists(pdf_path):
                pdf_path = _docx_to_pdf(path)
            stem = os.path.splitext(os.path.basename(path))[0]
            return FileResponse(pdf_path, filename=f"{stem}.pdf", media_type="application/pdf")

        return HTMLResponse("Cannot convert this file type to PDF", status_code=415)

    def _docx_to_pdf(docx_path: str) -> str:
        """Convert a DOCX file to PDF using WeasyPrint via an HTML intermediate."""
        import html as html_mod
        from docx import Document
        from weasyprint import HTML as WP_HTML

        doc = Document(docx_path)
        paragraphs_html = []

        for para in doc.paragraphs:
            raw = para.text
            if not raw.strip():
                paragraphs_html.append('<p style="margin:4px 0;">&nbsp;</p>')
                continue

            escaped = html_mod.escape(raw)
            is_all_bold = all(r.bold for r in para.runs if r.text.strip()) if para.runs else False
            font_size = None
            for r in para.runs:
                if r.font.size:
                    font_size = r.font.size
                    break

            from docx.shared import Pt

            if is_all_bold and font_size and font_size >= Pt(18):
                paragraphs_html.append(f'<p style="font-size:22pt;font-weight:700;margin:0 0 2px;">{escaped}</p>')
            elif font_size and font_size and font_size <= Pt(10) and "|" in raw:
                paragraphs_html.append(f'<p style="font-size:9pt;color:#444;margin:0 0 10px;">{escaped}</p>')
            elif is_all_bold and raw.strip() == raw.strip().upper() and len(raw.strip()) > 3:
                paragraphs_html.append(
                    f'<p style="font-size:10pt;font-weight:700;text-transform:uppercase;'
                    f'border-bottom:1px solid #000;padding-bottom:2px;margin:12px 0 5px;">{escaped}</p>'
                )
            elif is_all_bold and ("—" in raw or " — " in raw):
                paragraphs_html.append(f'<p style="font-size:10.5pt;font-weight:700;margin:8px 0 1px;">{escaped}</p>')
            elif raw.strip().startswith("•"):
                bullet = html_mod.escape(raw.strip().lstrip("•").strip())
                paragraphs_html.append(f'<p style="font-size:10pt;margin:1px 0 1px 18px;text-indent:-12px;">• {bullet}</p>')
            elif any(r.bold for r in para.runs if r.text.strip()):
                parts = []
                for r in para.runs:
                    t = html_mod.escape(r.text)
                    parts.append(f"<strong>{t}</strong>" if r.bold else t)
                paragraphs_html.append(f'<p style="font-size:10pt;margin:1px 0;">{"".join(parts)}</p>')
            else:
                paragraphs_html.append(f'<p style="font-size:10pt;margin:4px 0;">{escaped}</p>')

        html_content = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  @page {{ margin: 0.6in 0.75in; }}
  body {{ font-family: Calibri, Arial, sans-serif; font-size: 10pt; color: #000; line-height: 1.3; }}
  p {{ margin: 0; }}
</style>
</head><body>{"".join(paragraphs_html)}</body></html>"""

        pdf_path = docx_path.replace(".docx", ".pdf")
        WP_HTML(string=html_content).write_pdf(pdf_path)
        return pdf_path

    return app
