"""
sources/nepal_sites.py — Nepal job portals.

Two strategies per site:
  1. Targeted keyword searches (multiple terms × URL patterns)
  2. Browse all-recent listing pages (better recall)

nepal_source=True is always passed to filters.classify() so jobs
without explicit location become "Nepal — Verify Location" rather
than being excluded entirely.
"""

import time
import logging
from dataclasses import dataclass, field
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from config import SEARCH_TERMS, SCRAPE_DELAY
from filters import Job, classify
from sources.base import make_session, get_with_retry, extract_job_links
from storage import record_source_success, record_source_failure
from utils import is_fuzzy_duplicate

_log = logging.getLogger("job-monitor.nepal")


# ---------------------------------------------------------------------------
# Site registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SiteConfig:
    name:            str
    base_url:        str
    source_key:      str
    search_patterns: tuple[str, ...]
    browse_urls:     tuple[str, ...] = field(default_factory=tuple)


NEPAL_SITES: tuple[SiteConfig, ...] = (
    SiteConfig(
        name="MeroJob", base_url="https://merojob.com", source_key="merojob.com",
        search_patterns=(
            "https://merojob.com/search/?q={q}",
            "https://merojob.com/jobs/?s={q}",
        ),
        browse_urls=(
            "https://merojob.com/jobs/",
            "https://merojob.com/jobs/?page=2",
        ),
    ),
    SiteConfig(
        name="JobsNepal", base_url="https://www.jobsnepal.com", source_key="jobsnepal.com",
        search_patterns=(
            "https://www.jobsnepal.com/search-jobs/?search_keyword={q}",
            "https://www.jobsnepal.com/search/?q={q}",
        ),
        browse_urls=(
            "https://www.jobsnepal.com/",
            "https://www.jobsnepal.com/jobs/",
        ),
    ),
    SiteConfig(
        name="KumariJob", base_url="https://kumarijob.com", source_key="kumarijob.com",
        search_patterns=(
            "https://kumarijob.com/search-jobs/?q={q}",
            "https://kumarijob.com/search/?q={q}",
        ),
        browse_urls=(
            "https://kumarijob.com/",
            "https://kumarijob.com/jobs/",
        ),
    ),
    SiteConfig(
        name="Jobejee", base_url="https://www.jobejee.com", source_key="jobejee.com",
        search_patterns=(
            "https://www.jobejee.com/job-search?q={q}",
            "https://www.jobejee.com/jobs?keyword={q}",
        ),
        browse_urls=(
            "https://www.jobejee.com/jobs",
        ),
    ),
    SiteConfig(
        name="KantipurJob", base_url="https://kantipurjob.com", source_key="kantipurjob.com",
        search_patterns=(
            "https://kantipurjob.com/jobs?search={q}",
            "https://kantipurjob.com/search?q={q}",
        ),
        browse_urls=(
            "https://kantipurjob.com/jobs",
        ),
    ),
    SiteConfig(
        name="JobAxle", base_url="https://jobaxle.com", source_key="jobaxle.com",
        search_patterns=(
            "https://jobaxle.com/jobs?search={q}",
            "https://jobaxle.com/search?q={q}",
        ),
        browse_urls=(
            "https://jobaxle.com/jobs",
        ),
    ),
    SiteConfig(
        name="MeroRojgari", base_url="https://merorojgari.com", source_key="merorojgari.com",
        search_patterns=(
            "https://merorojgari.com/jobs?search={q}",
            "https://merorojgari.com/?s={q}",
        ),
        browse_urls=(
            "https://merorojgari.com/jobs",
            "https://merorojgari.com/",
        ),
    ),
    SiteConfig(
        name="NecoJobs", base_url="https://www.necojobs.com.np", source_key="necojobs.com.np",
        search_patterns=(
            "https://www.necojobs.com.np/search-jobs/?search_keyword={q}",
            "https://www.necojobs.com.np/search/?q={q}",
        ),
        browse_urls=(
            "https://www.necojobs.com.np/",
            "https://www.necojobs.com.np/jobs/",
        ),
    ),
    SiteConfig(
        name="JobsDynamics", base_url="https://jobsdynamics.com", source_key="jobsdynamics.com",
        search_patterns=(
            "https://jobsdynamics.com/jobs?search={q}",
            "https://jobsdynamics.com/?s={q}",
        ),
        browse_urls=(
            "https://jobsdynamics.com/jobs",
            "https://jobsdynamics.com/",
        ),
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_url(url: str, site: SiteConfig, session, seen_hrefs: set) -> list[Job]:
    r = get_with_retry(url, session=session)
    if r is None:
        return []
    soup  = BeautifulSoup(r.text, "html.parser")
    links = extract_job_links(soup, site.base_url)
    jobs: list[Job] = []
    for title, href, context in links:
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)
        job = classify(title=title, link=href, snippet=context,
                       source=site.source_key, nepal_source=True)
        if job:
            jobs.append(job)
    return jobs


def _merge(new: list[Job], pool: list[Job], seen_ids: set) -> None:
    for job in new:
        if job.id in seen_ids:
            continue
        if any(is_fuzzy_duplicate(job.title, j.title) for j in pool[-60:]):
            continue
        seen_ids.add(job.id)
        pool.append(job)


# ---------------------------------------------------------------------------
# Site scraper
# ---------------------------------------------------------------------------

def _scrape_site(site: SiteConfig) -> list[Job]:
    session     = make_session()
    all_jobs:   list[Job] = []
    seen_ids:   set[str]  = set()
    seen_hrefs: set[str]  = set()

    # Strategy 1 — keyword searches
    for term in SEARCH_TERMS:
        q = quote_plus(term)
        for pattern in site.search_patterns:
            jobs = _parse_url(pattern.format(q=q), site, session, seen_hrefs)
            _merge(jobs, all_jobs, seen_ids)
            if jobs:
                break   # first working URL wins for this term
        time.sleep(SCRAPE_DELAY)

    # Strategy 2 — browse all-recent
    for url in site.browse_urls:
        jobs = _parse_url(url, site, session, seen_hrefs)
        _merge(jobs, all_jobs, seen_ids)
        time.sleep(SCRAPE_DELAY)

    return all_jobs


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fetch_all_nepal_sites() -> list[Job]:
    all_jobs:    list[Job] = []
    global_seen: set[str]  = set()

    for site in NEPAL_SITES:
        try:
            site_jobs = _scrape_site(site)
            new: list[Job] = []
            for job in site_jobs:
                if job.id not in global_seen:
                    global_seen.add(job.id)
                    new.append(job)
            all_jobs.extend(new)
            record_source_success(site.source_key, len(new))
            _log.info(f"{site.name}: {len(new)} relevant jobs")
        except Exception as e:
            _log.error(f"{site.name}: fatal, skipping: {e}")
            record_source_failure(site.source_key)

    return all_jobs
