"""Build a structured profile.yaml from unstructured text (LinkedIn, resume PDF, plain text)."""

import logging
import os
import re

import yaml

from .llm_client import get_llm_response, parse_json_response

logger = logging.getLogger(__name__)

PROFILE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "profile.yaml"))


def build_profile_from_text(text: str) -> dict:
    """Use LLM to convert unstructured text into a structured profile dict.

    Returns the profile dict (ready to write as YAML).
    Raises ValueError if the LLM output can't be parsed.
    """
    prompt = f"""You are an expert resume parser. Convert the following text into a structured profile in JSON format.

INPUT TEXT:
{text[:6000]}

Return a JSON object with EXACTLY this structure. Fill every field you can find from the text. Use empty strings or empty lists for missing data — never omit a field.

{{
  "name": "Full Name",
  "email": "email@example.com",
  "phone": "+1-xxx-xxx-xxxx",
  "location": "City, State/Province, Country",
  "citizenship": "",
  "linkedin_url": "https://linkedin.com/in/...",
  "summary": "3-5 sentence professional summary written in first person. Focus on years of experience, key domains, leadership scope, and technical expertise.",
  "skills": {{
    "Category Name": ["skill1", "skill2", "skill3"],
    "Another Category": ["skill4", "skill5"]
  }},
  "experience": [
    {{
      "title": "Job Title",
      "company": "Company Name",
      "type": "Full-time",
      "start": "Mon YYYY",
      "end": "Present",
      "location": "City, Country",
      "bullets": [
        "Specific accomplishment with numbers where possible",
        "Another achievement"
      ]
    }}
  ],
  "education": [
    {{
      "institution": "University Name",
      "degree": "Bachelor's/Master's/etc",
      "field": "Field of Study",
      "years": "YYYY-YYYY"
    }}
  ],
  "certifications": ["Certification 1", "Certification 2"],
  "project_highlights": ["Notable project or achievement 1"],
  "languages": ["English", "Hindi"]
}}

Rules:
- Extract ALL work experience entries, maintaining chronological order (most recent first)
- For each experience, create 3-6 specific bullet points with quantified outcomes where the text provides numbers
- Group skills into meaningful categories (e.g., "Programming Languages", "Cloud & Infrastructure", "Leadership & Management", "AI & Machine Learning")
- If the text doesn't mention something (like phone or email), use an empty string — do NOT invent data
- The summary should be a polished professional summary, not a copy of raw text
- Return ONLY valid JSON, no markdown or commentary"""

    response = get_llm_response(prompt, max_tokens=6000)
    data = parse_json_response(response)

    # Validate required fields
    if not data.get("name"):
        raise ValueError("Could not extract a name from the provided text")

    # Ensure all expected fields exist
    defaults = {
        "name": "", "email": "", "phone": "", "location": "",
        "citizenship": "", "linkedin_url": "", "summary": "",
        "skills": {}, "experience": [], "education": [],
        "certifications": [], "project_highlights": [], "languages": [],
    }
    for key, default in defaults.items():
        if key not in data:
            data[key] = default

    # Ensure experience entries have all fields
    for exp in data.get("experience", []):
        for field in ["title", "company", "type", "start", "end", "location"]:
            if field not in exp:
                exp[field] = ""
        if "bullets" not in exp:
            exp["bullets"] = []

    # Ensure education entries have all fields
    for edu in data.get("education", []):
        for field in ["institution", "degree", "field", "years"]:
            if field not in edu:
                edu[field] = ""

    return data


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF file."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text() + "\n"
        doc.close()
        return text.strip()
    except ImportError:
        pass

    # Fallback: try pdfplumber
    try:
        import io
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            text = ""
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
        return text.strip()
    except ImportError:
        pass

    raise ImportError("No PDF reader available. Install PyMuPDF: pip install pymupdf")


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract text from a DOCX file."""
    import io
    from docx import Document
    doc = Document(io.BytesIO(file_bytes))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def fetch_linkedin_profile_text(url: str) -> str:
    """Fetch text content from a LinkedIn profile URL."""
    import requests
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    # Try direct fetch first (works for public profiles)
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        if len(text) > 500:
            return text[:8000]
    except Exception as e:
        logger.debug(f"Direct LinkedIn fetch failed: {e}")

    # Try Playwright for JS-rendered content
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)

            # Try expanding sections
            for selector in [
                "button:has-text('see more')",
                "button:has-text('Show all')",
                "[class*='see-more']",
            ]:
                try:
                    buttons = page.query_selector_all(selector)
                    for btn in buttons[:5]:
                        if btn.is_visible():
                            btn.click()
                            page.wait_for_timeout(500)
                except Exception:
                    pass

            text = page.evaluate("document.body.innerText")
            browser.close()

        if len(text) > 500:
            return text[:8000]
    except Exception as e:
        logger.debug(f"Playwright LinkedIn fetch failed: {e}")

    raise ValueError(
        "Could not fetch LinkedIn profile. The profile may be private or require login. "
        "Try copying your LinkedIn profile text manually and using the 'Paste Text' option instead."
    )


def save_profile(data: dict) -> None:
    """Write profile dict to profile.yaml, backing up the old one first."""
    # Backup existing profile
    if os.path.exists(PROFILE_PATH):
        backup_path = PROFILE_PATH + ".backup"
        import shutil
        shutil.copy2(PROFILE_PATH, backup_path)
        logger.info(f"Backed up existing profile to {backup_path}")

    with open(PROFILE_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False, width=120)
    logger.info("Profile saved successfully")
