"""
sources/linkedin.py — LinkedIn public guest API.

Improvements over v1:
  - 20+ role keywords
  - 3 location contexts (Butwal, Nepal, Remote)
  - Pagination: 3 pages per query (offsets 0, 25, 50)
  - Separate remote-only search with f_WT=2 filter
  - Robust card parsing with multiple fallback selectors
  - Rate-limit aware with 429 backoff

nepal_source=False: LinkedIn indexes worldwide jobs so we require explicit
Nepal/Butwal signals in the card text, unlike Nepal-specific portals.
"""

import re
import time
import logging
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from config import (
    LINKEDIN_KEYWORDS, LINKEDIN_LOCATIONS, LINKEDIN_PAGE_OFFSETS,
    LINKEDIN_DELAY, REQUEST_TIMEOUT,
)
from filters import Job, classify
from sources.base import get_with_retry
from storage import record_source_success, record_source_failure
from utils import is_fuzzy_duplicate

_log = logging.getLogger("job-monitor.linkedin")

_BASE = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

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

_SOURCE_KEY = "linkedin.com"


# ---------------------------------------------------------------------------
# Fetch raw cards from LinkedIn guest API
# ---------------------------------------------------------------------------

def _fetch_cards(keyword: str, location: str, start: int = 0, remote_only: bool = False) -> list:
    """
    Calls LinkedIn public guest jobs search and returns BeautifulSoup card elements.
    """
    params = (
        f"?keywords={quote_plus(keyword)}"
        f"&location={quote_plus(location)}"
        f"&start={start}"
        "&f_TPR=r86400"   # posted in last 24 hours
    )
    if remote_only:
        params += "&f_WT=2"  # work type = remote

    url = _BASE + params
    r   = get_with_retry(url, extra_headers=_LI_HEADERS, timeout=REQUEST_TIMEOUT, retries=2)
    if r is None:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    return soup.find_all("div", class_=re.compile(r"base-card"))


# ---------------------------------------------------------------------------
# Parse one job card
# ---------------------------------------------------------------------------

def _parse_card(card, loc_label: str) -> tuple[str, str, str] | None:
    """Returns (title, link, snippet) or None."""
    try:
        # Title
        title_tag = (
            card.find(["h3", "span"], class_=re.compile(r"base-search-card__title"))
            or card.find(["h3", "h2", "h4"])
        )
        title = title_tag.get_text(strip=True) if title_tag else ""

        # Link
        link_tag = (
            card.find("a", class_=re.compile(r"base-card__full-link"))
            or card.find("a", href=re.compile(r"linkedin\.com/jobs/view"))
            or card.find("a", href=True)
        )
        link = ""
        if link_tag:
            link = (link_tag.get("href") or "").split("?")[0].strip()

        # Company
        company_tag = card.find(
            ["h4", "span", "a"],
            class_=re.compile(r"base-search-card__subtitle"),
        )
        company = company_tag.get_text(strip=True) if company_tag else ""

        # Location
        loc_tag = card.find("span", class_=re.compile(r"job-search-card__location"))
        loc_text = loc_tag.get_text(strip=True) if loc_tag else loc_label

        snippet = f"{company} · {loc_text}".strip(" ·")

        if not title or not link:
            return None
        return title, link, snippet

    except Exception as e:
        _log.debug(f"Card parse error: {e}")
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fetch_linkedin() -> list[Job]:
    """
    Search LinkedIn for (keyword × location × page) combinations.
    Also runs a dedicated remote-only search for Nepal to maximise recall.
    """
    all_jobs:   list[Job] = []
    seen_ids:   set[str]  = set()
    total_cards            = 0
    blocked                = False

    for location, loc_label in LINKEDIN_LOCATIONS:
        for keyword in LINKEDIN_KEYWORDS:
            for offset in LINKEDIN_PAGE_OFFSETS:
                if blocked:
                    break
                cards = _fetch_cards(keyword, location, start=offset)
                if not cards and offset == 0:
                    pass   # no results for this query — normal
                total_cards += len(cards)
                _log.debug(f"[{loc_label}] '{keyword}' start={offset}: {len(cards)} cards")

                for card in cards:
                    parsed = _parse_card(card, loc_label)
                    if not parsed:
                        continue
                    title, link, snippet = parsed
                    job = classify(
                        title=title,
                        link=link,
                        snippet=snippet,
                        source=_SOURCE_KEY,
                        nepal_source=False,
                    )
                    if job and job.id not in seen_ids:
                        if not any(is_fuzzy_duplicate(job.title, j.title) for j in all_jobs[-40:]):
                            seen_ids.add(job.id)
                            all_jobs.append(job)

                time.sleep(LINKEDIN_DELAY)

            if blocked:
                break

    # Extra pass: remote-only search for Nepal (f_WT=2 filter)
    if not blocked:
        for keyword in LINKEDIN_KEYWORDS[:10]:   # top 10 keywords only
            cards = _fetch_cards(keyword, "Nepal", start=0, remote_only=True)
            total_cards += len(cards)
            for card in cards:
                parsed = _parse_card(card, "Nepal")
                if not parsed:
                    continue
                title, link, snippet = parsed
                job = classify(
                    title=title,
                    link=link,
                    snippet=snippet,
                    source=_SOURCE_KEY,
                    nepal_source=False,
                )
                if job and job.id not in seen_ids:
                    if not any(is_fuzzy_duplicate(job.title, j.title) for j in all_jobs[-40:]):
                        seen_ids.add(job.id)
                        all_jobs.append(job)
            time.sleep(LINKEDIN_DELAY)

    _log.info(
        f"LinkedIn: {total_cards} cards scanned → {len(all_jobs)} relevant jobs"
    )
    if all_jobs:
        record_source_success(_SOURCE_KEY, len(all_jobs))
    else:
        record_source_failure(_SOURCE_KEY)

    return all_jobs
