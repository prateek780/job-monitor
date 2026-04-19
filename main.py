"""
main.py — Daily job monitor entry point.

Run:  python main.py

What it does:
  1. Validates config
  2. Initialises SQLite DB
  3. Fetches jobs from all Nepal portals + LinkedIn
  4. Filters to only new (unseen) jobs
  5. Sends email digest
  6. Persists seen jobs so duplicates are never emailed again
  7. Prunes old DB entries (>90 days)
"""

import sys
from datetime import datetime

from config import (
    MAX_JOBS_PER_EMAIL,
    SEND_EMPTY_DIGEST,
    log,
)
from emailer import send_digest, validate_email_config
from filters import Job
from sources import fetch_all_nepal_sites, fetch_linkedin
from storage import init_db, load_seen_ids, save_jobs, prune_old_jobs


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def search_all() -> list[Job]:
    """Run all sources, deduplicate, return combined Job list."""
    log.info("Starting job search across all sources…")

    fetchers = [
        ("Nepal Portals", fetch_all_nepal_sites),
        ("LinkedIn",      fetch_linkedin),
    ]

    raw: list[Job] = []
    for name, fn in fetchers:
        try:
            jobs = fn()
            raw.extend(jobs)
            log.info(f"{name}: {len(jobs)} jobs fetched")
        except Exception as e:
            log.error(f"{name}: unexpected top-level error: {e}")

    # Global dedup
    seen_ids: set[str] = set()
    unique: list[Job] = []
    for job in raw:
        if job.id not in seen_ids:
            seen_ids.add(job.id)
            unique.append(job)

    log.info(f"Total unique relevant jobs this run: {len(unique)}")
    return unique


def sort_jobs(jobs: list[Job]) -> list[Job]:
    """Butwal first, then Remote, sorted by score desc within each group."""
    order = {"Butwal Onsite": 0, "Nepal Remote": 1}
    return sorted(
        jobs,
        key=lambda j: (order.get(j.category, 9), -j.score, j.title.lower()),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=" * 60)
    log.info("Daily Job Monitor — Nepal + LinkedIn Edition")
    log.info("=" * 60)

    # Validate email config early
    missing = validate_email_config()
    if missing:
        log.error(f"Missing required env vars: {', '.join(missing)}")
        sys.exit(1)

    # Init DB
    init_db()

    # Prune stale entries (runs silently if nothing to prune)
    prune_old_jobs(days=90)

    # Load previously seen job IDs
    seen_ids = load_seen_ids()
    log.info(f"{len(seen_ids)} jobs already seen in previous runs")

    # Fetch
    all_jobs = search_all()

    # Filter to new only
    new_jobs = [j for j in all_jobs if j.id not in seen_ids]
    log.info(f"{len(new_jobs)} genuinely new jobs (not previously emailed)")

    # Sort and cap
    new_jobs = sort_jobs(new_jobs)
    if len(new_jobs) > MAX_JOBS_PER_EMAIL:
        log.info(f"Capping email at {MAX_JOBS_PER_EMAIL} (found {len(new_jobs)})")
        to_email = new_jobs[:MAX_JOBS_PER_EMAIL]
    else:
        to_email = new_jobs

    today = datetime.now().strftime("%Y-%m-%d")

    # Send email
    if not to_email and not SEND_EMPTY_DIGEST:
        log.info("No new jobs and SEND_EMPTY_DIGEST=False — skipping email.")
    else:
        try:
            send_digest(to_email, today)
        except Exception as e:
            log.error(f"Email send failed: {e}")
            log.error("Not updating seen-jobs DB so we retry tomorrow.")
            sys.exit(1)

    # Persist — only after successful send
    inserted = save_jobs(new_jobs)  # save ALL new, even those above the cap
    log.info(f"Saved {inserted} new job IDs to DB")
    log.info("Done. ✓")


if __name__ == "__main__":
    main()
