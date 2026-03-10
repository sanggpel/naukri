"""Extract ATS-relevant keywords from job descriptions using LLM."""

from ..llm_client import get_llm_response, parse_json_response
from ..models import ExtractedKeywords


def extract_keywords(jd_text: str) -> ExtractedKeywords:
    """Extract structured keywords from a job description using the configured LLM."""
    prompt = f"""Analyze this job description and extract structured keywords for ATS resume optimization.

JOB DESCRIPTION:
{jd_text}

Return a JSON object with exactly these fields:
- "hard_skills": Technical skills, tools, technologies, programming languages mentioned
- "soft_skills": Leadership, communication, teamwork, and other soft skills mentioned
- "required_experience": Specific experience requirements (e.g., "5+ years in software development")
- "nice_to_haves": Skills or experience listed as preferred/nice-to-have
- "ats_keywords": The most important keywords that an ATS system would scan for (combine the most critical from all categories)
- "job_title": The exact job title
- "company_name": The company name
- "seniority_level": One of "entry", "mid", "senior", "lead", "manager", "director", "vp", "c-level"

Return ONLY valid JSON, no other text."""

    text = get_llm_response(prompt, max_tokens=2048)
    data = parse_json_response(text)

    # LLMs sometimes return strings instead of lists — normalize
    list_fields = ["hard_skills", "soft_skills", "required_experience", "nice_to_haves", "ats_keywords"]
    for field in list_fields:
        if field in data and isinstance(data[field], str):
            data[field] = [s.strip() for s in data[field].split(",") if s.strip()]

    return ExtractedKeywords(**data)
