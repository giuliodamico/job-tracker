"""Adzuna: API ufficiale di ricerca offerte (https://developer.adzuna.com), mercato italiano."""

import os

from agents.sources import JobPosting, get_json, html_to_text, parse_date
from app.db import SearchProfile

SEARCH_URL = "https://api.adzuna.com/v1/api/jobs/it/search/1"
# Lo scout salta la fonte, con un avviso, se queste variabili mancano.
REQUIRED_ENV = ("ADZUNA_APP_ID", "ADZUNA_APP_KEY")


def search(profile: SearchProfile, companies: dict) -> list[JobPosting]:
    """Le 50 offerte più recenti per keyword e località del profilo (companies non serve qui)."""
    params = {
        "app_id": os.environ["ADZUNA_APP_ID"],
        "app_key": os.environ["ADZUNA_APP_KEY"],
        "what": profile.keyword,
        "results_per_page": 50,
        "sort_by": "date",
        "content-type": "application/json",
    }
    if profile.location:
        params["where"] = profile.location

    data = get_json(SEARCH_URL, params)
    return [
        JobPosting(
            company=(job.get("company") or {}).get("display_name") or "Azienda non indicata",
            role=html_to_text(job.get("title")),
            location=(job.get("location") or {}).get("display_name"),
            # redirect_url ha parametri di tracking legati all'account: senza query string
            # l'URL resta lo stesso da una ricerca all'altra, e la deduplica funziona.
            url=job["redirect_url"].split("?", 1)[0],
            description=html_to_text(job.get("description")),
            source="adzuna",
            posted_date=parse_date(job.get("created")),
        )
        for job in data.get("results", [])
        if job.get("redirect_url")
    ]
