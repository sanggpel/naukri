"""LinkedIn network search to find referral connections using browser cookies."""

import json
import os
import time
from datetime import datetime, timedelta

import requests

from ..models import NetworkMatch
from ..profile_loader import load_settings


CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "network_cache.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/vnd.linkedin.normalized+json+2.1",
    "x-restli-protocol-version": "2.0.0",
}

GRAPHQL_ENDPOINT = "https://www.linkedin.com/voyager/api/graphql"
QUERY_ID = "voyagerSearchDashClusters.b0928897b71bd00a5a7291755dcd64f0"


def _load_cache() -> dict:
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r") as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def _load_cookies() -> dict:
    """Load LinkedIn cookies from the JSON cookie file exported from browser."""
    settings = load_settings()
    cookies_file = settings.get("linkedin", {}).get("cookies_file", "cookies.json")

    if not os.path.isabs(cookies_file):
        cookies_file = os.path.join(os.path.dirname(__file__), "..", "..", cookies_file)

    if not os.path.exists(cookies_file):
        raise FileNotFoundError(
            f"LinkedIn cookies file not found: {cookies_file}\n"
            "Export your LinkedIn cookies using a browser extension and save as JSON."
        )

    with open(cookies_file, "r") as f:
        cookie_list = json.load(f)

    cookies = {}
    for cookie in cookie_list:
        if cookie.get("domain", "").endswith("linkedin.com"):
            cookies[cookie["name"]] = cookie["value"]

    if "li_at" not in cookies and "JSESSIONID" not in cookies:
        raise ValueError(
            "LinkedIn cookies file doesn't contain authentication cookies (li_at or JSESSIONID). "
            "Make sure you're logged into LinkedIn when exporting cookies."
        )

    return cookies


def _get_csrf_token(cookies: dict) -> str:
    """Extract CSRF token from JSESSIONID cookie."""
    jsessionid = cookies.get("JSESSIONID", "")
    return jsessionid.strip('"')


def _build_session(cookies: dict) -> requests.Session:
    """Create an authenticated requests session."""
    csrf_token = _get_csrf_token(cookies)
    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update(HEADERS)
    if csrf_token:
        session.headers["csrf-token"] = csrf_token
    return session


def _search_people(session: requests.Session, company_name: str, network_depth: str, count: int = 20) -> list[dict]:
    """Search LinkedIn for people at a company, filtered by connection degree.

    network_depth: "F" = 1st degree, "S" = 2nd degree
    """
    # LinkedIn Voyager GraphQL uses REST-li style query params in the URL
    # Format: queryParameters:List((key:name,value:List(val)))
    url = (
        f"{GRAPHQL_ENDPOINT}?variables="
        f"(start:0,origin:FACETED_SEARCH,"
        f"query:(keywords:{company_name},"
        f"flagshipSearchIntent:SEARCH_SRP,"
        f"queryParameters:List("
        f"(key:network,value:List({network_depth})),"
        f"(key:resultType,value:List(PEOPLE))"
        f")))"
        f"&queryId={QUERY_ID}"
    )

    resp = session.get(url, timeout=15)
    if resp.status_code != 200:
        return []

    data = resp.json()
    return data.get("included", [])


def find_connections_at_company(
    company_name: str,
    rate_limit: float = 3.0,
    cache_ttl_hours: int = 24,
) -> list[NetworkMatch]:
    """Find 1st and 2nd degree connections at a target company."""
    # Check cache first
    cache = _load_cache()
    cache_key = f"company:{company_name.lower().strip()}"
    if cache_key in cache:
        cached = cache[cache_key]
        cached_time = datetime.fromisoformat(cached["timestamp"])
        if datetime.now() - cached_time < timedelta(hours=cache_ttl_hours):
            return [NetworkMatch(**m) for m in cached["matches"]]

    try:
        cookies = _load_cookies()
    except (FileNotFoundError, ValueError) as e:
        print(f"LinkedIn cookies error: {e}")
        return []

    session = _build_session(cookies)
    matches = []

    # Search 1st then 2nd degree
    for network_depth, degree in [("F", 1), ("S", 2)]:
        try:
            included = _search_people(session, company_name, network_depth)
            _extract_people(included, matches, company_name, degree)
        except Exception as e:
            print(f"Error searching {degree} degree connections: {e}")

        time.sleep(rate_limit)

    # Cache results
    cache[cache_key] = {
        "timestamp": datetime.now().isoformat(),
        "matches": [m.model_dump() for m in matches],
    }
    _save_cache(cache)

    return matches


def _extract_people(included: list[dict], matches: list, company_name: str, degree: int):
    """Extract people from LinkedIn Voyager API response."""
    company_lower = company_name.lower()

    for item in included:
        # Only look at EntityResultViewModel items (search result cards)
        item_type = item.get("$type", "")
        if "EntityResultViewModel" not in item_type:
            # Also accept items that have title + primarySubtitle structure
            if "title" not in item or "primarySubtitle" not in item:
                continue

        # Extract name
        title_obj = item.get("title", {})
        name = title_obj.get("text", "") if isinstance(title_obj, dict) else str(title_obj)
        if not name:
            continue

        # Extract headline / current title
        subtitle_obj = item.get("primarySubtitle", {})
        headline = subtitle_obj.get("text", "") if isinstance(subtitle_obj, dict) else str(subtitle_obj)

        # Extract LinkedIn profile URL
        nav_url = item.get("navigationUrl", "")
        # Clean tracking params from URL
        if "?" in nav_url:
            nav_url = nav_url.split("?")[0]

        # Filter: only include if company name appears in their headline
        if company_lower not in headline.lower() and company_lower not in name.lower():
            continue

        matches.append(
            NetworkMatch(
                person_name=name,
                connection_degree=degree,
                current_title=headline,
                company=company_name,
                linkedin_url=nav_url,
            )
        )


def format_referral_message(matches: list[NetworkMatch]) -> str:
    """Format network matches into a readable Telegram message."""
    if not matches:
        return "No connections found at this company in your LinkedIn network."

    first_degree = [m for m in matches if m.connection_degree == 1]
    second_degree = [m for m in matches if m.connection_degree == 2]

    lines = []
    total = len(matches)
    lines.append(f"Found {total} connection(s) at {matches[0].company}:\n")

    if first_degree:
        lines.append("1st Degree (can refer you directly):")
        for m in first_degree:
            line = f"  - {m.person_name}"
            if m.current_title:
                line += f"\n    {m.current_title}"
            if m.linkedin_url:
                line += f"\n    {m.linkedin_url}"
            lines.append(line)

    if second_degree:
        if first_degree:
            lines.append("")
        lines.append("2nd Degree (ask for intro):")
        for m in second_degree:
            line = f"  - {m.person_name}"
            if m.current_title:
                line += f"\n    {m.current_title}"
            if m.linkedin_url:
                line += f"\n    {m.linkedin_url}"
            lines.append(line)

    return "\n".join(lines)
