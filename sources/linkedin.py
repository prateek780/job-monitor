"""
sources/linkedin.py — LinkedIn public guest API (no login required).

Searches three location contexts:
  1. "Butwal, Lumbini Province, Nepal"  → category Butwal Onsite (if matching)
  2. "Nepal"                             → remote-only unless explicitly Butwal
  3. "Remote"                            → Nepal Remote (only if Nepal signal present)

nepal_source=False here — we require explicit Nepal/Butwal signals in the
card text because LinkedIn indexes worldwide jobs and is less trustworthy
about geography than Nepal-specific portals.
"""

import re
import time
import logging
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT, log
from filters import Job, classify
from sources.base import get_with_retry

_log = logging.getLogger("job-monitor.linkedin")

_BASE_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
)

_LI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.linkedin.com/",
}

# (location string sent to API, human label)
_LOCATIONS: tuple[tuple[str, str], ...] = (
    ("Butwal, Lumbini Province, Nepal", "Butwal"),
    ("Nepal",                            "Nepal"),
    ("Remote",                           "Remote"),
)

_KEYWORDS: tuple[str, ...] = (
    "receptionist",
    "customer service",
    "front desk",
    "admin assistant",
    "data entry",
    "call center",
    "office assistant",
    "cashier",
    "accounts coordinator",
)

_INTER_REQUEST_DELAY = 3.0    # LinkedIn rate-limits hard; be polite


# ---------------------------------------------------------------------------
# Fetch raw cards from LinkedIn guest API
# ---------------------------------------------------------------------------

def _fetch_cards(keyword: str, location: str, start: int = 0) -> list:
    """
    Calls the LinkedIn guest jobs API and returns a list of BeautifulSoup
    card elements.  Returns [] on any error.
    """
    url = (
        f"{_BASE_URL}"
        f"?keywords={quote_plus(keyword)}"
        f"&location={quote_plus(location)}"
        f"&start={start}"
        "&f_TPR=r86400"    # posted in last 24 h
    )
    r = get_with_retry(url, headers=_LI_HEADERS, timeout=REQUEST_TIMEOUT, retries=2)
    if r is None:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    return soup.find_all("div", class_=re.compile(r"base-card"))


# ---------------------------------------------------------------------------
# Parse a single card div
# ---------------------------------------------------------------------------

def _parse_card(card, loc_label: str) -> dict | None:
    """Return raw (title, link, snippet) or None if unparseable."""
    try:
        title_tag = card.find(
            ["h3", "span"],
            class_=re.compile(r"base-search-card__title"),
        )
        title = title_tag.get_text(strip=True) if title_tag else ""

        link_tag = card.find("a", class_=re.compile(r"base-card__full-link"))
        if not link_tag:
            link_tag = card.find("a", href=True)
        link = (link_tag.get("href") or "").split("?")[0].strip() if link_tag else ""

        company_tag = card.find(
            ["h4", "span"],
            class_=re.compile(r"base-search-card__subtitle"),
        )
        company = company_tag.get_text(strip=True) if company_tag else ""

        loc_tag = card.find(
            "span",
            class_=re.compile(r"job-search-card__location"),
        )
        loc_text = loc_tag.get_text(strip=True) if loc_tag else loc_label

        snippet = f"{company} · {loc_text}".strip(" ·")
        return {"title": title, "link": link, "snippet": snippet}
    except Exception as e:
        _log.debug(f"Card parse error: {e}")
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fetch_linkedin() -> list[Job]:
    """
    Search LinkedIn for all (keyword × location) combinations.
    Strict: nepal_source=False — only includes jobs where the card text
    itself contains clear Nepal/Butwal or remote-Nepal signals.
    """
    all_jobs: list[Job] = []
    seen_ids: set[str]  = set()

    for location, loc_label in _LOCATIONS:
        for keyword in _KEYWORDS:
            try:
                cards = _fetch_cards(keyword, location)
                _log.debug(
                    f"LinkedIn [{loc_label}] '{keyword}': {len(cards)} cards"
                )
                for card in cards:
                    raw = _parse_card(card, loc_label)
                    if not raw:
                        continue

                    job = classify(
                        title=raw["title"],
                        link=raw["link"],
                        snippet=raw["snippet"],
                        source="linkedin.com",
                        nepal_source=False,     # stricter for LinkedIn
                    )
                    if job and job.id not in seen_ids:
                        seen_ids.add(job.id)
                        all_jobs.append(job)

            except Exception as e:
                _log.error(
                    f"LinkedIn [{loc_label}] '{keyword}': unexpected error: {e}"
                )

            time.sleep(_INTER_REQUEST_DELAY)

    _log.info(f"LinkedIn: {len(all_jobs)} relevant jobs")
    return all_jobs
