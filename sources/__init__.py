"""sources — job-fetching backends."""
from sources.nepal_sites import fetch_all_nepal_sites
from sources.linkedin import fetch_linkedin

__all__ = ["fetch_all_nepal_sites", "fetch_linkedin"]
