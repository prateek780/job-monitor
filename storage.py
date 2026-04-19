"""
storage.py — SQLite persistence.

Tables:
  jobs          — every job ever seen
  runs          — one row per daily run
  source_health — tracks per-source success/failure
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import DATABASE_PATH, log
from filters import Job


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS jobs (
    id               TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    company          TEXT NOT NULL DEFAULT '',
    link             TEXT NOT NULL,
    source           TEXT NOT NULL,
    category         TEXT NOT NULL,
    score            REAL NOT NULL DEFAULT 0,
    matched_family   TEXT NOT NULL DEFAULT '',
    matched_keywords TEXT NOT NULL DEFAULT '[]',
    location_raw     TEXT NOT NULL DEFAULT '',
    remote           INTEGER NOT NULL DEFAULT 0,
    match_reason     TEXT NOT NULL DEFAULT '',
    first_seen       TEXT NOT NULL,
    last_seen        TEXT NOT NULL,
    emailed          INTEGER NOT NULL DEFAULT 0,
    emailed_at       TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs (first_seen);
CREATE INDEX IF NOT EXISTS idx_jobs_emailed    ON jobs (emailed);

CREATE TABLE IF NOT EXISTS runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at       TEXT NOT NULL,
    finished_at      TEXT,
    jobs_found       INTEGER DEFAULT 0,
    jobs_new         INTEGER DEFAULT 0,
    jobs_emailed     INTEGER DEFAULT 0,
    sources_ok       TEXT DEFAULT '[]',
    sources_failed   TEXT DEFAULT '[]',
    status           TEXT DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS source_health (
    source               TEXT PRIMARY KEY,
    last_success         TEXT,
    last_failure         TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    total_jobs_found     INTEGER NOT NULL DEFAULT 0
);
"""


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

@contextmanager
def _conn(path: Path = DATABASE_PATH):
    con = sqlite3.connect(str(path), timeout=15)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

def init_db(path: Path = DATABASE_PATH) -> None:
    with _conn(path) as con:
        con.executescript(_DDL)
    log.debug(f"Database initialised at {path}")


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def load_seen_ids(path: Path = DATABASE_PATH) -> set[str]:
    with _conn(path) as con:
        rows = con.execute("SELECT id FROM jobs").fetchall()
    return {r["id"] for r in rows}


def save_jobs(jobs: list[Job], path: Path = DATABASE_PATH) -> int:
    """Insert new jobs; update last_seen for already-known ones. Returns # inserted."""
    now      = datetime.now(timezone.utc).isoformat()
    inserted = 0

    with _conn(path) as con:
        for job in jobs:
            kw_json = json.dumps(job.matched_keywords)
            try:
                con.execute(
                    """
                    INSERT INTO jobs (
                        id, title, company, link, source, category,
                        score, matched_family, matched_keywords,
                        location_raw, remote, match_reason,
                        first_seen, last_seen, emailed, emailed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        job.id, job.title, job.company, job.link,
                        job.source, job.category, job.score,
                        job.matched_family, kw_json,
                        job.location_raw, int(job.remote),
                        job.match_reason, now, now, now,
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                # Already exists — update last_seen
                con.execute(
                    "UPDATE jobs SET last_seen = ? WHERE id = ?",
                    (now, job.id),
                )

    return inserted


def prune_old_jobs(days: int = 90, path: Path = DATABASE_PATH) -> int:
    with _conn(path) as con:
        cur = con.execute(
            "DELETE FROM jobs WHERE first_seen < datetime('now', ?)",
            (f"-{days} days",),
        )
    pruned = cur.rowcount
    if pruned:
        log.info(f"Pruned {pruned} jobs older than {days} days")
    return pruned


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def start_run(path: Path = DATABASE_PATH) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _conn(path) as con:
        cur = con.execute(
            "INSERT INTO runs (started_at, status) VALUES (?, 'running')",
            (now,),
        )
        return cur.lastrowid


def finish_run(
    run_id:         int,
    jobs_found:     int,
    jobs_new:       int,
    jobs_emailed:   int,
    sources_ok:     list[str],
    sources_failed: list[str],
    status:         str = "ok",
    path:           Path = DATABASE_PATH,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _conn(path) as con:
        con.execute(
            """
            UPDATE runs SET
                finished_at = ?, jobs_found = ?, jobs_new = ?,
                jobs_emailed = ?, sources_ok = ?, sources_failed = ?,
                status = ?
            WHERE id = ?
            """,
            (
                now, jobs_found, jobs_new, jobs_emailed,
                json.dumps(sources_ok), json.dumps(sources_failed),
                status, run_id,
            ),
        )


# ---------------------------------------------------------------------------
# Source health
# ---------------------------------------------------------------------------

def record_source_success(source: str, jobs_found: int, path: Path = DATABASE_PATH) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _conn(path) as con:
        con.execute(
            """
            INSERT INTO source_health (source, last_success, consecutive_failures, total_jobs_found)
            VALUES (?, ?, 0, ?)
            ON CONFLICT(source) DO UPDATE SET
                last_success = excluded.last_success,
                consecutive_failures = 0,
                total_jobs_found = total_jobs_found + excluded.total_jobs_found
            """,
            (source, now, jobs_found),
        )


def record_source_failure(source: str, path: Path = DATABASE_PATH) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _conn(path) as con:
        con.execute(
            """
            INSERT INTO source_health (source, last_failure, consecutive_failures, total_jobs_found)
            VALUES (?, ?, 1, 0)
            ON CONFLICT(source) DO UPDATE SET
                last_failure = excluded.last_failure,
                consecutive_failures = consecutive_failures + 1
            """,
            (source, now),
        )
