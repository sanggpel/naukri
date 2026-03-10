"""Cache generated resumes and cover letters for reuse across similar roles."""

import json
import os
from datetime import datetime

from ..models import ExtractedKeywords, GeneratedResume, ResumeSection

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cache")
RESUME_INDEX = os.path.join(CACHE_DIR, "resume_index.json")
CL_INDEX = os.path.join(CACHE_DIR, "cl_index.json")

# Minimum keyword overlap to consider a cached resume a match
KEYWORD_MATCH_THRESHOLD = 0.6


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _load_index(path: str) -> list[dict]:
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []


def _save_index(path: str, index: list[dict]):
    _ensure_cache_dir()
    with open(path, "w") as f:
        json.dump(index, f, indent=2)


def _keyword_overlap(keywords_a: list[str], keywords_b: list[str]) -> float:
    """Calculate overlap ratio between two keyword lists (case-insensitive)."""
    if not keywords_a or not keywords_b:
        return 0.0
    set_a = {k.lower().strip() for k in keywords_a}
    set_b = {k.lower().strip() for k in keywords_b}
    intersection = set_a & set_b
    # Overlap relative to the smaller set
    smaller = min(len(set_a), len(set_b))
    return len(intersection) / smaller if smaller > 0 else 0.0


# ── Resume Cache ──────────────────────────────────────────────────


def find_cached_resume(keywords: ExtractedKeywords) -> tuple[GeneratedResume | None, str | None, dict | None]:
    """Find a cached resume that matches the given keywords.

    Returns (resume, file_path, cache_entry) or (None, None, None) if no match.
    """
    index = _load_index(RESUME_INDEX)
    target_keywords = keywords.ats_keywords + keywords.hard_skills

    best_match = None
    best_overlap = 0.0

    for entry in index:
        cached_keywords = entry.get("ats_keywords", []) + entry.get("hard_skills", [])
        overlap = _keyword_overlap(target_keywords, cached_keywords)

        # Also check seniority level match
        same_seniority = entry.get("seniority_level", "").lower() == keywords.seniority_level.lower()

        # Boost overlap score if seniority matches
        effective_overlap = overlap + (0.1 if same_seniority else 0)

        if effective_overlap > best_overlap and overlap >= KEYWORD_MATCH_THRESHOLD:
            best_overlap = effective_overlap
            best_match = entry

    if best_match:
        resume_path = best_match.get("resume_json_path")
        if resume_path and os.path.exists(resume_path):
            with open(resume_path, "r") as f:
                data = json.load(f)
            sections = ResumeSection(**data["sections"])
            resume = GeneratedResume(
                sections=sections,
                matched_keywords=data.get("matched_keywords", []),
                ats_score_estimate=data.get("ats_score_estimate", 0),
            )
            return resume, best_match.get("docx_path"), best_match
    return None, None, None


def save_resume_to_cache(
    keywords: ExtractedKeywords,
    resume: GeneratedResume,
    docx_path: str,
    job_title: str = "",
    company: str = "",
):
    """Save a generated resume to the cache index."""
    _ensure_cache_dir()

    # Save the resume JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(CACHE_DIR, f"resume_{timestamp}.json")
    with open(json_path, "w") as f:
        json.dump(resume.model_dump(), f, indent=2)

    # Add to index
    index = _load_index(RESUME_INDEX)
    index.append({
        "timestamp": datetime.now().isoformat(),
        "job_title": job_title,
        "company": company,
        "seniority_level": keywords.seniority_level,
        "ats_keywords": keywords.ats_keywords,
        "hard_skills": keywords.hard_skills,
        "soft_skills": keywords.soft_skills,
        "ats_score": resume.ats_score_estimate,
        "matched_keywords": resume.matched_keywords,
        "resume_json_path": json_path,
        "docx_path": docx_path,
    })
    _save_index(RESUME_INDEX, index)


# ── Cover Letter Cache ────────────────────────────────────────────


def find_cached_cover_letter(keywords: ExtractedKeywords) -> tuple[str | None, dict | None]:
    """Find a cached cover letter body that can be adapted.

    Returns (cover_letter_text, cache_entry) or (None, None) if no match.
    """
    index = _load_index(CL_INDEX)
    target_keywords = keywords.ats_keywords + keywords.hard_skills

    best_match = None
    best_overlap = 0.0

    for entry in index:
        cached_keywords = entry.get("ats_keywords", []) + entry.get("hard_skills", [])
        overlap = _keyword_overlap(target_keywords, cached_keywords)

        same_seniority = entry.get("seniority_level", "").lower() == keywords.seniority_level.lower()
        effective_overlap = overlap + (0.1 if same_seniority else 0)

        if effective_overlap > best_overlap and overlap >= KEYWORD_MATCH_THRESHOLD:
            best_overlap = effective_overlap
            best_match = entry

    if best_match:
        text_path = best_match.get("text_path")
        if text_path and os.path.exists(text_path):
            with open(text_path, "r") as f:
                return f.read(), best_match
    return None, None


def adapt_cover_letter(original_text: str, new_company: str, new_title: str, old_company: str = "", old_title: str = "") -> str:
    """Adapt a cached cover letter by swapping company name and role title."""
    text = original_text

    # Replace old company name with new one
    if old_company and new_company and old_company != new_company:
        text = text.replace(old_company, new_company)

    # Replace old job title with new one
    if old_title and new_title and old_title != new_title:
        text = text.replace(old_title, new_title)

    return text


def save_cover_letter_to_cache(
    keywords: ExtractedKeywords,
    cover_letter_text: str,
    docx_path: str,
    job_title: str = "",
    company: str = "",
):
    """Save a generated cover letter to the cache index."""
    _ensure_cache_dir()

    # Save the cover letter text
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    text_path = os.path.join(CACHE_DIR, f"cl_{timestamp}.txt")
    with open(text_path, "w") as f:
        f.write(cover_letter_text)

    # Add to index
    index = _load_index(CL_INDEX)
    index.append({
        "timestamp": datetime.now().isoformat(),
        "job_title": job_title,
        "company": company,
        "seniority_level": keywords.seniority_level,
        "ats_keywords": keywords.ats_keywords,
        "hard_skills": keywords.hard_skills,
        "text_path": text_path,
        "docx_path": docx_path,
    })
    _save_index(CL_INDEX, index)
