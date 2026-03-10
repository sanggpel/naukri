"""Telegram bot command and message handlers."""

import logging
import os
import re
import traceback

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ..discovery.parser import parse_job_url
from ..discovery.scraper import search_jobs
from ..discovery.scout import scout_jobs, format_scout_message
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
from ..models import Application, JobListing
from ..network.linkedin import find_connections_at_company, format_referral_message
from ..profile_loader import load_profile, load_settings
from ..tracker import get_application, save_application

logger = logging.getLogger(__name__)

# Load profile once at module level
_profile = None
_settings = None


def _get_profile():
    global _profile
    if _profile is None:
        _profile = load_profile()
    return _profile


def _get_settings():
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def _save_chat_id(chat_id: int):
    """Save the user's chat ID so scheduled jobs can message them."""
    import yaml
    settings_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "settings.yaml")
    settings_path = os.path.abspath(settings_path)
    with open(settings_path, "r") as f:
        data = yaml.safe_load(f)
    if data.get("scout", {}).get("chat_id") != chat_id:
        data.setdefault("scout", {})["chat_id"] = chat_id
        with open(settings_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        logger.info(f"Saved chat_id: {chat_id}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    profile = _get_profile()

    # Save chat_id for scheduled scout messages
    chat_id = update.effective_chat.id
    _save_chat_id(chat_id)

    await update.message.reply_text(
        f"Hello {profile.name.split()[0]}! I'm your Job Application Assistant.\n\n"
        "Here's what I can do:\n\n"
        "/apply <url> - Generate custom resume & cover letter for a job\n"
        "/search <query> - Search job boards for opportunities\n"
        "/scout - Find new jobs matching your profile NOW\n"
        "/referrals <company> - Find LinkedIn connections at a company\n"
        "/profile - View your loaded profile summary\n"
        "/help - Show this help message\n\n"
        "I'll also automatically scout for new jobs every 6 hours!\n\n"
        "Or just paste a job URL and I'll generate your application materials!"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    await update.message.reply_text(
        "**Job Application Assistant Commands:**\n\n"
        "/apply <url> - Paste a job URL to generate:\n"
        "  - ATS-optimized resume (PDF)\n"
        "  - Custom cover letter (PDF)\n"
        "  - LinkedIn referral suggestions\n\n"
        "/search <query> - Search job boards\n"
        "  Example: /search senior product manager Calgary\n\n"
        "/referrals <company> - Find your LinkedIn connections\n"
        "  Example: /referrals Google\n\n"
        "/scout - Search job boards for new matching roles NOW\n\n"
        "/profile - Show your profile summary\n\n"
        "**Auto-scout:** I search for new jobs every 6 hours automatically!\n"
        "**Quick tip:** Just paste any job URL directly and I'll process it!",
        parse_mode="Markdown",
    )


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /profile command."""
    profile = _get_profile()
    skills_preview = ", ".join(profile.all_skills_flat()[:15])
    recent_roles = "\n".join(
        f"  - {exp.title} at {exp.company}" for exp in profile.experience[:4]
    )
    await update.message.reply_text(
        f"**Your Profile:**\n\n"
        f"**Name:** {profile.name}\n"
        f"**Location:** {profile.location}\n"
        f"**LinkedIn:** {profile.linkedin_url}\n\n"
        f"**Recent Roles:**\n{recent_roles}\n\n"
        f"**Key Skills:** {skills_preview}...\n\n"
        f"**Certifications:** {len(profile.certifications)} loaded\n"
        f"**Experience entries:** {len(profile.experience)}",
        parse_mode="Markdown",
    )


async def apply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /apply <url> command - generate resume + cover letter for a job."""
    if not context.args:
        await update.message.reply_text(
            "Please provide a job URL.\nUsage: /apply <job_url>\n\n"
            "Or just paste the URL directly!"
        )
        return

    url = context.args[0]
    await _process_job_url(update, context, url)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search <query> command - search job boards."""
    if not context.args:
        await update.message.reply_text(
            "Please provide a search query.\n"
            "Usage: /search senior product manager Calgary"
        )
        return

    query = " ".join(context.args)
    settings = _get_settings()

    await update.message.reply_text(f"Searching for: *{query}*...", parse_mode="Markdown")

    try:
        jobs = search_jobs(
            query=query,
            location=settings["discovery"]["default_location"],
            max_results=10,
            country=settings["discovery"].get("default_country", "Canada"),
        )
    except Exception as e:
        await update.message.reply_text(f"Search error: {e}")
        return

    if not jobs:
        await update.message.reply_text("No jobs found. Try a different query.")
        return

    # Store jobs in context for callback handling
    context.user_data["search_results"] = jobs

    # Build results message with inline buttons
    msg = f"Found {len(jobs)} jobs:\n\n"
    buttons = []
    for i, job in enumerate(jobs[:10]):
        msg += f"**{i+1}.** {job.title}\n"
        msg += f"    {job.company} - {job.location}\n"
        if job.url:
            msg += f"    {job.url}\n"
        msg += "\n"
        buttons.append(
            [InlineKeyboardButton(f"Apply to #{i+1}: {job.title[:30]}", callback_data=f"apply_{i}")]
        )

    keyboard = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)


async def referrals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /referrals <company> command."""
    if not context.args:
        await update.message.reply_text(
            "Please provide a company name.\nUsage: /referrals Google"
        )
        return

    company = " ".join(context.args)
    await update.message.reply_text(f"Searching your LinkedIn network for connections at *{company}*...", parse_mode="Markdown")

    try:
        matches = find_connections_at_company(company)
        message = format_referral_message(matches)
        await update.message.reply_text(message)
    except Exception as e:
        await update.message.reply_text(
            f"Could not search LinkedIn network: {e}\n\n"
            "Make sure LINKEDIN_EMAIL and LINKEDIN_PASSWORD are set in your .env file."
        )


async def handle_url_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain URLs pasted by the user."""
    text = update.message.text.strip()

    # Check if the message contains a URL
    url_pattern = re.compile(r'https?://\S+')
    match = url_pattern.search(text)

    if match:
        url = match.group(0)
        await _process_job_url(update, context, url)
    else:
        await update.message.reply_text(
            "I didn't recognize that as a job URL. Try:\n"
            "- Paste a job posting URL\n"
            "- /search <query> to find jobs\n"
            "- /help for all commands"
        )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()

    if query.data.startswith("apply_"):
        index = int(query.data.split("_")[1])
        jobs = context.user_data.get("search_results", [])
        if index < len(jobs):
            job = jobs[index]
            if job.url:
                await query.message.reply_text(f"Generating application for: *{job.title}* at *{job.company}*...", parse_mode="Markdown")
                await _process_job_listing(query.message, context, job)
            else:
                await query.message.reply_text("No URL available for this job.")
        else:
            await query.message.reply_text("Job not found in results.")

    elif query.data.startswith("scout_apply_"):
        index = int(query.data.split("_")[2])
        jobs = context.user_data.get("scout_results", [])
        if index < len(jobs):
            job = jobs[index]
            if job.url:
                await query.message.reply_text(f"Generating application for: *{job.title}* at *{job.company}*...", parse_mode="Markdown")
                await _process_job_listing(query.message, context, job)
            else:
                await query.message.reply_text("No URL available for this job.")
        else:
            await query.message.reply_text("Job not found in results.")

    elif query.data.startswith("referral_"):
        company = query.data.split("_", 1)[1]
        await query.message.reply_text(f"Searching LinkedIn for connections at *{company}*...", parse_mode="Markdown")
        try:
            matches = find_connections_at_company(company)
            message = format_referral_message(matches)
            await query.message.reply_text(message)
        except Exception as e:
            await query.message.reply_text(f"LinkedIn search error: {e}")


def _track_discovered_jobs(jobs: list[JobListing]):
    """Save scouted jobs to the dashboard tracker with 'discovered' status."""
    from datetime import datetime
    for job in jobs:
        if not job.id:
            continue
        # Don't overwrite if already tracked (e.g. already applied)
        if get_application(job.id):
            continue
        app = Application(
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
        save_application(app)


async def scout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /scout command - search job boards for new matching roles NOW."""
    await update.message.reply_text("Scouting job boards for new roles matching your profile...")

    try:
        new_jobs = scout_jobs()
    except Exception as e:
        await update.message.reply_text(f"Scout error: {e}")
        return

    if not new_jobs:
        await update.message.reply_text(
            "No new jobs found since last scout.\n"
            "I'll keep checking automatically every few hours!"
        )
        return

    # Track all discovered jobs in the dashboard
    _track_discovered_jobs(new_jobs)

    messages = format_scout_message(new_jobs)
    for msg in messages:
        await update.message.reply_text(msg, parse_mode="Markdown")

    # Offer to apply for any of them
    buttons = []
    for i, job in enumerate(new_jobs[:10]):
        if job.url:
            buttons.append(
                [InlineKeyboardButton(
                    f"Apply to: {job.title[:30]} @ {job.company[:15]}",
                    callback_data=f"scout_apply_{i}",
                )]
            )
    if buttons:
        context.user_data["scout_results"] = new_jobs
        keyboard = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(
            "Tap any job to generate your resume & cover letter:",
            reply_markup=keyboard,
        )


async def scheduled_scout(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled callback: scout for new jobs and send to user via Telegram."""
    settings = _get_settings()
    chat_id = settings.get("scout", {}).get("chat_id")
    if not chat_id:
        logger.warning("Scout: no chat_id configured. Send /start to the bot first.")
        return

    logger.info("Running scheduled job scout...")
    try:
        new_jobs = scout_jobs()
    except Exception as e:
        logger.error(f"Scheduled scout error: {e}")
        return

    if not new_jobs:
        logger.info("Scheduled scout: no new jobs found.")
        return

    # Track all discovered jobs in the dashboard
    _track_discovered_jobs(new_jobs)

    messages = format_scout_message(new_jobs)
    for msg in messages:
        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

    logger.info(f"Scheduled scout: sent {len(new_jobs)} new jobs to chat {chat_id}.")


async def _process_job_url(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Core flow: parse URL -> extract keywords -> generate resume + cover letter."""
    await update.message.reply_text("Parsing job posting...")

    try:
        job = parse_job_url(url)
    except Exception as e:
        await update.message.reply_text(f"Error parsing URL: {e}")
        return

    if not job.description:
        await update.message.reply_text(
            "Could not extract job description from that URL. "
            "The page might be behind a login wall. "
            "Try copying the job description and sending it directly."
        )
        return

    title_info = f"*{job.title}*" if job.title else "this role"
    company_info = f" at *{job.company}*" if job.company else ""
    await update.message.reply_text(
        f"Found: {title_info}{company_info}\n"
        "Generating your custom resume and cover letter...\n"
        "(This takes about 30-60 seconds)",
        parse_mode="Markdown",
    )

    await _process_job_listing(update.message, context, job)


async def _process_job_listing(message, context: ContextTypes.DEFAULT_TYPE, job: JobListing):
    """Generate resume + cover letter for a parsed job listing."""
    profile = _get_profile()

    try:
        # Step 1: Extract keywords
        keywords = extract_keywords(job.description)
        await message.reply_text(
            f"ATS Keywords found: {', '.join(keywords.ats_keywords[:10])}\n"
            f"Seniority: {keywords.seniority_level}"
        )

        job_title = job.title or keywords.job_title
        company = job.company or keywords.company_name

        # Step 2: Generate or reuse resume
        cached_resume, cached_resume_path, cached_entry = find_cached_resume(keywords)
        if cached_resume and cached_resume_path and os.path.exists(cached_resume_path):
            resume = cached_resume
            resume_path = cached_resume_path
            old_job = cached_entry.get("job_title", "") if cached_entry else ""
            old_co = cached_entry.get("company", "") if cached_entry else ""
            await message.reply_text(
                f"Reusing existing resume (ATS score: {resume.ats_score_estimate}/100)\n"
                f"Previously generated for: {old_job} at {old_co}"
            )
        else:
            resume = generate_resume(profile, job.description, keywords)
            resume_path = render_resume_pdf(resume, profile.name)
            save_resume_to_cache(keywords, resume, resume_path, job_title, company)
            await message.reply_text(f"Resume generated! ATS match score: {resume.ats_score_estimate}/100")

        # Step 3: Generate or adapt cover letter
        cached_cl_text, cached_cl_entry = find_cached_cover_letter(keywords)
        if cached_cl_text and cached_cl_entry:
            old_co = cached_cl_entry.get("company", "")
            old_title = cached_cl_entry.get("job_title", "")
            cover_letter = adapt_cover_letter(cached_cl_text, company, job_title, old_co, old_title)
            cl_path = render_cover_letter_pdf(cover_letter, profile.name)
            await message.reply_text(
                f"Adapted existing cover letter for {company}\n"
                f"(Based on letter for: {old_title} at {old_co})"
            )
        else:
            cover_letter = generate_cover_letter(profile, job.description, keywords)
            cl_path = render_cover_letter_pdf(cover_letter, profile.name)
            save_cover_letter_to_cache(keywords, cover_letter, cl_path, job_title, company)
            await message.reply_text("Cover letter generated!")

        # Step 5: Send files (each independently so one failure doesn't block the other)
        resume_ext = os.path.splitext(resume_path)[1]
        cl_ext = os.path.splitext(cl_path)[1]

        try:
            with open(resume_path, "rb") as f:
                await message.reply_document(
                    document=f,
                    filename=f"Resume_{job.company or 'Custom'}_{job.title or 'Role'}{resume_ext}".replace(" ", "_"),
                    caption=f"Your tailored resume (ATS Score: {resume.ats_score_estimate}/100)",
                    read_timeout=60, write_timeout=60,
                )
        except Exception as send_err:
            logger.error(f"Error sending resume: {send_err}")
            await message.reply_text(f"Resume saved locally but failed to send: {send_err}")

        try:
            with open(cl_path, "rb") as f:
                await message.reply_document(
                    document=f,
                    filename=f"CoverLetter_{job.company or 'Custom'}_{job.title or 'Role'}{cl_ext}".replace(" ", "_"),
                    caption="Your tailored cover letter",
                    read_timeout=60, write_timeout=60,
                )
        except Exception as send_err:
            logger.error(f"Error sending cover letter: {send_err}")
            await message.reply_text(f"Cover letter saved locally but failed to send: {send_err}")

        # Step 6: Track application in dashboard
        from datetime import datetime
        app_record = Application(
            id=job.id or f"{company}_{job_title}".replace(" ", "_")[:20],
            job_title=job_title,
            company=company,
            location=job.location,
            url=job.url,
            source=job.source,
            date_posted=job.date_posted,
            date_generated=datetime.now().isoformat(),
            status="generated",
            resume_path=os.path.abspath(resume_path),
            cover_letter_path=os.path.abspath(cl_path),
            ats_score=resume.ats_score_estimate,
            description=job.description,
        )
        save_application(app_record)
        logger.info(f"Tracked application: {job_title} at {company}")

        # Step 7: Offer referral search
        company = job.company or keywords.company_name
        if company:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    f"Find referrals at {company}",
                    callback_data=f"referral_{company}",
                )]
            ])
            await message.reply_text(
                f"Want to find someone who can refer you at *{company}*?",
                parse_mode="Markdown",
                reply_markup=keyboard,
            )

    except Exception as e:
        logger.error(f"Error generating application: {traceback.format_exc()}")
        await message.reply_text(
            f"Error generating application materials: {e}\n\n"
            "Check the bot logs for details."
        )
