"""
config.py — All configuration, keyword lists, scoring weights, and env loading.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Secrets / environment
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
REQUEST_TIMEOUT    = 28
SCRAPE_DELAY       = 2.0        # between requests to the same site
LINKEDIN_DELAY     = 3.5        # LinkedIn rate-limits hard
MAX_RETRIES        = 3
RETRY_BACKOFF      = 5          # seconds, doubles each retry
SESSION_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection":      "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# ---------------------------------------------------------------------------
# Role families — drives both search queries and scoring
# ---------------------------------------------------------------------------
# Each family has:
#   title_kw  : keywords matched in the job TITLE  (weight × 3)
#   body_kw   : keywords matched anywhere in text  (weight × 1)
#   weight    : base multiplier for this family
# ---------------------------------------------------------------------------
ROLE_FAMILIES: dict[str, dict] = {
    "customer_service": {
        "title_kw": [
            "customer service", "customer support", "client service",
            "service representative", "service agent", "client support",
            "customer care", "customer relations", "client relations",
            "customer success", "customer experience",
        ],
        "body_kw": [
            "customer service", "customer support", "client service",
            "handle customer", "resolve customer", "customer queries",
            "customer complaints",
        ],
        "weight": 3.0,
    },
    "reception": {
        "title_kw": [
            "receptionist", "front desk", "front office", "guest relations",
            "guest service", "lobby", "welcome desk",
        ],
        "body_kw": [
            "receptionist", "front desk", "front office", "greet visitors",
            "answer calls", "manage calls",
        ],
        "weight": 3.0,
    },
    "admin": {
        "title_kw": [
            "administrative assistant", "admin assistant", "office assistant",
            "office administrator", "office admin", "office coordinator",
            "executive assistant", "personal assistant", "operations assistant",
            "secretary", "coordinator", "office manager",
        ],
        "body_kw": [
            "administrative", "office support", "scheduling", "calendar management",
            "filing", "correspondence", "office duties", "clerical",
        ],
        "weight": 2.5,
    },
    "call_center": {
        "title_kw": [
            "call center", "call centre", "contact center", "inbound agent",
            "outbound agent", "bpo", "help desk", "helpdesk",
            "support representative", "support specialist", "support agent",
            "technical support representative",
        ],
        "body_kw": [
            "call center", "contact center", "inbound calls", "outbound calls",
            "help desk", "ticket resolution", "bpo",
        ],
        "weight": 2.5,
    },
    "data_entry": {
        "title_kw": [
            "data entry", "data entry operator", "data entry clerk",
            "data entry executive", "data processor", "form filling",
            "data management",
        ],
        "body_kw": [
            "data entry", "data input", "typing speed", "accurate data",
            "ms excel", "spreadsheet entry",
        ],
        "weight": 2.0,
    },
    "finance_admin": {
        "title_kw": [
            "accounts assistant", "accounts executive", "accounts officer",
            "billing coordinator", "billing executive", "cashier",
            "teller", "bookkeeper", "bookkeeping",
            "junior accountant", "accounting assistant",
        ],
        "body_kw": [
            "accounts payable", "accounts receivable", "billing", "invoicing",
            "cash handling", "tally", "bookkeeping", "cashier",
        ],
        "weight": 2.0,
    },
    "sales_support": {
        "title_kw": [
            "sales support", "sales coordinator", "sales executive",
            "sales assistant", "inside sales", "sales representative",
            "telesales", "sales officer",
        ],
        "body_kw": [
            "sales support", "sales coordination", "lead generation",
            "sales targets", "sales pipeline",
        ],
        "weight": 2.0,
    },
    "social_media": {
        "title_kw": [
            "social media assistant", "social media coordinator",
            "social media executive", "social media support",
            "digital marketing assistant", "content assistant",
            "community manager",
        ],
        "body_kw": [
            "social media", "facebook", "instagram", "tiktok", "content creation",
            "social media management", "community management",
        ],
        "weight": 2.0,
    },
    "general_admin": {
        "title_kw": [
            "clerk", "office clerk", "general clerk", "store keeper",
            "record keeper", "documentation officer",
        ],
        "body_kw": [
            "filing", "record keeping", "documentation", "general office",
        ],
        "weight": 1.5,
    },
}

# Flat lists derived from families — used for quick checks
ALL_TITLE_KEYWORDS: list[str] = [
    kw for fam in ROLE_FAMILIES.values() for kw in fam["title_kw"]
]
ALL_BODY_KEYWORDS: list[str] = [
    kw for fam in ROLE_FAMILIES.values() for kw in fam["body_kw"]
]

# ---------------------------------------------------------------------------
# Hard exclusions — job rejected if title contains ANY of these
# ---------------------------------------------------------------------------
EXCLUDE_TITLE: list[str] = [
    "machine learning", "artificial intelligence", " ai ", "ai/ml", "ai engineer",
    "ml engineer", "data scientist", "deep learning", "software engineer",
    "software developer", "full stack", "fullstack", "frontend engineer",
    "backend engineer", "devops", "cloud engineer", "cybersecurity",
    "blockchain", "web3", "python developer", "java developer",
    "react developer", "node developer", "android developer", "ios developer",
    "network engineer", "system administrator", "database administrator",
    "nlp engineer", "computer vision", "research scientist", "quantitative analyst",
    "robotics", "firmware engineer", "embedded engineer", "site reliability",
    "infrastructure engineer", "sap consultant", "oracle developer",
    "erp consultant", "it manager", "it director", "cto", "chief technology",
    "data engineer", "analytics engineer", "bi developer", "etl developer",
    "qa engineer", "test engineer", "automation engineer",
]

# ---------------------------------------------------------------------------
# Location signals
# ---------------------------------------------------------------------------
BUTWAL_SIGNALS: list[str] = [
    "butwal", "rupandehi", "lumbini province", "lumbini pradesh",
    "lumbini zone",
]

NEPAL_SIGNALS: list[str] = [
    "nepal", "kathmandu", "pokhara", "lalitpur", "bhaktapur", "biratnagar",
    "chitwan", "birgunj", "dharan", "hetauda", "nepalgunj", "itahari",
    "lumbini", "bharatpur", "narayanghat", "bagmati", "gandaki",
    "koshi", "madhesh", "sudurpashchim",
]

REMOTE_SIGNALS: list[str] = [
    "remote", "work from home", "wfh", "home-based", "home based",
    "virtual", "telecommute", "anywhere in nepal", "nepal remote",
    "work remotely", "remote position", "remote job", "remote work",
    "remote opportunity", "fully remote", "100% remote",
]

# Presence of ANY of these = worldwide = REJECT
WORLDWIDE_SIGNALS: list[str] = [
    "worldwide", "global remote", "anywhere in the world",
    "open to all countries", "any country", "any location worldwide",
    "us only", "uk only", "eu only", "canada only", "australia only",
    "india only", "singapore only", "work from anywhere",
    "open to candidates globally",
]

# ---------------------------------------------------------------------------
# Scoring thresholds
# ---------------------------------------------------------------------------
MIN_ROLE_SCORE     = 1.5    # minimum to even consider the job
AMBIGUITY_PENALTY  = 0.5    # subtracted when location is ambiguous

# ---------------------------------------------------------------------------
# Search terms — used across Nepal scrapers
# Grouped for targeted queries, flattened for looping
# ---------------------------------------------------------------------------
SEARCH_TERMS: list[str] = [
    # Core roles
    "customer service",
    "customer support",
    "receptionist",
    "front desk",
    "front office",
    # Admin
    "administrative assistant",
    "admin assistant",
    "office assistant",
    "office coordinator",
    "secretary",
    "coordinator",
    # Operations
    "data entry",
    "data entry operator",
    "call center",
    "help desk",
    # Finance
    "accounts assistant",
    "cashier",
    "billing",
    "bookkeeping",
    "teller",
    # Sales / social
    "sales coordinator",
    "sales support",
    "social media assistant",
    "social media coordinator",
    # General
    "clerk",
    "bpo",
    "back office",
]

# ---------------------------------------------------------------------------
# LinkedIn-specific config
# ---------------------------------------------------------------------------
LINKEDIN_KEYWORDS: list[str] = [
    "receptionist", "customer service", "front desk", "admin assistant",
    "data entry", "call center", "office assistant", "cashier",
    "accounts assistant", "sales coordinator", "customer support",
    "social media coordinator", "bookkeeping", "secretary",
    "billing coordinator", "bpo", "back office",
    "administrative assistant", "help desk", "teller",
    "office coordinator", "accounts executive",
]

LINKEDIN_LOCATIONS: list[tuple[str, str]] = [
    ("Butwal, Lumbini Province, Nepal", "Butwal"),
    ("Nepal",                            "Nepal"),
    ("Remote",                           "Remote"),
]

LINKEDIN_PAGE_OFFSETS: list[int] = [0, 25, 50]   # paginate 3 pages per query

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
MAX_JOBS_PER_EMAIL = 100
SEND_EMPTY_DIGEST  = True
CATEGORY_ORDER     = ["Butwal Onsite", "Nepal Remote", "Nepal — Verify Location"]

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
