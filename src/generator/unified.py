"""Unified application generator — produces resume, cover letter, fit summary, gap analysis, and ATS score.

Split into three focused LLM calls to ensure complete, high-quality output:
  Call 1: Job analysis + ATS score + Resume structure (summary, competencies, education, certs)
  Call 2: Resume experience section (all roles with tailored bullets)
  Call 3: Cover letter + Fit summary + Gap analysis
"""

import logging

from ..llm_client import get_llm_response, parse_json_response
from ..models import ExtractedKeywords, GeneratedResume, ResumeSection, UserProfile

logger = logging.getLogger(__name__)


def _build_profile_text(profile: UserProfile) -> tuple[str, str, str]:
    """Build text representations of profile sections."""
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

    return experience_text, skills_text, contact_line


def _call_1_analysis_and_resume_structure(
    profile: UserProfile, job_description: str, experience_text: str, skills_text: str
) -> dict:
    """Call 1: Job analysis, ATS score, and resume structure (everything except experience bullets)."""

    prompt = f"""You are an expert resume writer and ATS optimization specialist.

Analyze this job description against the candidate's profile. Then build the resume structure.

CANDIDATE PROFILE:
Name: {profile.name}
Summary: {profile.summary}

Skills:
{skills_text}

Experience titles: {', '.join(f'{e.title} at {e.company} ({e.start}-{e.end})' for e in profile.experience)}

Education:
{chr(10).join(f"- {e.degree}, {e.field}, {e.institution} ({e.years})" for e in profile.education)}

Certifications: {', '.join(profile.certifications) if profile.certifications else 'None'}

Project Highlights:
{chr(10).join(f"- {p}" for p in profile.project_highlights) if profile.project_highlights else 'None'}

JOB DESCRIPTION:
{job_description[:4000]}

Return this JSON:

{{
  "job_analysis": {{
    "job_title": "exact title from JD",
    "company_name": "company name from JD",
    "seniority_level": "senior|lead|manager|director|vp",
    "hard_skills": ["skill1", "skill2"],
    "soft_skills": ["skill1", "skill2"],
    "required_experience": ["req1", "req2"],
    "nice_to_haves": ["nice1", "nice2"],
    "ats_keywords": ["keyword1", "keyword2", "keyword3"]
  }},
  "ats_score": {{
    "overall": 85,
    "skills_match": 25,
    "experience_alignment": 22,
    "keyword_coverage": 20,
    "role_relevance": 18,
    "missing_keywords": ["keyword not found in profile"],
    "underrepresented_keywords": ["keyword that should be more prominent"]
  }},
  "executive_summary": "Write a 3-4 sentence professional summary tailored to this specific role. Lead with the strongest relevant fact (years of experience in the most relevant domain). Mention specific technologies/skills from the JD that the candidate has. No buzzwords. Plain, confident language.",
  "technology_stack": "Comma-separated list of technologies from the candidate's profile that appear in or are relevant to the JD. Only include what the candidate actually knows.",
  "core_competencies": {{
    "Category 1": ["skill1", "skill2", "skill3", "skill4", "skill5"],
    "Category 2": ["skill6", "skill7", "skill8", "skill9"],
    "Category 3": ["skill10", "skill11", "skill12", "skill13"],
    "Category 4": ["skill14", "skill15", "skill16", "skill17"]
  }},
  "education": [
    "Master of Computer Application, Computer Science — University of Pune (1994-1997)",
    "B.A. (Hons) Mathematics — University of Delhi (1990-1993)",
    "Certificate in E-Learning — University of Calgary (2016-2017)"
  ],
  "certifications": ["AWS Cloud Practitioner", "ITIL Foundation Certified"],
  "project_highlights": [
    "Specific project highlight relevant to this JD"
  ],
  "matched_keywords": ["keyword1", "keyword2"]
}}

RULES:
- core_competencies: 3-5 categories, 4-6 skills each. Prioritize JD keywords where candidate has the skill. Use the skill names from the JD (e.g., if JD says "machine learning" don't write "ML").
- education: Include ALL education entries. Format: "Degree, Field — Institution (Years)"
- certifications: Include ALL certifications. List the most JD-relevant ones first.
- project_highlights: Pick the 3-5 most relevant to this JD. Reword to emphasize JD-relevant aspects.
- Do NOT invent skills or certifications the candidate doesn't have.
- Return ONLY valid JSON."""

    text = get_llm_response(prompt, max_tokens=4000)
    return parse_json_response(text)


def _call_2_experience(
    profile: UserProfile, job_description: str, experience_text: str, ats_keywords: list[str]
) -> list[dict]:
    """Call 2: Generate tailored experience bullets for ALL roles."""

    num_exp = len(profile.experience)
    roles_list = "\n".join(
        f"  {i+1}. {e.title} at {e.company} ({e.start} - {e.end}) — {e.location}"
        for i, e in enumerate(profile.experience)
    )

    prompt = f"""You are an expert resume writer. Generate tailored experience bullets for a candidate applying to a specific role.

TARGET ROLE KEYWORDS: {', '.join(ats_keywords[:20])}

JOB DESCRIPTION (key requirements):
{job_description[:2500]}

CANDIDATE HAS {num_exp} ROLES. You must return bullets for ALL {num_exp} roles:
{roles_list}

FULL EXPERIENCE DETAILS:
{experience_text}

RULES:
- Return an array of exactly {num_exp} objects, one per role, in the same order as listed above.
- Recent/relevant roles (last 2-3 roles): 4-6 bullets each.
- Mid-career roles: 3-4 bullets each.
- Older roles (10+ years ago): 2-3 bullets each.
- Each bullet: strong action verb + specific what you did + measurable outcome or scope.
- Rewrite bullets to emphasize aspects that match the target JD, but ONLY use facts from the candidate's actual experience.
- Do NOT invent metrics, tools, titles, or achievements.
- Use action verbs: built, led, designed, shipped, reduced, grew, managed, launched, delivered, migrated, automated, architected, scaled, mentored, drove, owned, improved.
- NEVER use: results-driven, passionate, leveraged, spearheaded, cutting-edge, synergy, orchestrate, utilize.
- If a bullet has a number/metric in the original, always keep it.

Return JSON:

{{
  "experience": [
    {{
      "title": "Job Title",
      "company": "Company Name",
      "period": "Start - End",
      "location": "Location",
      "bullets": [
        "Strong verb + specific action + measurable outcome"
      ]
    }}
  ]
}}

You MUST return exactly {num_exp} experience entries. Do NOT skip any role.
Return ONLY valid JSON."""

    text = get_llm_response(prompt, max_tokens=6000)
    data = parse_json_response(text)
    return data.get("experience", [])


def _call_3_cover_letter(
    profile: UserProfile, job_description: str, job_title: str, company_name: str,
    experience_text: str, contact_line: str
) -> dict:
    """Call 3: Cover letter + Fit summary + Gap analysis."""

    # Build a concise version of top experience for the cover letter
    top_experience = ""
    for exp in profile.experience[:5]:  # Focus on recent roles
        top_experience += f"\n{exp.title} at {exp.company} ({exp.start} - {exp.end})\n"
        for bullet in exp.bullets[:3]:  # Top 3 bullets per role
            top_experience += f"  - {bullet}\n"

    prompt = f"""You are writing a cover letter for a senior technology leader applying to a specific role.

CANDIDATE: {profile.name}
ROLE: {job_title} at {company_name}
CONTACT: {contact_line}
CITIZENSHIP: {profile.citizenship}

CANDIDATE SUMMARY: {profile.summary}

RECENT EXPERIENCE:
{top_experience}

JOB DESCRIPTION:
{job_description[:3000]}

Generate THREE things:

1. COVER LETTER (250-350 words, 4 paragraphs):

Paragraph 1 — The hook (2-3 sentences):
- Name the exact role and company.
- Reference ONE specific thing from the JD (a product, initiative, challenge, or technology) and connect it to something concrete you've done.
- Example good opening: "The Sr. Manager, AI Self-Serve role at Rogers caught my attention because of its focus on building intelligent self-service tools — something I've been doing hands-on for the past two years at AI Foundry, where I built AI-powered platforms that serve thousands of users."

Paragraph 2 — Your strongest proof (4-5 sentences):
- Pick 2-3 specific achievements from your experience that directly address the role's biggest requirements.
- Use numbers: team sizes, revenue impact, scale, timeline.
- Each sentence should connect YOUR achievement to THEIR need.
- Vary sentence structure. Do NOT start consecutive sentences with "I".

Paragraph 3 — What else you bring (3-4 sentences):
- Leadership style, technical depth, or domain expertise that adds value beyond the core requirements.
- Mention something specific — a methodology, a type of team you've built, a technical approach.

Paragraph 4 — Close (2 sentences):
- Brief, professional. Express interest in discussing further.
- No begging, no "I would be honored", no "I am confident".

Sign off exactly like this:
Sincerely,
{profile.name}
{contact_line}

STRICT RULES:
- Write like a senior professional talking to a peer, not like a job applicant begging for a chance.
- BANNED phrases (instant reject if you use these): "I am excited", "I am passionate", "I am thrilled", "I am confident", "I am eager", "I believe I am", "perfect fit", "esteemed company", "dynamic team", "fast-paced environment", "hit the ground running", "unique opportunity", "I would be honored", "aligns perfectly".
- Maximum 2 sentences starting with "I" per paragraph.
- Do NOT restate the resume. The cover letter tells a story the resume can't.
- Every claim must be backed by a specific example from the experience.

2. FIT SUMMARY (5-7 bullets):
Each bullet: "[Specific experience/achievement from profile] → directly addresses [specific JD requirement]"
Be concrete — name companies, technologies, team sizes, metrics.

3. GAP ANALYSIS (3-5 bullets):
Honest gaps between candidate and JD requirements. For each:
- What's missing
- How to address it (transferable skill, adjacent experience, or honest acknowledgment)

Return JSON:
{{
  "cover_letter": "Full text with \\n\\n between paragraphs and \\n for line breaks in sign-off.",
  "fit_summary": ["bullet 1", "bullet 2", "bullet 3", "bullet 4", "bullet 5"],
  "gap_analysis": ["gap 1", "gap 2", "gap 3"]
}}

Return ONLY valid JSON. No markdown."""

    text = get_llm_response(prompt, max_tokens=4000)
    return parse_json_response(text)


def _optimize_cached_resume(
    cached_resume: GeneratedResume, keywords: ExtractedKeywords,
    job_description: str, ats_keywords: list[str],
) -> tuple[GeneratedResume, dict]:
    """Lightweight LLM call to patch a cached resume — only fix what's missing for the new JD.

    Instead of regenerating everything, this:
    - Updates the executive summary to reference the new role/company
    - Adds missing keywords to core competencies
    - Tweaks the top 2-3 experience entries to emphasize JD-relevant aspects
    - Returns updated ATS score
    """
    import json as _json

    cached_data = cached_resume.model_dump()
    current_summary = cached_data["sections"]["executive_summary"]
    current_competencies = cached_data["sections"]["core_competencies"]
    current_experience_top3 = cached_data["sections"]["experience"][:3]

    prompt = f"""You have a previously generated resume that is a strong match for a new job.
Instead of rebuilding everything, only update what's needed to better match this specific JD.

CURRENT EXECUTIVE SUMMARY:
{current_summary}

CURRENT CORE COMPETENCIES:
{_json.dumps(current_competencies, indent=2)}

TOP 3 EXPERIENCE ENTRIES (only update these):
{_json.dumps(current_experience_top3, indent=2)}

NEW JOB DESCRIPTION:
{job_description[:3000]}

TARGET ATS KEYWORDS: {', '.join(ats_keywords[:20])}
MISSING KEYWORDS (not in current resume): {', '.join(k for k in ats_keywords if k.lower() not in _json.dumps(cached_data).lower())}

Return JSON with ONLY the changes needed:
{{
  "executive_summary": "Updated 3-4 sentence summary referencing the new role/company. Keep the substance, change the framing.",
  "core_competencies": {{
    "Category": ["skill1", "skill2", "skill3", "skill4"]
  }},
  "experience_updates": [
    {{
      "index": 0,
      "bullets": ["updated bullet 1", "updated bullet 2"]
    }}
  ],
  "ats_score": {{
    "overall": 87,
    "skills_match": 26,
    "experience_alignment": 23,
    "keyword_coverage": 20,
    "role_relevance": 18,
    "missing_keywords": ["still missing"],
    "underrepresented_keywords": ["needs emphasis"]
  }},
  "matched_keywords": ["keyword1", "keyword2"]
}}

RULES:
- Only update experience_updates for roles where bullets need JD-relevant tweaks (max 3 roles).
- For experience_updates, include ALL bullets for that role (not just changed ones) since they replace the existing bullets.
- core_competencies should be the FULL updated set (3-5 categories, merge missing keywords into appropriate categories).
- Do NOT invent skills or achievements not in the original resume.
- Return ONLY valid JSON."""

    text = get_llm_response(prompt, max_tokens=4000)
    updates = parse_json_response(text)

    # Apply updates to cached resume
    sections_data = cached_data["sections"]

    if updates.get("executive_summary"):
        sections_data["executive_summary"] = updates["executive_summary"]

    if updates.get("core_competencies"):
        sections_data["core_competencies"] = updates["core_competencies"]

    # Apply experience bullet updates
    for update in updates.get("experience_updates", []):
        idx = update.get("index", -1)
        bullets = update.get("bullets", [])
        if 0 <= idx < len(sections_data["experience"]) and bullets:
            sections_data["experience"][idx]["bullets"] = bullets

    ats_data = updates.get("ats_score", {"overall": cached_resume.ats_score_estimate})
    if isinstance(ats_data, (int, float)):
        ats_data = {"overall": int(ats_data)}

    sections = ResumeSection(**sections_data)
    resume = GeneratedResume(
        sections=sections,
        matched_keywords=updates.get("matched_keywords", cached_resume.matched_keywords),
        ats_score_estimate=ats_data.get("overall", cached_resume.ats_score_estimate),
    )

    return resume, ats_data


def generate_application(
    profile: UserProfile,
    job_description: str,
) -> dict:
    """Generate application materials. Uses cache when a strong match exists (saves 2 LLM calls).

    Flow:
    - Always: Call 1 — Job analysis + ATS score (needed for every job)
    - If cached resume matches (>=60% keyword overlap):
        - Call 2 — Lightweight optimize: patch summary, competencies, top bullets
    - If no cache match:
        - Call 2 — Full experience bullets for all roles
        - Call 3 — (after delay) Resume structure
    - Always: Final call — Cover letter + Fit + Gaps (always fresh per job)

    Returns a dict with keys:
        - keywords: ExtractedKeywords
        - resume: GeneratedResume
        - cover_letter: str
        - fit_summary: list[str]
        - gap_analysis: list[str]
        - ats_breakdown: dict
    """
    import time

    from .cache import find_cached_resume

    experience_text, skills_text, contact_line = _build_profile_text(profile)

    # ── Call 1: Job Analysis + ATS + Resume Structure (always needed) ──
    logger.info("Call 1: Analyzing job and building resume structure...")
    structure = _call_1_analysis_and_resume_structure(
        profile, job_description, experience_text, skills_text
    )

    # Parse job analysis
    ja = structure.get("job_analysis", {})
    list_fields = ["hard_skills", "soft_skills", "required_experience", "nice_to_haves", "ats_keywords"]
    for field in list_fields:
        if field in ja and isinstance(ja[field], str):
            ja[field] = [s.strip() for s in ja[field].split(",") if s.strip()]
    keywords = ExtractedKeywords(**ja)

    # Parse ATS score
    ats_data = structure.get("ats_score", {})
    if isinstance(ats_data, (int, float)):
        ats_data = {"overall": int(ats_data)}
    overall_score = ats_data.get("overall", 0)

    ats_keywords = ja.get("ats_keywords", []) + ja.get("hard_skills", [])

    time.sleep(3)  # Avoid Groq rate limits

    # ── Check cache for a reusable resume ──
    cached_resume, cached_path, cached_entry = find_cached_resume(keywords)

    if cached_resume and len(cached_resume.sections.experience) >= len(profile.experience) - 1:
        # Strong match found — optimize instead of rebuilding
        logger.info("Cache hit! Optimizing existing resume instead of full rebuild (saves 1-2 LLM calls)...")
        resume, ats_data = _optimize_cached_resume(
            cached_resume, keywords, job_description, ats_keywords,
        )
        overall_score = ats_data.get("overall", overall_score)
    else:
        # No cache match — full generation (Call 2 + build from Call 1 structure)
        logger.info("No cache match. Full generation: experience bullets for all %d roles...", len(profile.experience))
        experience_entries = _call_2_experience(
            profile, job_description, experience_text, ats_keywords
        )

        # Validate: fill missing entries from profile
        if len(experience_entries) < len(profile.experience):
            logger.warning(
                "LLM returned %d experience entries, expected %d. Filling from profile.",
                len(experience_entries), len(profile.experience),
            )
            for i in range(len(experience_entries), len(profile.experience)):
                exp = profile.experience[i]
                experience_entries.append({
                    "title": exp.title,
                    "company": exp.company,
                    "period": f"{exp.start} - {exp.end}",
                    "location": exp.location,
                    "bullets": exp.bullets,
                })

        sections = ResumeSection(
            executive_summary=structure.get("executive_summary", ""),
            technology_stack=structure.get("technology_stack", ""),
            core_competencies=structure.get("core_competencies", {}),
            experience=experience_entries,
            education=structure.get("education", []),
            certifications=structure.get("certifications", []),
            project_highlights=structure.get("project_highlights", []),
        )
        resume = GeneratedResume(
            sections=sections,
            matched_keywords=structure.get("matched_keywords", []),
            ats_score_estimate=overall_score,
        )

    # ── Cover Letter + Fit + Gaps (always fresh per job) ──
    job_title = ja.get("job_title", "the role")
    company_name = ja.get("company_name", "the company")

    time.sleep(3)  # Avoid Groq rate limits

    logger.info("Generating cover letter and analysis...")
    cl_data = _call_3_cover_letter(
        profile, job_description, job_title, company_name,
        experience_text, contact_line,
    )

    cover_letter = cl_data.get("cover_letter", "")

    fit_summary = cl_data.get("fit_summary", [])
    if isinstance(fit_summary, str):
        fit_summary = [s.strip() for s in fit_summary.split("\n") if s.strip()]

    gap_analysis = cl_data.get("gap_analysis", [])
    if isinstance(gap_analysis, str):
        gap_analysis = [s.strip() for s in gap_analysis.split("\n") if s.strip()]

    logger.info("Done. Resume: %d experience entries, CL: %d chars, Cache: %s",
                len(resume.sections.experience), len(cover_letter),
                "optimized" if cached_resume else "full build")

    return {
        "keywords": keywords,
        "resume": resume,
        "cover_letter": cover_letter,
        "fit_summary": fit_summary,
        "gap_analysis": gap_analysis,
        "ats_breakdown": ats_data,
    }
