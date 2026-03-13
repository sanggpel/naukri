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


_GROQ_FALLBACK_MODELS = [
    "meta-llama/llama-4-scout-17b-16e-instruct",  # 30K TPM, 500K TPD
    "qwen/qwen3-32b",                              # 6K TPM, 500K TPD
    "llama-3.1-8b-instant",                         # 6K TPM, 500K TPD
]


def _groq_response(prompt: str, max_tokens: int, settings: dict) -> str:
    """Call Groq API (OpenAI-compatible) with retry on rate limits and automatic model fallback."""
    import logging
    import time

    logger = logging.getLogger(__name__)

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set in environment / .env file")

    primary_model = settings.get("llm", {}).get("groq_model", "llama-3.3-70b-versatile")
    models_to_try = [primary_model] + [m for m in _GROQ_FALLBACK_MODELS if m != primary_model]

    for model_idx, model in enumerate(models_to_try):
        if model_idx > 0:
            logger.info("Falling back to model: %s", model)

        result = _groq_call_with_retry(prompt, max_tokens, api_key, model, logger)
        if result is not None:
            return result

        logger.warning("Model %s rate limited. Trying next fallback...", model)

    raise ValueError(
        "All Groq models rate limited. "
        "Options: wait for limits to reset, or switch to Anthropic in Settings (provider: anthropic)."
    )


def _groq_call_with_retry(prompt: str, max_tokens: int, api_key: str, model: str, logger) -> str | None:
    """Try a single Groq model with retries. Returns None if rate limited beyond recovery."""
    import time

    max_retries = 3
    for attempt in range(max_retries):
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

        # Log rate limit status from headers (always present)
        remaining_req = resp.headers.get("x-ratelimit-remaining-requests", "?")
        remaining_tok = resp.headers.get("x-ratelimit-remaining-tokens", "?")
        limit_req = resp.headers.get("x-ratelimit-limit-requests", "?")
        limit_tok = resp.headers.get("x-ratelimit-limit-tokens", "?")
        logger.info(
            "Groq [%s] — requests: %s/%s remaining, tokens: %s/%s remaining",
            model, remaining_req, limit_req, remaining_tok, limit_tok,
        )

        if resp.status_code == 429:
            # Parse retry-after or use exponential backoff
            retry_after = resp.headers.get("retry-after")
            reset_req = resp.headers.get("x-ratelimit-reset-requests", "")
            reset_tok = resp.headers.get("x-ratelimit-reset-tokens", "")

            if retry_after:
                wait = float(retry_after)
            else:
                wait = min(2 ** attempt * 5, 60)  # 5s, 10s, 20s, 60s

            # Determine which limit was hit
            limit_type = "tokens per minute"
            if remaining_req == "0":
                limit_type = f"daily requests (resets: {reset_req})"
            elif remaining_tok == "0":
                limit_type = f"tokens/min (resets: {reset_tok})"
            elif wait > 120:
                limit_type = "daily token quota"

            # If wait is too long (daily limit hit), return None to try next model
            if wait > 90:
                logger.warning(
                    "Model %s daily limit hit (%s). Wait would be %dm %ds — trying fallback instead.",
                    model, limit_type, int(wait // 60), int(wait % 60),
                )
                return None  # Signal to try next model

            logger.warning(
                "Groq rate limited: %s [%s] (attempt %d/%d). Waiting %.0fs...",
                limit_type, model, attempt + 1, max_retries, wait,
            )
            time.sleep(wait)
            continue

        resp.raise_for_status()
        data = resp.json()

        # Log token usage for this call
        usage = data.get("usage", {})
        if usage:
            logger.info(
                "Groq [%s] — prompt: %d, completion: %d, total: %d tokens",
                model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), usage.get("total_tokens", 0),
            )

        return data["choices"][0]["message"]["content"].strip()

    # All retries exhausted for this model
    return None


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
    """Extract and parse JSON from an LLM response that may contain markdown.

    Handles common LLM quirks: markdown fences, trailing commas, unescaped
    newlines inside string values, and truncated output.
    """
    import re

    text = text.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0].strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract the outermost JSON object
    start = text.find("{")
    if start != -1:
        # Find matching closing brace
        depth = 0
        end = -1
        in_string = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break

        if end != -1:
            candidate = text[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

            # Fix trailing commas before } or ]
            cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass

    # Last resort: if JSON was truncated (LLM hit token limit), try to repair
    # by closing open strings, arrays, and objects
    fragment = text[start:] if start != -1 else text
    # Remove trailing incomplete key-value pair
    fragment = re.sub(r",\s*\"[^\"]*\"?\s*:?\s*\"?[^\"]*$", "", fragment)
    # Close any open strings
    if fragment.count('"') % 2 == 1:
        fragment += '"'
    # Close open arrays and objects
    open_braces = fragment.count("{") - fragment.count("}")
    open_brackets = fragment.count("[") - fragment.count("]")
    fragment += "]" * max(0, open_brackets) + "}" * max(0, open_braces)
    # Fix trailing commas
    fragment = re.sub(r",\s*([}\]])", r"\1", fragment)
    try:
        return json.loads(fragment)
    except json.JSONDecodeError:
        raise ValueError(f"Could not parse JSON from LLM response. First 500 chars: {text[:500]}")
