"""
sources/base.py — Shared HTTP session, retry logic, and link extraction.
"""

import re
import time
import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

from config import SESSION_HEADERS, REQUEST_TIMEOUT, MAX_RETRIES, RETRY_BACKOFF

log = logging.getLogger("job-monitor.http")

# Words that indicate navigation / UI links — skip these anchors
_NAV_WORDS: frozenset[str] = frozenset({
    "home", "about", "contact", "login", "register", "sign up", "sign in",
    "forgot", "privacy", "terms", "careers", "jobs", "post a job",
    "employers", "candidates", "blog", "faq", "help", "search", "filter",
    "next", "prev", "previous", "page", "load more", "view all",
})


def make_session() -> requests.Session:
    """Create a reusable Session with default headers."""
    s = requests.Session()
    s.headers.update(SESSION_HEADERS)
    return s


def get_with_retry(
    url:     str,
    session: Optional[requests.Session] = None,
    *,
    timeout:  int   = REQUEST_TIMEOUT,
    retries:  int   = MAX_RETRIES,
    backoff:  float = RETRY_BACKOFF,
    extra_headers: dict | None = None,
) -> Optional[requests.Response]:
    """
    GET with exponential backoff.
    Returns Response on success, None on permanent failure.
    """
    fetch = (session or requests).get
    kwargs: dict = {"timeout": timeout, "allow_redirects": True}
    if extra_headers:
        kwargs["headers"] = extra_headers

    for attempt in range(retries):
        try:
            r = fetch(url, **kwargs)

            if r.status_code in (404, 410):
                log.debug(f"[{r.status_code}] Permanent: {url}")
                return None

            if r.status_code == 403:
                log.warning(f"[403] Blocked: {url}")
                return None

            if r.status_code == 429:
                wait = backoff * (2 ** attempt) + 30
                log.warning(f"[429] Rate-limited. Backing off {wait:.0f}s: {url}")
                time.sleep(wait)
                continue

            r.raise_for_status()
            return r

        except requests.exceptions.Timeout:
            log.warning(f"Timeout attempt {attempt+1}/{retries}: {url}")
        except requests.exceptions.ConnectionError as e:
            log.warning(f"ConnectionError attempt {attempt+1}/{retries}: {url} — {e}")
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else 0
            log.warning(f"[{code}] HTTP error attempt {attempt+1}/{retries}: {url}")
            if code < 500:
                return None   # 4xx → don't retry
        except Exception as e:
            log.error(f"Unexpected error fetching {url}: {e}")
            return None

        if attempt < retries - 1:
            wait = backoff * (2 ** attempt)
            log.debug(f"Retry in {wait:.0f}s…")
            time.sleep(wait)

    log.warning(f"All {retries} attempts exhausted: {url}")
    return None


def extract_job_links(
    soup:     BeautifulSoup,
    base_url: str,
    min_text_len: int = 5,
    max_text_len: int = 160,
) -> list[tuple[str, str, str]]:
    """
    Heuristic anchor scanner. Tries specific selectors first, broad fallback second.
    Returns list of (title, absolute_href, parent_context_text).
    """
    results:    list[tuple[str, str, str]] = []
    seen_hrefs: set[str] = set()

    # Try specific selectors that commonly hold job titles
    SELECTORS = [
        "h1 a", "h2 a", "h3 a", "h4 a",
        ".job-title a", ".position a", ".title a", ".job-name a",
        "[class*='job-title'] a", "[class*='job_title'] a",
        "[class*='position'] a", "[class*='vacancy'] a",
        "[class*='listing'] a", "[class*='job-card'] a",
        "td a", "li a",
    ]

    candidates: list = []
    for sel in SELECTORS:
        found = soup.select(sel)
        if found:
            candidates.extend(found)

    if not candidates:
        candidates = soup.find_all("a", href=True)

    for a in candidates:
        text = a.get_text(strip=True)
        href = (a.get("href") or "").strip()

        if not href or not text:
            continue
        if len(text) < min_text_len or len(text) > max_text_len:
            continue
        if any(w == text.lower().strip() for w in _NAV_WORDS):
            continue
        # Skip obvious non-job links
        if re.search(r"(javascript:|mailto:|#\s*$)", href):
            continue

        # Resolve relative
        if not href.startswith("http"):
            href = base_url.rstrip("/") + "/" + href.lstrip("/")

        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        parent  = a.find_parent(["div", "li", "tr", "article", "section"])
        context = parent.get_text(" ", strip=True)[:500] if parent else text
        results.append((text, href, context))

    return results
