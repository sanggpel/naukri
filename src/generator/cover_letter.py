"""Generate tailored cover letters using LLM."""

from ..llm_client import get_llm_response
from ..models import ExtractedKeywords, UserProfile


def generate_cover_letter(
    profile: UserProfile,
    job_description: str,
    keywords: ExtractedKeywords,
) -> str:
    """Generate a tailored cover letter."""
    recent_roles = profile.experience[:4]
    experience_summary = ""
    for exp in recent_roles:
        experience_summary += f"\n{exp.title} at {exp.company} ({exp.start} - {exp.end})\n"
        for bullet in exp.bullets[:3]:
            experience_summary += f"  - {bullet}\n"

    linkedin_short = profile.linkedin_url.replace("https://", "").replace("http://", "").rstrip("/")
    contact_line = f"{profile.location} {profile.phone} {profile.email} {linkedin_short}"

    prompt = f"""You are writing a cover letter for {profile.name}.
Write in first person as {profile.name}. Be professional, warm, and specific.

CANDIDATE INFO:
Name: {profile.name}
Location: {profile.location}
Contact: {profile.phone} | {profile.email} | {profile.linkedin_url}

Summary: {profile.summary}

Key Experience:
{experience_summary}

Skills: {', '.join(profile.all_skills_flat()[:20])}

TARGET JOB:
Title: {keywords.job_title}
Company: {keywords.company_name}

JOB DESCRIPTION:
{job_description[:3000]}

KEY ATS KEYWORDS: {', '.join(keywords.ats_keywords[:15])}

INSTRUCTIONS:
1. Start with "Dear Hiring Team,"
2. Opening paragraph: Express excitement about the specific role and company. Mention what attracted you.
3. Body paragraphs (2-3): Connect your experience to the role requirements. Reference specific achievements. Naturally incorporate ATS keywords.
4. Closing paragraph: Express enthusiasm and invite discussion.
5. End with:
   Sincerely,
   {profile.name}
   {contact_line}

TONE: Professional but warm, confident not arrogant, specific not generic.
LENGTH: 4-5 paragraphs, roughly one page.
DO NOT use bullet points — write in flowing paragraphs.
Return ONLY the cover letter text, no other commentary."""

    return get_llm_response(prompt, max_tokens=2048)
