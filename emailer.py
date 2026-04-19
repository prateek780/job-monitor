"""
emailer.py — Build and send the daily job digest email.

Each job card shows:
  title (linked) · company · location · source · match reason · score
"""

import html
import re
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS,
    EMAIL_FROM, EMAIL_TO, CATEGORY_ORDER, log,
)
from filters import Job
from utils import friendly_source


# ---------------------------------------------------------------------------
# Category display metadata
# ---------------------------------------------------------------------------

CATEGORY_META: dict[str, dict] = {
    "Butwal Onsite": {
        "icon":       "📍",
        "border":     "#3b82f6",
        "header_bg":  "#dbeafe",
        "header_txt": "#1e3a5f",
    },
    "Nepal Remote": {
        "icon":       "🌏",
        "border":     "#10b981",
        "header_bg":  "#d1fae5",
        "header_txt": "#064e3b",
    },
    "Nepal — Verify Location": {
        "icon":       "🔍",
        "border":     "#f59e0b",
        "header_bg":  "#fef3c7",
        "header_txt": "#78350f",
    },
}


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _score_bar(score: float) -> str:
    """Tiny visual score indicator (up to 5 dots)."""
    filled = min(5, max(1, round(score / 6)))
    return "●" * filled + "○" * (5 - filled)


def _job_card(job: Job) -> str:
    title       = html.escape(job.title)
    link        = html.escape(job.link, quote=True)
    snippet     = html.escape(job.snippet[:200])
    src         = html.escape(friendly_source(job.source))
    reason      = html.escape(job.match_reason)
    company     = html.escape(job.company) if job.company else ""
    loc         = html.escape(job.location_raw) if job.location_raw else ""
    score_dots  = _score_bar(job.score)

    company_line = f'<span style="color:#374151;">{company}</span> &nbsp;' if company else ""
    loc_badge = (
        f'<span style="background:#fef9c3;color:#78350f;padding:1px 7px;'
        f'border-radius:99px;font-size:11px;margin-left:4px;">{loc}</span>'
        if loc else ""
    )
    src_badge = (
        f'<span style="background:#e0e7ff;color:#3730a3;padding:1px 7px;'
        f'border-radius:99px;font-size:11px;margin-left:4px;">{src}</span>'
    )
    li_badge = (
        '<span style="background:#dbeafe;color:#1d4ed8;padding:1px 7px;'
        'border-radius:99px;font-size:11px;margin-left:4px;">LinkedIn</span>'
        if "linkedin" in job.source else ""
    )

    return (
        f'<div style="border-left:3px solid #3b82f6;padding:10px 14px;'
        f'margin:0 0 10px 0;background:#f9fafb;border-radius:0 6px 6px 0;">'
        # Title
        f'<div style="margin-bottom:4px;">'
        f'<a href="{link}" style="font-weight:600;color:#1d4ed8;'
        f'text-decoration:none;font-size:14px;">{title}</a>'
        f'</div>'
        # Company + location
        f'<div style="font-size:12px;color:#4b5563;margin-bottom:4px;">'
        f'{company_line}{loc_badge}{src_badge}{li_badge}'
        f'</div>'
        # Snippet
        f'<div style="color:#374151;font-size:12px;margin-bottom:5px;'
        f'line-height:1.55;">{snippet}</div>'
        # Reason + score
        f'<div style="font-size:11px;color:#6b7280;">'
        f'<em>{reason}</em> &nbsp; '
        f'<span title="Relevance score" style="color:#9ca3af;">{score_dots}</span>'
        f'</div>'
        f'</div>'
    )


def _no_jobs_html(today: str) -> str:
    return (
        f'<html><body style="font-family:-apple-system,Segoe UI,Arial,sans-serif;'
        f'color:#111;max-width:600px;margin:auto;padding:24px;">'
        f'<h2 style="color:#1d4ed8;">📋 Daily Job Digest — {today}</h2>'
        f'<p style="color:#6b7280;">'
        f'No new matching jobs found today.<br>'
        f'Searched 9 Nepal portals + LinkedIn.<br>'
        f'Check back tomorrow! 🌱'
        f'</p></body></html>'
    )


def build_email_html(jobs: list[Job], today: str) -> str:
    if not jobs:
        return _no_jobs_html(today)

    # Group and sort by score desc within each category
    grouped: dict[str, list[Job]] = {}
    for job in jobs:
        grouped.setdefault(job.category, []).append(job)
    for cat in grouped:
        grouped[cat].sort(key=lambda j: -j.score)

    total = len(jobs)
    parts = [
        '<html><body style="font-family:-apple-system,Segoe UI,Arial,sans-serif;'
        'color:#111;max-width:760px;margin:auto;padding:24px;background:#f3f4f6;">',
        '<div style="background:white;padding:28px;border-radius:12px;'
        'box-shadow:0 2px 10px rgba(0,0,0,0.08);">',

        # Header
        '<h1 style="color:#1d4ed8;margin:0 0 4px 0;font-size:22px;">'
        '📋 Daily Job Digest — Prativa Khanal</h1>',
        f'<p style="color:#6b7280;margin:0 0 8px 0;font-size:13px;">'
        f'{today} &nbsp;·&nbsp; <strong>{total}</strong> new '
        f'job{"s" if total != 1 else ""} found</p>',

        # Category summary pills
        '<div style="margin-bottom:20px;">',
    ]

    for cat in CATEGORY_ORDER:
        n    = len(grouped.get(cat, []))
        meta = CATEGORY_META.get(cat, {})
        if n:
            bg  = meta.get("header_bg", "#f3f4f6")
            txt = meta.get("header_txt", "#111")
            ico = meta.get("icon", "•")
            parts.append(
                f'<span style="background:{bg};color:{txt};padding:3px 10px;'
                f'border-radius:99px;font-size:12px;margin-right:6px;">'
                f'{ico} {html.escape(cat)}: {n}'
                f'</span>'
            )

    parts.append('</div>')

    # Job sections
    for cat in CATEGORY_ORDER:
        cat_jobs = grouped.get(cat, [])
        if not cat_jobs:
            continue
        meta = CATEGORY_META.get(cat, {})
        n    = len(cat_jobs)
        ico  = meta.get("icon", "•")
        bg   = meta.get("header_bg", "#f3f4f6")
        txt  = meta.get("header_txt", "#111827")

        parts.append(
            f'<div style="background:{bg};padding:10px 14px;'
            f'border-radius:6px;margin:20px 0 10px 0;">'
            f'<h2 style="color:{txt};margin:0;font-size:16px;">'
            f'{ico} {html.escape(cat)} '
            f'<span style="color:#9ca3af;font-weight:normal;font-size:12px;">'
            f'({n} job{"s" if n != 1 else ""})</span>'
            f'</h2></div>'
        )

        if cat == "Nepal — Verify Location":
            parts.append(
                '<p style="color:#92400e;font-size:12px;margin:0 0 10px 0;">'
                '⚠️ Location not specified in listing — click through to verify '
                'it is in Butwal or genuinely remote before applying.'
                '</p>'
            )

        for job in cat_jobs:
            parts.append(_job_card(job))

    parts += [
        '<hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">',
        '<p style="color:#9ca3af;font-size:11px;text-align:center;">',
        'Daily Job Monitor &nbsp;·&nbsp; Nepal + LinkedIn Edition',
        '</p></div></body></html>',
    ]
    return "".join(parts)


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------

def send_digest(jobs: list[Job], today: str) -> None:
    n         = len(jobs)
    subject   = (
        f"Job Digest — {today} ({n} new job{'s' if n != 1 else ''})"
        if n else f"Job Digest — {today} (no new jobs)"
    )
    html_body = build_email_html(jobs, today)
    plain     = re.sub(r"\n\s*\n", "\n\n", re.sub(r"<[^>]+>", "", html_body)).strip()

    msg            = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = ", ".join(EMAIL_TO)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    log.info(f"Sending digest to {', '.join(EMAIL_TO)} ({n} jobs)")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
    log.info("Email sent.")


def validate_email_config() -> list[str]:
    missing = []
    if not SMTP_HOST:  missing.append("SMTP_HOST")
    if not SMTP_USER:  missing.append("SMTP_USER")
    if not SMTP_PASS:  missing.append("SMTP_PASS")
    if not EMAIL_FROM: missing.append("EMAIL_FROM")
    if not EMAIL_TO:   missing.append("EMAIL_TO")
    return missing
