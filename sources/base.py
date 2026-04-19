"""
sources/base.py — Shared HTTP utilities and retry logic.
"""

import time
import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

from config import HEADERS, REQUEST_TIMEOUT, MAX_RETRIES, RETRY_BACKOFF

log = logging.getLogger("job-monitor.http")

# Nav links to skip when scanning anchor text
_NAV_WORDS = {
    "home", "about", "contact", "login", "register", "sign up", "sign in",
    "forgot", "privacy", "terms", "careers", "jobs", "post a job",
    "employers", "candidates", "blog", "faq", "help",
}


def get_with_retry(
    url:     str,
    headers: dict = HEADERS,
    *,
    timeout: int  = REQUEST_TIMEOUT,
    retries: int  = MAX_RETRIES,
    backoff: float = RETRY_BACKOFF,
    session: Optional[requests.Session] = None,
) -> Optional[requests.Response]:
    """
    GET with exponential back-off.
    Returns the Response on success, None on permanent failure.
    """
    fetch = (session or requests).get

    for attempt in range(retries):
        try:
            r = fetch(url, headers=headers, timeout=timeout, allow_redirects=True)

            if r.status_code in (404, 410):
                log.debug(f"[HTTP {r.status_code}] {url}")
                return None          # permanent — don't retry

            if r.status_code == 429:
                wait = backoff * (2 ** attempt) + 30
                log.warning(f"Rate-limited (429) by {url}. Waiting {wait:.0f}s…")
                time.sleep(wait)
                continue

            r.raise_for_status()
            return r

        except requests.exceptions.Timeout:
            log.warning(f"Timeout on attempt {attempt + 1}/{retries}: {url}")
        except requests.exceptions.ConnectionError as e:
            log.warning(f"Connection error on attempt {attempt + 1}/{retries}: {url} — {e}")
        except requests.exceptions.HTTPError as e:
            log.warning(f"HTTP error on attempt {attempt + 1}/{retries}: {url} — {e}")
            # 5xx → retry; 4xx → give up
            if r.status_code < 500:
                return None
        except Exception as e:
            log.error(f"Unexpected error fetching {url}: {e}")
            return None

        if attempt < retries - 1:
            wait = backoff * (2 ** attempt)
            log.debug(f"Backing off {wait:.0f}s before retry…")
            time.sleep(wait)

    log.warning(f"All {retries} attempts failed for {url}")
    return None


def parse_job_links(
    soup:     BeautifulSoup,
    base_url: str,
) -> list[tuple[str, str, str]]:
    """
    Heuristic anchor scanner.
    Returns list of (title, href, parent_text) tuples.
    Tries specific selectors first, falls back to broad scan.
    """
    results: list[tuple[str, str, str]] = []
    seen_hrefs: set[str] = set()

    SPECIFIC_SELECTORS = [
        "h1 a", "h2 a", "h3 a",
        ".job-title a", ".position a", ".title a",
        "[class*='job'] a", "[class*='vacancy'] a",
        "[class*='position'] a", "[class*='listing'] a",
        "td a", "li a",
    ]

    candidates = []
    for sel in SPECIFIC_SELECTORS:
        found = soup.select(sel)
        if found:
            candidates.extend(found)

    if not candidates:
        candidates = soup.find_all("a", href=True)

    for a in candidates:
        text = a.get_text(strip=True)
        href = (a.get("href") or "").strip()

        if not href or not text or len(text) < 4 or len(text) > 150:
            continue

        # Skip nav / utility links
        if any(w in text.lower() for w in _NAV_WORDS):
            continue

        # Resolve relative URLs
        if not href.startswith("http"):
            href = base_url.rstrip("/") + "/" + href.lstrip("/")

        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        parent = a.find_parent(["div", "li", "tr", "article", "section"])
        context = parent.get_text(" ", strip=True)[:400] if parent else text

        results.append((text, href, context))

    return results
