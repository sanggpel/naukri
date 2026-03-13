"""Update profile.yaml with additional context provided by the user to fill gaps."""

import logging
import os

import yaml

from .llm_client import get_llm_response, parse_json_response

logger = logging.getLogger(__name__)

PROFILE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "profile.yaml"))


def update_profile_from_context(additional_context: str, gaps: list[str] | None = None) -> None:
    """Parse additional context and merge into profile.yaml.

    Uses LLM to extract structured updates (skills, experience bullets,
    certifications, project highlights) from free-text input, then merges
    them into the existing profile without duplicating.
    """
    # Load current profile
    with open(PROFILE_PATH, "r") as f:
        profile_data = yaml.safe_load(f)

    # Build current profile summary for context
    current_skills = []
    for category, skills in profile_data.get("skills", {}).items():
        current_skills.extend(skills)

    current_certs = profile_data.get("certifications", [])
    current_highlights = profile_data.get("project_highlights", [])

    gaps_text = "\n".join(f"- {g}" for g in gaps) if gaps else "None provided"

    prompt = f"""You are a profile update assistant. The user has provided additional context about their experience to address gaps identified in a job application.

CURRENT PROFILE SKILLS: {', '.join(current_skills[:50])}
CURRENT CERTIFICATIONS: {', '.join(current_certs)}
CURRENT PROJECT HIGHLIGHTS: {', '.join(current_highlights[:5])}

GAPS IDENTIFIED:
{gaps_text}

USER'S ADDITIONAL CONTEXT:
{additional_context}

Extract structured updates from the user's context. Only include information the user actually mentioned — do NOT invent anything.

Return a JSON object with these fields (use empty lists/dicts if nothing to add):

{{
  "new_skills": {{
    "Category Name": ["skill1", "skill2"]
  }},
  "new_experience_bullets": [
    {{
      "company_match": "partial company name to match against existing experience entries",
      "bullets": ["new bullet point to add"]
    }}
  ],
  "new_certifications": ["cert1"],
  "new_project_highlights": ["highlight1"],
  "summary_addition": "A sentence or two to append to the professional summary, or empty string if nothing to add"
}}

Rules:
- For new_skills: group into existing or new categories. Use the same category names as the current profile when possible.
- For new_experience_bullets: match to existing jobs by company name (partial match is fine). Only add bullets that represent NEW information.
- Do NOT repeat skills/certs/highlights that already exist in the profile.
- Keep bullets specific and quantified where the user provided numbers.
- Return ONLY valid JSON."""

    try:
        text = get_llm_response(prompt, max_tokens=2000)
        updates = parse_json_response(text)
    except Exception as e:
        logger.error(f"Failed to parse profile updates: {e}")
        return

    changed = False

    # Merge new skills
    new_skills = updates.get("new_skills", {})
    if new_skills and isinstance(new_skills, dict):
        if "skills" not in profile_data:
            profile_data["skills"] = {}
        for category, skills in new_skills.items():
            if not isinstance(skills, list):
                continue
            if category not in profile_data["skills"]:
                profile_data["skills"][category] = []
            existing = set(s.lower() for s in profile_data["skills"][category])
            for skill in skills:
                if skill.lower() not in existing:
                    profile_data["skills"][category].append(skill)
                    changed = True
                    logger.info(f"Added skill: {skill} to {category}")

    # Merge new experience bullets into matching jobs
    new_bullets = updates.get("new_experience_bullets", [])
    if new_bullets and isinstance(new_bullets, list):
        for entry in new_bullets:
            if not isinstance(entry, dict):
                continue
            match_text = entry.get("company_match", "").lower()
            bullets = entry.get("bullets", [])
            if not match_text or not bullets:
                continue
            for exp in profile_data.get("experience", []):
                company = exp.get("company", "").lower()
                title = exp.get("title", "").lower()
                if match_text in company or match_text in title:
                    existing_bullets = set(b.lower()[:50] for b in exp.get("bullets", []))
                    for bullet in bullets:
                        if bullet.lower()[:50] not in existing_bullets:
                            exp.setdefault("bullets", []).append(bullet)
                            changed = True
                            logger.info(f"Added bullet to {exp.get('company')}: {bullet[:60]}...")
                    break

    # Merge new certifications
    new_certs = updates.get("new_certifications", [])
    if new_certs and isinstance(new_certs, list):
        if "certifications" not in profile_data:
            profile_data["certifications"] = []
        existing = set(c.lower() for c in profile_data["certifications"])
        for cert in new_certs:
            if cert.lower() not in existing:
                profile_data["certifications"].append(cert)
                changed = True
                logger.info(f"Added certification: {cert}")

    # Merge new project highlights
    new_highlights = updates.get("new_project_highlights", [])
    if new_highlights and isinstance(new_highlights, list):
        if "project_highlights" not in profile_data:
            profile_data["project_highlights"] = []
        existing = set(h.lower()[:50] for h in profile_data["project_highlights"])
        for highlight in new_highlights:
            if highlight.lower()[:50] not in existing:
                profile_data["project_highlights"].append(highlight)
                changed = True
                logger.info(f"Added project highlight: {highlight[:60]}...")

    # Append to summary if provided
    summary_addition = updates.get("summary_addition", "")
    if summary_addition and isinstance(summary_addition, str) and summary_addition.strip():
        current_summary = profile_data.get("summary", "")
        if summary_addition.lower() not in current_summary.lower():
            profile_data["summary"] = current_summary.rstrip() + " " + summary_addition.strip()
            changed = True
            logger.info(f"Updated summary with: {summary_addition[:60]}...")

    # Save updated profile
    if changed:
        with open(PROFILE_PATH, "w") as f:
            yaml.dump(profile_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False, width=120)
        logger.info("Profile updated successfully")
    else:
        logger.info("No new information to add to profile")
