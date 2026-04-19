"""
filters.py — Scoring-based job classifier.

Location rules (strict):
  ✓ Onsite + Butwal signal           → "Butwal Onsite"
  ✓ Remote + Nepal signal            → "Nepal Remote"
  ✓ Nepal portal + no location info  → "Nepal — Verify Location"
  ✗ Worldwide remote                 → EXCLUDED
  ✗ LinkedIn + no Nepal/Butwal signal→ EXCLUDED
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from config import (
    ROLE_FAMILIES,
    EXCLUDE_TITLE,
    BUTWAL_SIGNALS,
    NEPAL_SIGNALS,
    REMOTE_SIGNALS,
    WORLDWIDE_SIGNALS,
    MIN_ROLE_SCORE,
    AMBIGUITY_PENALTY,
    log,
)
from utils import make_job_id, extract_company


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Job:
    id:               str
    title:            str
    company:          str
    link:             str
    snippet:          str
    source:           str
    category:         str           # "Butwal Onsite" | "Nepal Remote" | "Nepal — Verify Location"
    score:            float
    matched_family:   str           # which role family matched
    matched_keywords: list[str] = field(default_factory=list)
    remote:           bool = False
    location_raw:     str  = ""
    match_reason:     str  = ""     # human-readable reason shown in email


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lower(*parts: str) -> str:
    return " ".join(p.lower() for p in parts if p)


def _has(text: str, signals: list[str]) -> bool:
    return any(s in text for s in signals)


def _count_signals(text: str, signals: list[str]) -> int:
    return sum(1 for s in signals if s in text)


def _title_excluded(title: str) -> bool:
    padded = f" {title.lower()} "
    return _has(padded, EXCLUDE_TITLE)


# ---------------------------------------------------------------------------
# Role scoring
# ---------------------------------------------------------------------------

def _score_role(title: str, snippet: str) -> tuple[float, str, list[str]]:
    """
    Returns (score, best_family_name, matched_keywords).
    Title matches weight 3×, body matches 1×.
    Returns the family that produced the highest score.
    """
    title_l = f" {title.lower()} "
    full_l  = _lower(title, snippet)

    best_score  = 0.0
    best_family = ""
    all_matched: list[str] = []

    for family_name, family in ROLE_FAMILIES.items():
        w     = family["weight"]
        score = 0.0
        kws: list[str] = []

        for kw in family["title_kw"]:
            if kw in title_l:
                score += w * 3.0
                kws.append(kw)

        for kw in family["body_kw"]:
            if kw in full_l and kw not in kws:
                score += w * 1.0
                kws.append(kw)

        if score > best_score:
            best_score  = score
            best_family = family_name

        all_matched.extend(k for k in kws if k not in all_matched)

    return best_score, best_family, all_matched


# ---------------------------------------------------------------------------
# Location detection
# ---------------------------------------------------------------------------

@dataclass
class LocationResult:
    category:   str    # final bucket
    confidence: float  # 0–1
    remote:     bool
    location_raw: str


def _detect_location(
    title:        str,
    snippet:      str,
    nepal_source: bool,
) -> LocationResult:
    """
    Classifies job into a location bucket with confidence.
    nepal_source=True means the job came from a Nepal-specific portal.
    """
    text = _lower(title, snippet)

    is_worldwide = _has(text, WORLDWIDE_SIGNALS)
    is_remote    = _has(text, REMOTE_SIGNALS)
    is_butwal    = _has(text, BUTWAL_SIGNALS)
    is_nepal     = _has(text, NEPAL_SIGNALS) or nepal_source

    # Strongest location mention for display
    loc_raw = ""
    for sig in BUTWAL_SIGNALS:
        if sig in text:
            loc_raw = "Butwal"
            break
    if not loc_raw:
        for sig in NEPAL_SIGNALS:
            if sig in text:
                loc_raw = sig.title()
                break
    if not loc_raw and is_remote:
        loc_raw = "Remote"

    # Decision tree
    if is_worldwide:
        return LocationResult("EXCLUDED", 1.0, False, "worldwide")

    if is_butwal:
        return LocationResult("Butwal Onsite", 0.95, False, loc_raw)

    if is_remote and is_nepal:
        return LocationResult("Nepal Remote", 0.90, True, loc_raw or "Remote / Nepal")

    if is_remote and nepal_source:
        # Remote job on Nepal portal — almost certainly Nepal-eligible
        return LocationResult("Nepal Remote", 0.80, True, "Remote / Nepal")

    if is_remote and not is_nepal:
        # Remote but no Nepal signal and not from Nepal portal → exclude
        return LocationResult("EXCLUDED", 0.75, True, "remote / no Nepal signal")

    if nepal_source:
        # Onsite-ish job on Nepal portal, no city mentioned in card
        # Include it so Prativa can check the full listing
        return LocationResult("Nepal — Verify Location", 0.60, False, loc_raw or "Nepal (unverified)")

    # LinkedIn or unknown source with no clear location → exclude
    return LocationResult("EXCLUDED", 0.70, False, "ambiguous")


# ---------------------------------------------------------------------------
# Main classifier
# ---------------------------------------------------------------------------

def classify(
    title:        str,
    link:         str,
    snippet:      str,
    source:       str,
    nepal_source: bool = False,
) -> Optional[Job]:
    """
    Returns a Job if it passes all filters, None otherwise.
    """
    title   = title.strip()
    snippet = re.sub(r"\s+", " ", snippet.strip())[:500]

    if not title or not link:
        return None

    # Hard title exclusion
    if _title_excluded(title):
        return None

    # Role scoring
    score, family, matched = _score_role(title, snippet)
    if score < MIN_ROLE_SCORE:
        return None

    # Location classification
    loc = _detect_location(title, snippet, nepal_source)
    if loc.category == "EXCLUDED":
        return None

    # Build human-readable match reason
    kw_display = ", ".join(matched[:3])
    reason = f"Matched: {kw_display}" if kw_display else f"Role family: {family}"

    company = extract_company(snippet)

    return Job(
        id=make_job_id(link, title, company),
        title=title,
        company=company,
        link=link.strip(),
        snippet=snippet,
        source=source,
        category=loc.category,
        score=round(score, 2),
        matched_family=family,
        matched_keywords=matched,
        remote=loc.remote,
        location_raw=loc.location_raw,
        match_reason=reason,
    )
