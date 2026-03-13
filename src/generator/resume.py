"""Generate ATS-optimized resumes tailored to specific job descriptions using LLM."""

from ..llm_client import get_llm_response, parse_json_response
from ..models import ExtractedKeywords, GeneratedResume, ResumeSection, UserProfile


def generate_resume(
    profile: UserProfile,
    job_description: str,
    keywords: ExtractedKeywords,
) -> GeneratedResume:
    """Generate a tailored, ATS-optimized resume."""
    experience_text = ""
    for exp in profile.experience:
        experience_text += f"\n{exp.title} at {exp.company} ({exp.start} - {exp.end})\n"
        for bullet in exp.bullets:
            experience_text += f"  - {bullet}\n"

    skills_text = ""
    for category, skills in profile.skills.items():
        skills_text += f"{category}: {', '.join(skills)}\n"

    prompt = f"""You are writing a resume for a real person applying to a real job. Your goal is a resume
that sounds like a confident human wrote it — not a template, not a marketing brochure.

CANDIDATE PROFILE:
Name: {profile.name}
Location: {profile.location}
Contact: {profile.phone} | {profile.email} | {profile.linkedin_url}
Citizenship: {profile.citizenship}

Current Summary: {profile.summary}

Skills:
{skills_text}

Experience:
{experience_text}

Education:
{chr(10).join(f"- {e.degree}, {e.institution} ({e.years})" for e in profile.education)}

Certifications:
{chr(10).join(f"- {c}" for c in profile.certifications)}

Project Highlights:
{chr(10).join(f"- {p}" for p in profile.project_highlights)}

TARGET JOB DESCRIPTION:
{job_description[:4000]}

ATS KEYWORDS TO INCORPORATE (use naturally, not forced):
Hard Skills: {', '.join(keywords.hard_skills)}
Soft Skills: {', '.join(keywords.soft_skills)}
Required Experience: {', '.join(keywords.required_experience)}
Critical ATS Keywords: {', '.join(keywords.ats_keywords)}

RESUME WRITING RULES:

EXECUTIVE SUMMARY (3-4 sentences):
- Write in plain, direct language. No "Results-driven" or "Dynamic leader" or "Passionate about".
- Lead with the strongest fact: years of experience, what they actually built, team sizes they led.
- Second sentence: their most relevant recent work (e.g., "Recently built an AI SaaS platform...").
- Third sentence: what makes them specifically suited for THIS role, not any role.
- Sound like a person describing themselves to a peer, not a marketing pitch.

TECHNOLOGY STACK (new section — add right after summary):
- List actual technologies in a flat format: "Python, Django, PostgreSQL, AWS, Docker, LLM APIs, RAG"
- Only include technologies the candidate actually has from their profile.
- Use the exact tech names from the job description where the candidate genuinely has the skill.

CORE COMPETENCIES:
- 3-4 categories max with 4-5 skills each.
- Use plain terms. "Team leadership" not "Transformative people leadership".
- Drop any buzzword that could apply to literally anyone.

EXPERIENCE:
- Each bullet must contain a SPECIFIC action and a SPECIFIC outcome or scope.
- BAD: "Improved engineering standards through refactoring initiatives"
- GOOD: "Rewrote the billing pipeline from monolith to microservices, reducing deploy time from 2 hours to 15 minutes"
- Include numbers: team sizes, revenue impact, percentage improvements, system scale.
- If the original bullet has no metric, reframe it with scope (e.g., "for a platform serving 500K users").
- Recent/relevant roles: 4-5 strong bullets. Older roles: 2-3 bullets.
- KEEP ALL ROLES from the profile. Do NOT skip any.

GENERAL:
- DO NOT fabricate experience, metrics, or skills not in the profile.
- DO NOT use these words/phrases: "results-driven", "leveraged", "spearheaded", "cutting-edge",
  "passionate", "dynamic", "synergy", "paradigm", "utilize", "strategize", "orchestrate".
- Prefer: "built", "led", "designed", "shipped", "reduced", "grew", "managed", "launched".
- The resume should fill 2 full pages for a senior candidate.

Return a JSON object with this exact structure:
{{
  "sections": {{
    "executive_summary": "The tailored summary text",
    "technology_stack": "Python, Django, PostgreSQL, AWS, ...",
    "core_competencies": {{
      "Category Name": ["skill1", "skill2"],
      "Another Category": ["skill3", "skill4"]
    }},
    "experience": [
      {{
        "title": "Job Title",
        "company": "Company Name",
        "period": "Start - End",
        "location": "Location",
        "bullets": ["Achievement 1", "Achievement 2"]
      }}
    ],
    "education": ["Degree — Institution"],
    "certifications": ["Cert 1", "Cert 2"],
    "project_highlights": ["Highlight 1", "Highlight 2"]
  }},
  "matched_keywords": ["keyword1", "keyword2"],
  "ats_score_estimate": 85
}}

Return ONLY valid JSON, no other text."""

    text = get_llm_response(prompt, max_tokens=8000)
    data = parse_json_response(text)
    sections = ResumeSection(**data["sections"])

    return GeneratedResume(
        sections=sections,
        matched_keywords=data.get("matched_keywords", []),
        ats_score_estimate=data.get("ats_score_estimate", 0),
    )
