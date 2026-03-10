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

    prompt = f"""You are an expert resume writer and ATS optimization specialist. Create a tailored resume
for the candidate below, optimized for the target job.

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

ATS KEYWORDS TO INCORPORATE:
Hard Skills: {', '.join(keywords.hard_skills)}
Soft Skills: {', '.join(keywords.soft_skills)}
Required Experience: {', '.join(keywords.required_experience)}
Critical ATS Keywords: {', '.join(keywords.ats_keywords)}

INSTRUCTIONS:
1. Write an EXECUTIVE SUMMARY (3-4 sentences) tailored to this specific role, naturally incorporating the most important ATS keywords.
2. Create CORE COMPETENCIES organized into categories that match what this job is looking for. Use the exact terminology from the job description where the candidate genuinely has the skill.
3. Rewrite EXPERIENCE bullets to emphasize achievements relevant to this role. Keep it truthful but reframe existing experience to align with the job requirements. Use action verbs and quantify results where possible.
4. Select the most relevant EDUCATION, CERTIFICATIONS, and PROJECT HIGHLIGHTS.
5. Estimate an ATS match score (0-100) based on keyword coverage.

Return a JSON object with this exact structure:
{{
  "sections": {{
    "executive_summary": "The tailored summary text",
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

IMPORTANT:
- Keep experience TRUTHFUL — rephrase and reframe, but do NOT fabricate
- Naturally weave ATS keywords into bullet points, not just list them
- Include ALL work experience entries from the profile. Do NOT skip any roles. Recent roles get 3-4 bullets, older roles get 2-3 bullets.
- The resume MUST fill 2 full pages. This is a senior leader with 20+ years of experience — a 1-page resume is unacceptable.
- Include 4-6 core competency categories with 4-6 skills each
- Include all education, certifications, and project highlights
- Return ONLY valid JSON, no other text."""

    text = get_llm_response(prompt, max_tokens=8000)
    data = parse_json_response(text)
    sections = ResumeSection(**data["sections"])

    return GeneratedResume(
        sections=sections,
        matched_keywords=data.get("matched_keywords", []),
        ats_score_estimate=data.get("ats_score_estimate", 0),
    )
