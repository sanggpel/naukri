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

    prompt = f"""Write a cover letter for {profile.name} applying to {keywords.job_title} at {keywords.company_name}.
Write in first person. Sound like a real person writing to another real person — not a template.

CANDIDATE:
Name: {profile.name}
Location: {profile.location}
Contact: {profile.phone} | {profile.email} | {profile.linkedin_url}

Background: {profile.summary}

Recent Experience:
{experience_summary}

Relevant Skills: {', '.join(profile.all_skills_flat()[:20])}

JOB DESCRIPTION:
{job_description[:3000]}

COVER LETTER RULES:

OPENING (1 paragraph):
- Start with "Dear Hiring Team,"
- State what role you're applying for and why this specific company interests you.
- Reference something SPECIFIC about the company or role from the job description — not generic
  "I'm excited about your innovative company" but something like "The focus on AI-powered document
  processing resonates with my recent work building..."
- Keep it to 2-3 sentences. Do NOT say "I am writing to express my interest".

BODY (2 paragraphs — each covering a DIFFERENT angle):
- Paragraph 2: Your most relevant RECENT experience. Pick ONE concrete accomplishment from the
  last 2-3 years that directly connects to what this role needs. Use a specific number or outcome.
  Do NOT list your entire career history.
- Paragraph 3: A DIFFERENT strength — could be leadership style, a technical skill that matches,
  or domain knowledge. Do NOT repeat what paragraph 2 already covered.
  Each body paragraph should be 3-4 sentences max.

CLOSING (1 paragraph):
- 1-2 sentences. Say you'd welcome a conversation. Do NOT grovel or over-explain.

Sign off with:
Sincerely,
{profile.name}
{contact_line}

THINGS TO AVOID:
- "I am passionate about..." / "I am excited to..." / "I am thrilled..."
- "Throughout my career..." / "Over the past X years..." (the resume covers this)
- Repeating the same achievement in different words across paragraphs
- Listing skills like a resume — weave them into the story
- Generic praise about the company that could apply to any company
- Any sentence that could appear unchanged in a letter to a different company

THINGS TO DO:
- Each paragraph should add NEW information, not rephrase the previous one
- Reference the company name and role naturally (1-2 times, not in every sentence)
- Use specific details: team sizes, technologies, metrics, products
- Keep the total letter to ~300 words (4 short paragraphs + sign-off)

Return ONLY the cover letter text, no other commentary."""

    return get_llm_response(prompt, max_tokens=2048)
