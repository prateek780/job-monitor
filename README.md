# Daily Job Monitor — Nepal + LinkedIn

Automated daily job digest for **Prativa Khanal** (Receptionist / Front Desk / Customer Support, based in Butwal, Nepal).

Searches 10 Nepal job portals and LinkedIn every day at **12:00 PM Nepal time** and emails only new, matching jobs.

---

## Strict Location Rules

| Job type | Included? |
|---|---|
| Onsite in **Butwal** | Yes— **Butwal Onsite** |
| Remote, Nepal-eligible |  Yes — **Nepal Remote** |
| Onsite outside Butwal (e.g. Kathmandu) | ❌ No |
| Worldwide remote |  No |
| Ambiguous location |  No (conservative) |

---

## Sources

| # | Portal | URL |
|---|---|---|
| 1 | MeroJob | https://merojob.com |
| 2 | JobsNepal | https://www.jobsnepal.com |
| 3 | KumariJob | https://kumarijob.com |
| 4 | Jobejee | https://www.jobejee.com |
| 5 | KantipurJob | https://kantipurjob.com |
| 6 | JobAxle | https://jobaxle.com |
| 7 | MeroRojgari | https://merorojgari.com |
| 8 | NecoJobs | https://www.necojobs.com.np |
| 9 | RamroJob | https://ramrojob.com |
| 10 | Jobs Dynamics | https://jobsdynamics.com |
| 11 | LinkedIn | Public guest API (no login) |

---

## Quick Start (local)

```bash
# 1. Clone / copy this project
# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment
cp .env.example .env
# Edit .env with your SMTP and email settings

# 4. Run
python main.py
```

> **Gmail users:** Use an [App Password](https://myaccount.google.com/apppasswords), not your main password. You must have 2FA enabled.

---

## GitHub Actions (automated daily run)

### 1. Add repository secrets

Go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret | Value |
|---|---|
| `SMTP_HOST` | e.g. `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | your Gmail address |
| `SMTP_PASS` | your Gmail App Password |
| `EMAIL_FROM` | your Gmail address |
| `EMAIL_TO` | recipient email |

### 2. Push the workflow file

The file `.github/workflows/daily_job_monitor.yml` is already included. Once pushed to GitHub, the workflow will run automatically every day at **12:00 PM Nepal time (06:15 UTC)**.

### 3. Test manually

Go to **Actions → Daily Job Monitor → Run workflow** to trigger a test run immediately.

---

## Project Structure

```
job_monitor/
├── main.py              # Entry point / orchestrator
├── config.py            # All constants, keywords, env loading
├── filters.py           # Job classification, location rules, scoring
├── storage.py           # SQLite persistence (seen-jobs DB)
├── emailer.py           # HTML email builder + SMTP sender
├── sources/
│   ├── __init__.py
│   ├── base.py          # Shared HTTP + retry utilities
│   ├── nepal_sites.py   # All 10 Nepal portals
│   └── linkedin.py      # LinkedIn public guest API
├── requirements.txt
├── .env.example
└── .github/
    └── workflows/
        └── daily_job_monitor.yml
```

---

## Customisation

### Add/remove role keywords
Edit `ROLE_KEYWORDS` in `config.py`.

### Add/remove excluded titles
Edit `EXCLUDE_TITLE_KEYWORDS` in `config.py`.

### Change email cap
Edit `MAX_JOBS_PER_EMAIL` in `config.py` (default: 80).

### Suppress no-news emails
Set `SEND_EMPTY_DIGEST=False` in `config.py`.

### Add a new Nepal portal
Add a `SiteConfig` entry to `NEPAL_SITES` in `sources/nepal_sites.py`.

---

## How Filtering Works

1. **Title exclusion** — hard rejects engineering/AI/tech roles
2. **Role scoring** — title match = 2 pts, snippet match = 1 pt; minimum 1 pt required
3. **Location gate** — strict rules applied (see table above)
4. **Deduplication** — by URL path hash; never emails the same job twice

---

## Logs

The monitor writes to `job_monitor.log` in the project root. In GitHub Actions this is visible in the workflow run output.
