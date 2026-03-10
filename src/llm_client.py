"""Unified LLM client supporting both Groq and Anthropic."""

import json
import os

import requests

from .profile_loader import load_settings


def get_llm_response(prompt: str, max_tokens: int = 4096) -> str:
    """Get a response from the configured LLM provider (Groq or Anthropic)."""
    settings = load_settings()
    provider = settings.get("llm", {}).get("provider", "groq")

    if provider == "groq":
        return _groq_response(prompt, max_tokens, settings)
    else:
        return _anthropic_response(prompt, max_tokens, settings)


def _groq_response(prompt: str, max_tokens: int, settings: dict) -> str:
    """Call Groq API (OpenAI-compatible)."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set in environment / .env file")

    model = settings.get("llm", {}).get("groq_model", "llama-3.3-70b-versatile")

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.7,
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def _anthropic_response(prompt: str, max_tokens: int, settings: dict) -> str:
    """Call Anthropic Claude API."""
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set in environment / .env file")

    model = settings.get("llm", {}).get("anthropic_model", "claude-sonnet-4-20250514")
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def parse_json_response(text: str) -> dict:
    """Extract and parse JSON from an LLM response that may contain markdown."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    return json.loads(text)
