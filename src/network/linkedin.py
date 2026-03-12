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
TRUSTED_CONNECTIONS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "trusted_connections.yaml")


def load_trusted_connections() -> list[dict]:
    """Load trusted connections from config/trusted_connections.yaml."""
    path = os.path.abspath(TRUSTED_CONNECTIONS_PATH)
    if not os.path.exists(path):
        return []
    import yaml
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return data.get("trusted_connections", []) if data else []


def _get_shared_connections(session: requests.Session, vanity_name: str) -> list[dict]:
    """Fetch shared connections for a LinkedIn profile (by vanity name from URL).

    Returns list of dicts with 'name' and 'url' for each shared connection.
    Falls back to empty list on any error.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Step 1: resolve vanity name → internal profile ID
    profile_resp = session.get(
        f"https://www.linkedin.com/voyager/api/identity/profiles/{vanity_name}",
        timeout=10,
    )
    if profile_resp.status_code != 200:
        logger.debug(f"Could not fetch profile {vanity_name}: {profile_resp.status_code}")
        return []

    profile_data = profile_resp.json()
    # Extract the memberId or entityUrn
    entity_urn = profile_data.get("entityUrn", "")
    member_id = entity_urn.split(":")[-1] if entity_urn else ""
    if not member_id:
        return []

    # Step 2: fetch shared connections
    sc_resp = session.get(
        f"https://www.linkedin.com/voyager/api/relationships/sharedConnections"
        f"?q=memberConnections&memberIdentity={vanity_name}&start=0&count=10",
        timeout=10,
    )
    if sc_resp.status_code != 200:
        logger.debug(f"Shared connections for {vanity_name} returned {sc_resp.status_code}")
        return []

    sc_data = sc_resp.json()
    shared = []
    for item in sc_data.get("included", []):
        first = item.get("firstName", {})
        last = item.get("lastName", {})
        first_text = first.get("text", "") if isinstance(first, dict) else str(first)
        last_text = last.get("text", "") if isinstance(last, dict) else str(last)
        name = f"{first_text} {last_text}".strip()
        vanity = item.get("publicIdentifier", "")
        url = f"https://www.linkedin.com/in/{vanity}" if vanity else ""
        if name:
            shared.append({"name": name, "url": url})
    return shared


def _vanity_from_url(linkedin_url: str) -> str:
    """Extract vanity name from a LinkedIn profile URL."""
    url = linkedin_url.rstrip("/")
    return url.split("/in/")[-1].split("?")[0] if "/in/" in url else ""


def _enrich_with_warm_paths(
    matches: list[NetworkMatch],
    session: requests.Session,
    trusted: list[dict],
    rate_limit: float,
) -> None:
    """For each match, check if any trusted connection is a shared connection.

    Mutates matches in-place, setting warm_path_via / warm_path_url.
    Also marks 1st-degree matches that ARE in the trusted list directly.
    """
    import logging
    logger = logging.getLogger(__name__)

    if not trusted:
        return

    # Normalise trusted list for fast lookup (by name and vanity)
    trusted_by_name = {t["name"].lower(): t for t in trusted}
    trusted_by_vanity = {_vanity_from_url(t.get("linkedin_url", "")).lower(): t for t in trusted if t.get("linkedin_url")}

    for match in matches:
        # 1st-degree: check if this person IS a trusted contact
        if match.connection_degree == 1:
            name_lower = match.person_name.lower()
            vanity = _vanity_from_url(match.linkedin_url).lower()
            if name_lower in trusted_by_name or (vanity and vanity in trusted_by_vanity):
                match.warm_path_via = "★ Trusted contact"
                match.warm_path_url = match.linkedin_url
            continue

        # 2nd-degree: check shared connections against trusted list
        vanity = _vanity_from_url(match.linkedin_url)
        if not vanity:
            continue
        try:
            shared = _get_shared_connections(session, vanity)
            time.sleep(rate_limit)
        except Exception as e:
            logger.debug(f"Shared connections error for {match.person_name}: {e}")
            continue

        for sc in shared:
            sc_name = sc.get("name", "").lower()
            sc_vanity = _vanity_from_url(sc.get("url", "")).lower()
            trusted_entry = trusted_by_name.get(sc_name) or trusted_by_vanity.get(sc_vanity)
            if trusted_entry:
                match.warm_path_via = trusted_entry["name"]
                match.warm_path_url = trusted_entry.get("linkedin_url", "")
                break  # first match is enough


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
    import logging
    logger = logging.getLogger(__name__)

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
    logger.info(f"LinkedIn search [{network_depth}] status: {resp.status_code}")

    if resp.status_code == 401:
        raise RuntimeError("LinkedIn cookies have expired. Please re-export your cookies from the browser and update your cookies file.")
    if resp.status_code == 429:
        raise RuntimeError("LinkedIn rate limit reached. Please wait a few minutes before trying again.")
    if resp.status_code != 200:
        logger.warning(f"LinkedIn API returned {resp.status_code}: {resp.text[:300]}")
        raise RuntimeError(f"LinkedIn API returned an unexpected error (HTTP {resp.status_code}). Check the server logs for details.")

    data = resp.json()
    included = data.get("included", [])
    logger.info(f"LinkedIn search [{network_depth}] returned {len(included)} items")
    return included


def find_connections_at_company(
    company_name: str,
    rate_limit: float = 3.0,
    cache_ttl_hours: int = 24,
    force_refresh: bool = False,
) -> list[NetworkMatch]:
    """Find 1st and 2nd degree connections at a target company."""
    # Check cache first
    cache = _load_cache()
    cache_key = f"company:{company_name.lower().strip()}"
    if not force_refresh and cache_key in cache:
        cached = cache[cache_key]
        cached_time = datetime.fromisoformat(cached["timestamp"])
        # Only use cache if it has results; always re-fetch if previous result was empty
        if cached["matches"] and datetime.now() - cached_time < timedelta(hours=cache_ttl_hours):
            return [NetworkMatch(**m) for m in cached["matches"]]

    try:
        cookies = _load_cookies()
    except (FileNotFoundError, ValueError) as e:
        raise RuntimeError(f"LinkedIn cookies error: {e}") from e

    session = _build_session(cookies)
    matches = []
    errors = []

    # Search 1st then 2nd degree
    for network_depth, degree in [("F", 1), ("S", 2)]:
        try:
            included = _search_people(session, company_name, network_depth)
            _extract_people(included, matches, company_name, degree)
        except Exception as e:
            errors.append(f"{degree}° search failed: {e}")

        time.sleep(rate_limit)

    if errors and not matches:
        raise RuntimeError("LinkedIn search failed: " + "; ".join(errors))

    # Enrich with warm paths via trusted connections
    trusted = load_trusted_connections()
    if trusted and matches:
        try:
            _enrich_with_warm_paths(matches, session, trusted, rate_limit)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Warm path enrichment failed: {e}")

    # Cache results (only cache if no errors or we got results)
    if not errors or matches:
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

        # Filter: skip if we have a headline and it clearly doesn't mention the company.
        # Be lenient — many people write short headlines like "PM at Shopify" but also
        # just "Product Manager". Only skip if another company name is prominent.
        if headline and company_lower not in headline.lower() and company_lower not in nav_url.lower():
            # Still include if no competing company keyword found (headline is generic)
            competing = any(
                word in headline.lower()
                for word in ["at ", " @ ", "with ", "for "]
            )
            if competing:
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
