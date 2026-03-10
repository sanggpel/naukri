"""Job discovery using python-jobspy to search multiple job boards."""

import hashlib
import json
import os

from jobspy import scrape_jobs

from ..models import JobListing


def search_jobs(
    query: str,
    location: str = "Calgary, AB, Canada",
    sources: list[str] | None = None,
    max_results: int = 30,
    country: str = "Canada",
) -> list[JobListing]:
    """Search job boards and return structured job listings."""
    if sources is None:
        sources = ["indeed", "linkedin", "glassdoor"]

    try:
        df = scrape_jobs(
            site_name=sources,
            search_term=query,
            location=location,
            results_wanted=max_results,
            country_indeed=country,
            hours_old=72,
        )
    except Exception as e:
        print(f"JobSpy scrape error: {e}")
        return []

    def _clean(val, default=""):
        """Convert pandas value to string, treating NaN as empty."""
        s = str(val) if val is not None else default
        return default if s in ("nan", "None", "NaN") else s

    jobs = []
    for _, row in df.iterrows():
        job_id = hashlib.md5(
            f"{row.get('title', '')}{row.get('company', '')}{row.get('job_url', '')}".encode()
        ).hexdigest()[:12]

        job = JobListing(
            id=job_id,
            title=_clean(row.get("title")),
            company=_clean(row.get("company")),
            location=_clean(row.get("location")),
            url=_clean(row.get("job_url")),
            description=_clean(row.get("description")),
            date_posted=_clean(row.get("date_posted")),
            source=_clean(row.get("site")),
            salary=_clean(row.get("min_amount")),
        )
        jobs.append(job)
        _save_job(job)

    return jobs


def _save_job(job: JobListing):
    """Cache job listing to disk."""
    data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "jobs")
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, f"{job.id}.json")
    with open(path, "w") as f:
        json.dump(job.model_dump(), f, indent=2)
