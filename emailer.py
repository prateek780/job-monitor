"""
emailer.py — Build and send the daily job digest email.
"""

import html
import re
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS,
    EMAIL_FROM, EMAIL_TO, log,
)
from filters import Job

_SOURCE_NAMES: dict[str, str] = {
    "merojob.com":      "MeroJob",
    "jobsnepal.com":    "JobsNepal",
    "kumarijob.com":    "KumariJob",
    "jobejee.com":      "Jobejee",
    "kantipurjob.com":  "KantipurJob",
    "jobaxle.com":      "JobAxle",
    "merorojgari.com":  "MeroRojgari",
    "necojobs.com.np":  "NecoJobs",
    "ramrojob.com":     "RamroJob",
    "jobsdynamics.com": "Jobs Dynamics",
    "linkedin.com":     "LinkedIn",
}

CATEGORY_ORDER = ["Butwal Onsite", "Nepal Remote"]

CATEGORY_META: dict[str, dict] = {
    "Butwal Onsite": {"icon": "📍", "color": "#1d4ed8", "bg": "#dbeafe"},
    "Nepal Remote":  {"icon": "🌏", "color": "#065f46", "bg": "#d1fae5"},
}


def _friendly_source(raw: str) -> str:
    for key, label in _SOURCE_NAMES.items():
        if key in raw:
            return label
    return raw.title()


def _no_jobs_html(today: str) -> str:
    return f"""
<html><body style="font-family:-apple-system,Segoe UI,Arial,sans-serif;
color:#111;max-width:600px;margin:auto;padding:24px;">
<h2 style="color:#1d4ed8;">📋 Daily Job Digest — {today}</h2>
<p style="color:#6b7280;">
  No new matching jobs today.<br>
  We searched all Nepal portals + LinkedIn.<br>
  Check back tomorrow! 🌱
</p>
</body></html>
"""


def _job_card_html(job: Job) -> str:
    title   = html.escape(job.title)
    link    = html.escape(job.link, quote=True)
    snippet = html.escape(job.snippet)
    src     = html.escape(_friendly_source(job.source))
    kws     = ", ".join(html.escape(k) for k in job.matched_keywords[:3])
    loc     = html.escape(job.location_raw) if job.location_raw else ""

    loc_badge = (
        f' &nbsp;<span style="background:#fef9c3;color:#713f12;padding:1px 7px;'
        f'border-radius:99px;font-size:11px;">{loc}</span>'
        if loc else ""
    )
    kw_badge = (
        f' &nbsp;<span style="background:#d1fae5;color:#065f46;padding:1px 7px;'
        f'border-radius:99px;font-size:11px;">{kws}</span>'
        if kws else ""
    )
    li_badge = (
        ' &nbsp;<span style="background:#dbeafe;color:#1d4ed8;padding:1px 7px;'
        'border-radius:99px;font-size:11px;">LinkedIn</span>'
        if "linkedin" in job.source else ""
    )

    return (
        f'<div style="border-left:3px solid #3b82f6;padding:10px 14px;'
        f'margin:0 0 10px 0;background:#f9fafb;border-radius:0 6px 6px 0;">'
        f'<a href="{link}" style="font-weight:600;color:#1d4ed8;'
        f'text-decoration:none;font-size:14px;">{title}</a>'
        f'<div style="color:#6b7280;font-size:11px;margin-top:3px;">'
        f'{src}{li_badge}{loc_badge}{kw_badge}'
        f'</div>'
        f'<div style="color:#374151;font-size:12px;margin-top:5px;'
        f'line-height:1.55;">{snippet}</div>'
        f'</div>'
    )


def build_email_html(jobs: list[Job], today: str) -> str:
    if not jobs:
        return _no_jobs_html(today)

    grouped: dict[str, list[Job]] = {}
    for job in jobs:
        grouped.setdefault(job.category, []).append(job)

    for cat in grouped:
        grouped[cat].sort(key=lambda j: -j.score)

    total = len(jobs)
    parts = [
        '<html><body style="font-family:-apple-system,Segoe UI,Arial,sans-serif;'
        'color:#111;max-width:740px;margin:auto;padding:24px;background:#f3f4f6;">',
        '<div style="background:white;padding:28px;border-radius:10px;'
        'box-shadow:0 2px 8px rgba(0,0,0,0.08);">',
        '<h1 style="color:#1d4ed8;margin:0 0 4px 0;font-size:22px;">'
        '📋 Daily Job Digest — Prativa Khanal</h1>',
        f'<p style="color:#6b7280;margin:0 0 24px 0;font-size:13px;">'
        f'{today} &nbsp;·&nbsp; <strong>{total}</strong> new '
        f'job{"s" if total != 1 else ""} '
        f'(Butwal onsite &amp; Nepal remote)</p>',
    ]

    for category in CATEGORY_ORDER:
        cat_jobs = grouped.get(category, [])
        if not cat_jobs:
            continue
        meta = CATEGORY_META[category]
        n    = len(cat_jobs)
        parts.append(
            f'<h2 style="color:#111827;border-bottom:2px solid {meta["bg"]};'
            f'padding-bottom:6px;margin-top:28px;font-size:16px;">'
            f'{meta["icon"]} {html.escape(category)} '
            f'<span style="color:#9ca3af;font-weight:normal;font-size:12px;">'
            f'({n} job{"s" if n != 1 else ""})</span></h2>'
        )
        for job in cat_jobs:
            parts.append(_job_card_html(job))

    parts += [
        '<hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">',
        '<p style="color:#9ca3af;font-size:11px;text-align:center;">',
        'Daily Job Monitor &nbsp;·&nbsp; Nepal + LinkedIn',
        '</p></div></body></html>',
    ]
    return "".join(parts)


def send_digest(jobs: list[Job], today: str) -> None:
    subject   = f"Job Digest — {today} ({len(jobs)} new jobs)" if jobs else f"Job Digest — {today} (no new jobs)"
    html_body = build_email_html(jobs, today)
    plain     = re.sub(r"\n\s*\n", "\n\n", re.sub(r"<[^>]+>", "", html_body)).strip()

    msg            = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = ", ".join(EMAIL_TO)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    log.info(f"Sending digest to {', '.join(EMAIL_TO)} — {len(jobs)} jobs")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
    log.info("Email sent successfully.")


def validate_email_config() -> list[str]:
    missing = []
    if not SMTP_HOST: missing.append("SMTP_HOST")
    if not SMTP_USER: missing.append("SMTP_USER")
    if not SMTP_PASS: missing.append("SMTP_PASS")
    if not EMAIL_FROM: missing.append("EMAIL_FROM")
    if not EMAIL_TO: missing.append("EMAIL_TO")
    return missing