"""Automated job scout — searches job boards and sends new matches to Telegram."""

import json
import logging
import os
from datetime import datetime

from ..models import JobListing
from ..profile_loader import load_settings
from .scraper import search_jobs

logger = logging.getLogger(__name__)

SEEN_JOBS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "seen_jobs.json")


def _load_seen_ids() -> set:
    """Load the set of job IDs we've already sent to the user."""
    if os.path.exists(SEEN_JOBS_PATH):
        with open(SEEN_JOBS_PATH, "r") as f:
            data = json.load(f)
            return set(data.get("ids", []))
    return set()


def _save_seen_ids(ids: set):
    os.makedirs(os.path.dirname(SEEN_JOBS_PATH), exist_ok=True)
    with open(SEEN_JOBS_PATH, "w") as f:
        json.dump({"ids": list(ids), "updated": datetime.now().isoformat()}, f)


def scout_jobs() -> list[JobListing]:
    """Run all configured search queries and return only NEW jobs not seen before."""
    settings = load_settings()
    scout_config = settings.get("scout", {})
    queries = scout_config.get("queries", [])
    location = scout_config.get("location", settings["discovery"]["default_location"])
    country = scout_config.get("country", settings["discovery"].get("default_country", "Canada"))
    sources = scout_config.get("sources", settings["discovery"]["default_sources"])
    max_per_query = scout_config.get("max_per_query", 15)
    remote_only = scout_config.get("remote_only", False)

    if not queries:
        logger.warning("No scout queries configured in settings.yaml")
        return []

    seen_ids = _load_seen_ids()
    new_jobs = []

    for query in queries:
        logger.info(f"Scouting: '{query}' in {location}")
        try:
            jobs = search_jobs(
                query=query,
                location=location,
                sources=sources,
                max_results=max_per_query,
                country=country,
            )

            for job in jobs:
                if job.id in seen_ids:
                    continue

                # Optional: filter remote-only
                if remote_only:
                    loc_lower = job.location.lower()
                    title_lower = job.title.lower()
                    if not any(kw in loc_lower or kw in title_lower for kw in ["remote", "hybrid", "anywhere"]):
                        continue

                new_jobs.append(job)
                seen_ids.add(job.id)

        except Exception as e:
            logger.error(f"Scout error for '{query}': {e}")

    _save_seen_ids(seen_ids)
    logger.info(f"Scout complete: {len(new_jobs)} new jobs found")
    return new_jobs


def format_scout_message(jobs: list[JobListing], batch_size: int = 5) -> list[str]:
    """Format new jobs into Telegram messages (split into batches to avoid message limits)."""
    if not jobs:
        return []

    messages = []
    for i in range(0, len(jobs), batch_size):
        batch = jobs[i : i + batch_size]
        lines = [f"Found {len(jobs)} new jobs for you:\n"] if i == 0 else []

        for j, job in enumerate(batch, start=i + 1):
            lines.append(f"*{j}. {job.title}*")
            lines.append(f"   {job.company} — {job.location}")
            if job.source:
                lines.append(f"   Source: {job.source}")
            if job.url:
                lines.append(f"   {job.url}")
            lines.append("")

        messages.append("\n".join(lines))

    return messages
