"""
sources/nepal_sites.py — Scrapers for all 10 Nepal job portals.

Each portal is described by a SiteConfig.  A single generic function
(_scrape_site) handles fetching + parsing for all of them.

nepal_source=True is passed to filters.classify() for every portal here,
meaning a job tagged "remote" on these sites is treated as Nepal-eligible
without needing an explicit "Nepal" mention in the text.
"""

import time
import logging
from dataclasses import dataclass
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from config import HEADERS, SCRAPE_DELAY, SEARCH_TERMS, log
from filters import Job, classify
from sources.base import get_with_retry, parse_job_links

_log = logging.getLogger("job-monitor.nepal")


# ---------------------------------------------------------------------------
# Site registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SiteConfig:
    name:         str
    base_url:     str
    url_patterns: tuple[str, ...]   # each may contain {q} placeholder
    source_key:   str               # short label used in emails


NEPAL_SITES: tuple[SiteConfig, ...] = (
    SiteConfig(
        name="MeroJob",
        base_url="https://merojob.com",
        url_patterns=(
            "https://merojob.com/search/?q={q}",
            "https://merojob.com/jobs/?s={q}",
        ),
        source_key="merojob.com",
    ),
    SiteConfig(
        name="JobsNepal",
        base_url="https://www.jobsnepal.com",
        url_patterns=(
            "https://www.jobsnepal.com/search-jobs/?search_keyword={q}",
            "https://www.jobsnepal.com/search/?q={q}",
        ),
        source_key="jobsnepal.com",
    ),
    SiteConfig(
        name="KumariJob",
        base_url="https://kumarijob.com",
        url_patterns=(
            "https://kumarijob.com/search-jobs/?q={q}",
            "https://kumarijob.com/search/?q={q}",
        ),
        source_key="kumarijob.com",
    ),
    SiteConfig(
        name="Jobejee",
        base_url="https://www.jobejee.com",
        url_patterns=(
            "https://www.jobejee.com/job-search?q={q}",
            "https://www.jobejee.com/jobs?keyword={q}",
        ),
        source_key="jobejee.com",
    ),
    SiteConfig(
        name="KantipurJob",
        base_url="https://kantipurjob.com",
        url_patterns=(
            "https://kantipurjob.com/jobs?search={q}",
            "https://kantipurjob.com/search?q={q}",
        ),
        source_key="kantipurjob.com",
    ),
    SiteConfig(
        name="JobAxle",
        base_url="https://jobaxle.com",
        url_patterns=(
            "https://jobaxle.com/jobs?search={q}",
            "https://jobaxle.com/search?q={q}",
        ),
        source_key="jobaxle.com",
    ),
    SiteConfig(
        name="MeroRojgari",
        base_url="https://merorojgari.com",
        url_patterns=(
            "https://merorojgari.com/jobs?search={q}",
            "https://merorojgari.com/?s={q}",
        ),
        source_key="merorojgari.com",
    ),
    SiteConfig(
        name="NecoJobs",
        base_url="https://www.necojobs.com.np",
        url_patterns=(
            "https://www.necojobs.com.np/search-jobs/?search_keyword={q}",
            "https://www.necojobs.com.np/search/?q={q}",
        ),
        source_key="necojobs.com.np",
    ),
    SiteConfig(
        name="RamroJob",
        base_url="https://ramrojob.com",
        url_patterns=(
            "https://ramrojob.com/jobs?search={q}",
            "https://ramrojob.com/?s={q}",
        ),
        source_key="ramrojob.com",
    ),
    SiteConfig(
        name="JobsDynamics",
        base_url="https://jobsdynamics.com",
        url_patterns=(
            "https://jobsdynamics.com/jobs?search={q}",
            "https://jobsdynamics.com/?s={q}",
        ),
        source_key="jobsdynamics.com",
    ),
)


# ---------------------------------------------------------------------------
# Generic scraper
# ---------------------------------------------------------------------------

def _scrape_site(site: SiteConfig, term: str) -> list[Job]:
    """Fetch one search term from one portal. Returns filtered Job list."""
    q    = quote_plus(term)
    jobs: list[Job] = []

    for pattern in site.url_patterns:
        url = pattern.format(q=q)
        r   = get_with_retry(url, headers=HEADERS)
        if r is None:
            _log.debug(f"{site.name}: no response for {url}")
            continue

        soup  = BeautifulSoup(r.text, "html.parser")
        links = parse_job_links(soup, site.base_url)

        for title, href, context in links:
            job = classify(
                title=title,
                link=href,
                snippet=context,
                source=site.source_key,
                nepal_source=True,          # all Nepal portals are trusted Nepal sources
            )
            if job:
                jobs.append(job)

        _log.debug(f"{site.name} [{term}]: {url} → {len(jobs)} passing")
        break  # first working URL wins; don't double-count

    return jobs


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fetch_all_nepal_sites() -> list[Job]:
    """
    Run every (site × search_term) combination.
    Deduplicates by job ID before returning.
    Catches and logs exceptions per-site so one broken portal never
    stops the rest.
    """
    all_jobs: list[Job] = []
    seen_ids: set[str]  = set()

    for site in NEPAL_SITES:
        site_jobs: list[Job] = []
        try:
            for term in SEARCH_TERMS:
                try:
                    for job in _scrape_site(site, term):
                        if job.id not in seen_ids:
                            seen_ids.add(job.id)
                            site_jobs.append(job)
                except Exception as e:
                    _log.error(f"{site.name} [{term}]: unexpected error: {e}")
                time.sleep(SCRAPE_DELAY)

        except Exception as e:
            _log.error(f"{site.name}: fatal error, skipping site: {e}")
            continue

        all_jobs.extend(site_jobs)
        _log.info(f"{site.name}: {len(site_jobs)} relevant jobs")

    return all_jobs
