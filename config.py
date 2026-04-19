"""
config.py — All constants, keyword lists, and environment loading.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Environment / secrets
# ---------------------------------------------------------------------------
SMTP_HOST  = os.getenv("SMTP_HOST", "")
SMTP_PORT  = int(os.getenv("SMTP_PORT") or "587")
SMTP_USER  = os.getenv("SMTP_USER", "")
SMTP_PASS  = os.getenv("SMTP_PASS", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "")
EMAIL_TO   = [e.strip() for e in os.getenv("EMAIL_TO", "").split(",") if e.strip()]

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "jobs.db"))
LOG_LEVEL     = os.getenv("LOG_LEVEL", "INFO").upper()

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT = 25
SCRAPE_DELAY    = 2.0
MAX_RETRIES     = 3
RETRY_BACKOFF   = 4

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# ---------------------------------------------------------------------------
# Role keywords — positive signals
# ---------------------------------------------------------------------------
ROLE_KEYWORDS: list[str] = [
    "customer support",
    "customer service",
    "receptionist",
    "front desk",
    "client relations",
    "sales support",
    "administrative assistant",
    "admin assistant",
    "office assistant",
    "office admin",
    "social media assistant",
    "social media support",
    "call center",
    "data entry",
    "bookkeeping",
    "cashier",
    "help desk",
    "support representative",
    "support specialist",
    "service representative",
    "account coordinator",
    "operations assistant",
    "teller",
    "secretary",
    "coordinator",
    "billing",
    "accounts",
    "clerk",
]

# ---------------------------------------------------------------------------
# Exclude — jobs whose *title* matches any of these are rejected outright
# ---------------------------------------------------------------------------
EXCLUDE_TITLE_KEYWORDS: list[str] = [
    "machine learning", "artificial intelligence", " ai ", "ai/ml",
    "ml engineer", "data scientist", "deep learning", "software engineer",
    "software developer", "full stack", "fullstack", "frontend engineer",
    "backend engineer", "devops", "cloud engineer", "cybersecurity",
    "blockchain", "web3", "python developer", "java developer",
    "react developer", "node developer", "android developer", "ios developer",
    "network engineer", "system administrator", "database administrator",
    "nlp engineer", "computer vision", "research scientist", "quantitative",
    "robotics", "firmware", "embedded", "site reliability",
    "infrastructure engineer", "it support engineer", "erp",
    "sap consultant", "oracle developer",
]

# ---------------------------------------------------------------------------
# Location signals
# ---------------------------------------------------------------------------
BUTWAL_TERMS: list[str] = [
    "butwal", "rupandehi", "lumbini province", "lumbini pradesh",
]

NEPAL_TERMS: list[str] = [
    "nepal", "kathmandu", "pokhara", "lalitpur", "bhaktapur", "biratnagar",
    "chitwan", "birgunj", "dharan", "hetauda", "nepalgunj", "itahari",
    "lumbini", "bharatpur", "narayanghat", "bagmati", "gandaki",
]

REMOTE_TERMS: list[str] = [
    "remote", "work from home", "wfh", "home-based", "home based",
    "virtual", "telecommute", "anywhere in nepal",
]

WORLDWIDE_TERMS: list[str] = [
    "worldwide", "global remote", "anywhere in the world",
    "open to all countries", "any country", "any location",
    "us only", "uk only", "eu only", "canada only",
    "australia only", "india only", "singapore only",
]

# ---------------------------------------------------------------------------
# Search terms used across all Nepal scrapers
# ---------------------------------------------------------------------------
SEARCH_TERMS: list[str] = [
    "customer service",
    "receptionist",
    "front desk",
    "data entry",
    "admin assistant",
    "cashier",
    "secretary",
    "office assistant",
    "call center",
    "accounts",
    "coordinator",
    "billing",
    "bookkeeping",
    "clerk",
    "teller",
]

# ---------------------------------------------------------------------------
# Email / digest
# ---------------------------------------------------------------------------
MAX_JOBS_PER_EMAIL = 80
SEND_EMPTY_DIGEST  = True

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("job_monitor.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("job-monitor")
