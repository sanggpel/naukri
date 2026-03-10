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

    prompt = f"""You are writing a cover letter for Sangeeta Bahri, a senior software leader.
Write in first person as Sangeeta. Match the tone and style of this sample cover letter:

SAMPLE COVER LETTER STYLE:
"I'm excited to apply for this opportunity at [Company]. What particularly attracted me to the role
is the chance to operate at the intersection of engineering leadership, technical strategy, and
product execution — acting as a strong partner to executive leadership while helping engineering
teams translate ambitious ideas into scalable platforms.

Over the course of my career, I've often found myself operating in roles that function as a
technical advisor and execution partner to senior leadership. With more than 20 years in software
development and engineering leadership, I've helped organizations navigate complex technical
decisions, shape product direction, and ensure engineering teams are set up to deliver reliably
at scale."

CANDIDATE INFO:
Name: {profile.name}
Location: {profile.location}
Contact: {profile.phone} | {profile.email} | {profile.linkedin_url}

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
   Sangeeta Bahri
   Calgary, AB (403) 589-3616 sbahri@gmail.com linkedin.com/in/sangeetabahri

TONE: Professional but warm, confident not arrogant, specific not generic.
LENGTH: 4-5 paragraphs, roughly one page.
DO NOT use bullet points — write in flowing paragraphs.
Return ONLY the cover letter text, no other commentary."""

    return get_llm_response(prompt, max_tokens=2048)
