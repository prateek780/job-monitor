"""
utils.py — Shared text utilities: normalization, fuzzy dedup, company extraction.
"""

import re
import hashlib
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    t = text.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def normalize_title(title: str) -> str:
    """Normalize job title for deduplication purposes."""
    t = normalize_text(title)
    # Remove common noise words that vary between postings of the same job
    noise = r"\b(urgently|urgently hiring|hiring|now|immediate|immediately|opening|vacancy|position|job|role|opportunity|required|needed|wanted)\b"
    t = re.sub(noise, "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def word_set(text: str) -> set[str]:
    return set(normalize_text(text).split())


def jaccard(a: str, b: str) -> float:
    """Jaccard similarity between two strings (by word sets)."""
    sa, sb = word_set(a), word_set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def is_fuzzy_duplicate(title_a: str, title_b: str, threshold: float = 0.75) -> bool:
    """True if two job titles are likely the same posting."""
    return jaccard(normalize_title(title_a), normalize_title(title_b)) >= threshold


# ---------------------------------------------------------------------------
# Job ID — stable hash for deduplication
# ---------------------------------------------------------------------------

def make_job_id(link: str, title: str, company: str = "") -> str:
    """
    Primary key: SHA-1 of normalized URL path.
    Fallback: SHA-1 of (normalized title + company).
    """
    if link:
        p   = urlparse(link.strip().lower())
        key = f"{p.netloc}{p.path}".rstrip("/")
    else:
        key = normalize_title(title) + "|" + normalize_text(company)
    return hashlib.sha1(key.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Company extraction
# ---------------------------------------------------------------------------

_COMPANY_PATTERNS = [
    # "CompanyName · Location"   (LinkedIn style)
    re.compile(r"^(.+?)\s*[·•|]\s*", re.IGNORECASE),
    # "at CompanyName"
    re.compile(r"\bat\s+([A-Z][^,\n·•|]{2,40})", re.IGNORECASE),
    # "Company: CompanyName"
    re.compile(r"company[:\s]+([^,\n·•|]{2,40})", re.IGNORECASE),
]

def extract_company(snippet: str) -> str:
    """Best-effort company name extraction from a job card snippet."""
    for pat in _COMPANY_PATTERNS:
        m = pat.search(snippet.strip())
        if m:
            candidate = m.group(1).strip()
            # Reject if it looks like a job title or generic word
            if len(candidate) > 2 and not any(
                w in candidate.lower()
                for w in ("job", "vacancy", "hiring", "apply", "http", "www")
            ):
                return candidate[:60]
    return ""


# ---------------------------------------------------------------------------
# Source display name
# ---------------------------------------------------------------------------

_SOURCE_DISPLAY: dict[str, str] = {
    "merojob.com":      "MeroJob",
    "jobsnepal.com":    "JobsNepal",
    "kumarijob.com":    "KumariJob",
    "jobejee.com":      "Jobejee",
    "kantipurjob.com":  "KantipurJob",
    "jobaxle.com":      "JobAxle",
    "merorojgari.com":  "MeroRojgari",
    "necojobs.com.np":  "NecoJobs",
    "jobsdynamics.com": "Jobs Dynamics",
    "linkedin.com":     "LinkedIn",
}

def friendly_source(raw: str) -> str:
    for key, label in _SOURCE_DISPLAY.items():
        if key in raw:
            return label
    return raw.title()
