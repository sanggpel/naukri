"""Unified application generator — produces resume, cover letter, fit summary, gap analysis, and ATS score in one LLM call."""

import logging

from ..llm_client import get_llm_response, parse_json_response
from ..models import ExtractedKeywords, GeneratedResume, ResumeSection, UserProfile

logger = logging.getLogger(__name__)


def generate_application(
    profile: UserProfile,
    job_description: str,
) -> dict:
    """Generate all application materials in a single LLM call.

    Returns a dict with keys:
        - keywords: ExtractedKeywords
        - resume: GeneratedResume
        - cover_letter: str
        - fit_summary: list[str]  (5-7 bullet points)
        - gap_analysis: list[str]  (gaps and improvement suggestions)
        - ats_breakdown: dict  (skills_match, experience_alignment, keyword_coverage, role_relevance)
    """
    experience_text = ""
    for exp in profile.experience:
        experience_text += f"\n{exp.title} at {exp.company} ({exp.start} - {exp.end})"
        if exp.location:
            experience_text += f" — {exp.location}"
        experience_text += "\n"
        for bullet in exp.bullets:
            experience_text += f"  - {bullet}\n"

    skills_text = ""
    for category, skills in profile.skills.items():
        skills_text += f"{category}: {', '.join(skills)}\n"

    linkedin_short = profile.linkedin_url.replace("https://", "").replace("http://", "").rstrip("/")
    contact_line = f"{profile.location} | {profile.phone} | {profile.email} | {linkedin_short}"

    prompt = f"""You are an expert recruiter, hiring manager, and resume writer.

Your task is to analyze a job description and candidate profile, then generate tailored application materials.

The goal is to produce materials that are:
- tailored to the job description
- honest and evidence-based
- written in a clear, natural tone
- optimized for ATS systems without sounding robotic

IMPORTANT RULES:
- Do NOT invent experience, skills, metrics, titles, tools, or achievements.
- Only use information explicitly provided in the candidate profile.
- If a skill is not present in the candidate information, do not add it.
- Avoid buzzwords, fluff, and exaggerated claims.
- Avoid: "results-driven", "passionate", "thrilled", "esteemed company", "dynamic",
  "leveraged", "spearheaded", "cutting-edge", "synergy", "orchestrate", "utilize".
- Prefer: "built", "led", "designed", "shipped", "reduced", "grew", "managed", "launched".

CANDIDATE PROFILE:
Name: {profile.name}
Location: {profile.location}
Contact: {profile.phone} | {profile.email} | {profile.linkedin_url}
Citizenship: {profile.citizenship}

Summary: {profile.summary}

Skills:
{skills_text}

Experience:
{experience_text}

Education:
{chr(10).join(f"- {e.degree}, {e.field}, {e.institution} ({e.years})" for e in profile.education)}

Certifications:
{chr(10).join(f"- {c}" for c in profile.certifications)}

Project Highlights:
{chr(10).join(f"- {p}" for p in profile.project_highlights)}

JOB DESCRIPTION:
{job_description[:4000]}

PROCESS — follow these steps in order:

STEP 1 — JOB ANALYSIS:
Extract key responsibilities, required/preferred qualifications, important skills/tools,
industry keywords, and core problems the role solves.

STEP 2 — CANDIDATE MATCH:
Compare candidate to job requirements. Identify strong matches, transferable skills,
gaps, and what to emphasize.

STEP 3 — ATS SCORE:
Score across 4 dimensions:
- Skills match (0-30): how many required skills the candidate has
- Experience alignment (0-25): how well their experience maps to the role
- Keyword coverage (0-25): how many JD keywords appear in the candidate's profile
- Role relevance (0-20): overall fit for the role level and domain
List missing and underrepresented keywords.

STEP 4 — RESUME:
- Professional summary: 3-5 lines, plain language, lead with strongest fact
- Technology stack: flat list of actual technologies from candidate's profile matching the role
- Core skills: 3-4 categories, 4-5 skills each, plain terms
- Experience: ALL roles from profile. Recent: 4-5 bullets. Older: 2-3 bullets.
  Each bullet = specific action + specific outcome with numbers.
- Education, certifications, project highlights

STEP 5 — COVER LETTER:
- 250-350 words, 4 short paragraphs
- Opening: interest in this specific role/company (reference something from the JD)
- Middle: most relevant experience, connected to role needs
- Closing: interest in discussing the opportunity
- Do NOT repeat the resume. Do NOT say "I am passionate about" or repeat achievements.
- Sign off: Sincerely, {profile.name}, {contact_line}

STEP 6 — FIT SUMMARY:
5-7 bullets, each connecting: candidate experience → job requirement.

STEP 7 — GAP ANALYSIS:
Missing skills, keywords to emphasize, honest improvement suggestions.

Return a single JSON object:

{{
  "job_analysis": {{
    "job_title": "exact title",
    "company_name": "company name",
    "seniority_level": "senior|lead|manager|director|vp",
    "hard_skills": ["skill1", "skill2"],
    "soft_skills": ["skill1", "skill2"],
    "required_experience": ["req1", "req2"],
    "nice_to_haves": ["item1", "item2"],
    "ats_keywords": ["kw1", "kw2"]
  }},

  "ats_score": {{
    "overall": 85,
    "skills_match": 25,
    "experience_alignment": 22,
    "keyword_coverage": 20,
    "role_relevance": 18,
    "missing_keywords": ["keyword not in profile"],
    "underrepresented_keywords": ["keyword present but should be more prominent"]
  }},

  "resume": {{
    "executive_summary": "3-4 sentences. Plain language. Lead with strongest fact.",
    "technology_stack": "Python, Django, PostgreSQL, AWS, Docker, LLM APIs, RAG",
    "core_competencies": {{
      "Category": ["skill1", "skill2", "skill3", "skill4"]
    }},
    "experience": [
      {{
        "title": "Job Title",
        "company": "Company Name",
        "period": "Start - End",
        "location": "Location",
        "bullets": ["Specific action + outcome with numbers"]
      }}
    ],
    "education": ["Degree, Field — Institution (Years)"],
    "certifications": ["Cert 1"],
    "project_highlights": ["Highlight 1"]
  }},

  "cover_letter": "Full cover letter text here. 4 paragraphs, ~300 words.",

  "fit_summary": [
    "Candidate experience → job requirement connection"
  ],

  "gap_analysis": [
    "Missing skill or improvement suggestion"
  ],

  "matched_keywords": ["keyword1", "keyword2"]
}}

Return ONLY valid JSON. No markdown, no code fences, no commentary."""

    text = get_llm_response(prompt, max_tokens=8000)
    data = parse_json_response(text)

    # Parse job analysis into ExtractedKeywords
    ja = data.get("job_analysis", {})
    list_fields = ["hard_skills", "soft_skills", "required_experience", "nice_to_haves", "ats_keywords"]
    for field in list_fields:
        if field in ja and isinstance(ja[field], str):
            ja[field] = [s.strip() for s in ja[field].split(",") if s.strip()]

    keywords = ExtractedKeywords(**ja)

    # Parse ATS score
    ats_data = data.get("ats_score", {})
    if isinstance(ats_data, (int, float)):
        # LLM returned just a number instead of breakdown
        ats_data = {"overall": int(ats_data)}
    overall_score = ats_data.get("overall", data.get("ats_score_estimate", 0))

    # Parse resume
    resume_data = data.get("resume", {})
    sections = ResumeSection(**resume_data)
    resume = GeneratedResume(
        sections=sections,
        matched_keywords=data.get("matched_keywords", []),
        ats_score_estimate=overall_score,
    )

    # Cover letter
    cover_letter = data.get("cover_letter", "")

    # Fit summary and gap analysis
    fit_summary = data.get("fit_summary", [])
    if isinstance(fit_summary, str):
        fit_summary = [s.strip() for s in fit_summary.split("\n") if s.strip()]

    gap_analysis = data.get("gap_analysis", [])
    if isinstance(gap_analysis, str):
        gap_analysis = [s.strip() for s in gap_analysis.split("\n") if s.strip()]

    return {
        "keywords": keywords,
        "resume": resume,
        "cover_letter": cover_letter,
        "fit_summary": fit_summary,
        "gap_analysis": gap_analysis,
        "ats_breakdown": ats_data,
    }
