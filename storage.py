"""
storage.py — SQLite persistence.

Tracks every job ever seen so we only email genuinely new ones.
Uses WAL mode for safe concurrent access.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from config import DATABASE_PATH, log
from filters import Job


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS seen_jobs (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    link         TEXT NOT NULL,
    source       TEXT NOT NULL,
    category     TEXT NOT NULL,
    score        REAL NOT NULL DEFAULT 0,
    found_at     TEXT NOT NULL,
    emailed_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_seen_jobs_found_at ON seen_jobs (found_at);
"""


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

@contextmanager
def _conn(path: Path = DATABASE_PATH):
    con = sqlite3.connect(str(path))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db(path: Path = DATABASE_PATH) -> None:
    """Create tables if they don't exist."""
    with _conn(path) as con:
        con.executescript(_DDL)
    log.debug(f"Database ready at {path}")


def load_seen_ids(path: Path = DATABASE_PATH) -> set[str]:
    """Return the set of all job IDs previously stored."""
    with _conn(path) as con:
        rows = con.execute("SELECT id FROM seen_jobs").fetchall()
    return {r[0] for r in rows}


def save_jobs(jobs: list[Job], path: Path = DATABASE_PATH) -> int:
    """
    Insert jobs that are not already in the DB.
    Returns the number of rows actually inserted.
    """
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    with _conn(path) as con:
        for job in jobs:
            try:
                con.execute(
                    """
                    INSERT OR IGNORE INTO seen_jobs
                        (id, title, link, source, category, score, found_at, emailed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job.id,
                        job.title,
                        job.link,
                        job.source,
                        job.category,
                        job.score,
                        now,
                        now,   # mark as emailed immediately
                    ),
                )
                if con.execute(
                    "SELECT changes()"
                ).fetchone()[0]:
                    inserted += 1
            except sqlite3.Error as e:
                log.warning(f"DB insert error for {job.id}: {e}")
    return inserted


def prune_old_jobs(days: int = 90, path: Path = DATABASE_PATH) -> int:
    """Remove jobs older than `days` to keep the DB small."""
    with _conn(path) as con:
        cur = con.execute(
            """
            DELETE FROM seen_jobs
            WHERE found_at < datetime('now', ?)
            """,
            (f"-{days} days",),
        )
    pruned = cur.rowcount
    if pruned:
        log.info(f"Pruned {pruned} old jobs (> {days} days)")
    return pruned
