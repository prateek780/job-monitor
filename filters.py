"""
filters.py — Job classification with strict location rules.

Inclusion logic:
  ✓ Onsite + Butwal             → "Butwal Onsite"
  ✓ Remote + Nepal              → "Nepal Remote"
  ✓ Nepal portal + no location  → "Nepal — Verify Location"
  ✗ Remote + Worldwide          → EXCLUDED
  ✗ LinkedIn + no Nepal signal  → EXCLUDED
"""

import re
import hashlib
from dataclasses import dataclass, field
from typing import Optional

from config import (
    ROLE_KEYWORDS,
    EXCLUDE_TITLE_KEYWORDS,
    BUTWAL_TERMS,
    NEPAL_TERMS,
    REMOTE_TERMS,
    WORLDWIDE_TERMS,
)


@dataclass
class Job:
    id:               str
    title:            str
    link:             str
    snippet:          str
    source:           str
    category:         str
    score:            float
    matched_keywords: list[str] = field(default_factory=list)
    remote:           bool = False
    location_raw:     str  = ""


def make_job_id(link: str, title: str) -> str:
    from urllib.parse import urlparse
    if link:
        p = urlparse(link.strip().lower())
        key = f"{p.netloc}{p.path}".rstrip("/")
    else:
        key = re.sub(r"\s+", " ", title.lower().strip())
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def _lower(*parts: str) -> str:
    return " ".join(p.lower() for p in parts if p)


def _has(text: str, terms: list[str]) -> bool:
    return any(t in text for t in terms)


def _detect_remote(title: str, snippet: str) -> bool:
    return _has(_lower(title, snippet), REMOTE_TERMS)


def _detect_worldwide(title: str, snippet: str) -> bool:
    return _has(_lower(title, snippet), WORLDWIDE_TERMS)


def _detect_butwal(title: str, snippet: str) -> bool:
    return _has(_lower(title, snippet), BUTWAL_TERMS)


def _detect_nepal(title: str, snippet: str) -> bool:
    return _has(_lower(title, snippet), NEPAL_TERMS)


def _role_score(title: str, snippet: str) -> tuple[float, list[str]]:
    title_text = _lower(title)
    full_text  = _lower(title, snippet)
    score      = 0.0
    matched: list[str] = []

    for kw in ROLE_KEYWORDS:
        if kw in title_text:
            score += 2.0
            if kw not in matched:
                matched.append(kw)
        elif kw in full_text:
            score += 1.0
            if kw not in matched:
                matched.append(kw)

    return score, matched


def _title_excluded(title: str) -> bool:
    padded = f" {title.lower()} "
    return _has(padded, EXCLUDE_TITLE_KEYWORDS)


def _best_location_string(title: str, snippet: str) -> str:
    text = _lower(title, snippet)
    for t in BUTWAL_TERMS:
        if t in text:
            return "Butwal"
    if _has(text, REMOTE_TERMS):
        return "Remote / Nepal"
    for t in NEPAL_TERMS:
        if t in text:
            return t.title()
    return ""


def classify(
    title:        str,
    link:         str,
    snippet:      str,
    source:       str,
    nepal_source: bool = False,
) -> Optional[Job]:
    title   = title.strip()
    snippet = re.sub(r"\s+", " ", snippet.strip())[:400]

    if not title or not link:
        return None

    if _title_excluded(title):
        return None

    score, matched = _role_score(title, snippet)
    if score < 1.0:
        return None

    is_remote    = _detect_remote(title, snippet)
    is_worldwide = _detect_worldwide(title, snippet)
    is_butwal    = _detect_butwal(title, snippet)
    is_nepal     = _detect_nepal(title, snippet) or nepal_source

    # -----------------------------------------------------------------------
    # Location gate
    # -----------------------------------------------------------------------
    if is_worldwide:
        return None                        # worldwide → always reject

    if is_remote:
        if is_nepal:
            category = "Nepal Remote"
        else:
            return None                    # remote but no Nepal signal → reject

    elif is_butwal:
        category = "Butwal Onsite"

    elif nepal_source:
        # Nepal-specific portal but no location in card text.
        # Include so Prativa gets the lead — verify location before applying.
        category = "Nepal — Verify Location"

    else:
        return None                        # LinkedIn with no clear location → reject

    return Job(
        id=make_job_id(link, title),
        title=title,
        link=link.strip(),
        snippet=snippet,
        source=source,
        category=category,
        score=score,
        matched_keywords=matched,
        remote=is_remote,
        location_raw=_best_location_string(title, snippet),
    )
