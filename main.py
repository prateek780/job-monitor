"""
main.py — Daily job monitor entry point.

Run:  python main.py

Pipeline:
  1. Validate config
  2. Init DB, start run record
  3. Fetch from all Nepal portals + LinkedIn
  4. Deduplicate against seen-jobs DB
  5. Email digest to all recipients
  6. Persist new jobs, finish run record
  7. Prune old DB entries
"""

import sys
from datetime import datetime

from config import MAX_JOBS_PER_EMAIL, SEND_EMPTY_DIGEST, CATEGORY_ORDER, log
from emailer import send_digest, validate_email_config
from filters import Job
from sources import fetch_all_nepal_sites, fetch_linkedin
from storage import (
    init_db, load_seen_ids, save_jobs, prune_old_jobs,
    start_run, finish_run,
)
from utils import is_fuzzy_duplicate


# ---------------------------------------------------------------------------
# Search pipeline
# ---------------------------------------------------------------------------

def search_all() -> tuple[list[Job], list[str], list[str]]:
    """
    Run all sources. Returns (jobs, sources_ok, sources_failed).
    Failures in individual sources are caught and logged — they never
    stop the rest of the run.
    """
    log.info("Starting job search across all sources…")

    raw:            list[Job] = []
    sources_ok:     list[str] = []
    sources_failed: list[str] = []

    fetchers = [
        ("Nepal Portals", fetch_all_nepal_sites),
        ("LinkedIn",      fetch_linkedin),
    ]

    for name, fn in fetchers:
        try:
            jobs = fn()
            raw.extend(jobs)
            sources_ok.append(name)
            log.info(f"{name}: {len(jobs)} jobs")
        except Exception as e:
            log.error(f"{name}: top-level failure: {e}")
            sources_failed.append(name)

    # Global dedup by ID
    seen_ids: set[str] = set()
    unique:   list[Job] = []
    for job in raw:
        if job.id not in seen_ids:
            seen_ids.add(job.id)
            unique.append(job)

    log.info(f"Total unique relevant jobs this run: {len(unique)}")
    return unique, sources_ok, sources_failed


def sort_jobs(jobs: list[Job]) -> list[Job]:
    """Sort by category order, then score descending."""
    order = {cat: i for i, cat in enumerate(CATEGORY_ORDER)}
    return sorted(
        jobs,
        key=lambda j: (order.get(j.category, 99), -j.score, j.title.lower()),
    )


# ---------------------------------------------------------------------------
# Run summary log
# ---------------------------------------------------------------------------

def log_summary(jobs: list[Job], sources_ok: list[str], sources_failed: list[str]) -> None:
    from collections import Counter
    counts = Counter(j.category for j in jobs)
    log.info("─" * 50)
    log.info("RUN SUMMARY")
    for cat in CATEGORY_ORDER:
        log.info(f"  {cat}: {counts.get(cat, 0)} jobs")
    log.info(f"  Sources OK:     {', '.join(sources_ok) or 'none'}")
    log.info(f"  Sources FAILED: {', '.join(sources_failed) or 'none'}")
    log.info("─" * 50)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=" * 60)
    log.info("Daily Job Monitor — Nepal + LinkedIn Edition v2")
    log.info("=" * 60)

    # Validate email config first
    missing = validate_email_config()
    if missing:
        log.error(f"Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    # Init DB
    init_db()
    run_id = start_run()

    # Prune old jobs silently
    prune_old_jobs(days=90)

    # Load seen IDs
    seen_ids = load_seen_ids()
    log.info(f"{len(seen_ids)} jobs already seen in previous runs")

    # Fetch all
    all_jobs, sources_ok, sources_failed = search_all()

    # Filter to only new
    new_jobs = [j for j in all_jobs if j.id not in seen_ids]
    log.info(f"{len(new_jobs)} genuinely new jobs")

    # Sort and cap
    new_jobs = sort_jobs(new_jobs)
    if len(new_jobs) > MAX_JOBS_PER_EMAIL:
        log.info(f"Capping email at {MAX_JOBS_PER_EMAIL} (found {len(new_jobs)})")
        to_email = new_jobs[:MAX_JOBS_PER_EMAIL]
    else:
        to_email = new_jobs

    log_summary(to_email, sources_ok, sources_failed)

    today = datetime.now().strftime("%Y-%m-%d")

    # Send
    if not to_email and not SEND_EMPTY_DIGEST:
        log.info("No new jobs and SEND_EMPTY_DIGEST=False — skipping email.")
        jobs_emailed = 0
    else:
        try:
            send_digest(to_email, today)
            jobs_emailed = len(to_email)
        except Exception as e:
            log.error(f"Email send failed: {e}")
            finish_run(run_id, len(all_jobs), len(new_jobs), 0,
                       sources_ok, sources_failed, status="email_failed")
            log.error("Not updating seen-jobs DB — will retry tomorrow.")
            sys.exit(1)

    # Persist all new jobs (even those above the cap)
    inserted = save_jobs(new_jobs)
    log.info(f"Saved {inserted} new job IDs to DB")

    finish_run(
        run_id,
        jobs_found=len(all_jobs),
        jobs_new=len(new_jobs),
        jobs_emailed=jobs_emailed,
        sources_ok=sources_ok,
        sources_failed=sources_failed,
        status="ok",
    )
    log.info("Done. ✓")


if __name__ == "__main__":
    main()
