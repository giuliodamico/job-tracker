"""Greenhouse: job board pubbliche delle aziende in companies.yaml (API senza autenticazione)."""

import logging
from functools import cache

from agents.sources import JobPosting, SourceError, get_json, html_to_text, parse_date, title_matches
from app.db import SearchProfile

BOARD_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"

log = logging.getLogger(__name__)


@cache
def _jobs(token: str) -> list[dict]:
    """Tutte le offerte di una board. In cache: con più profili la board si scarica una volta."""
    return get_json(BOARD_URL.format(token=token), {"content": "true"}).get("jobs", [])


def search(profile: SearchProfile, companies: dict) -> list[JobPosting]:
    """Offerte delle aziende Greenhouse con la keyword del profilo nel titolo."""
    postings = []
    for company in companies.get("greenhouse", []):
        try:
            jobs = _jobs(company["token"])
        except SourceError as exc:
            log.warning("Greenhouse, %s: %s", company["name"], exc)
            continue
        for job in jobs:
            if not title_matches(job["title"], profile.keyword):
                continue
            postings.append(
                JobPosting(
                    company=company["name"],
                    role=job["title"].strip(),
                    location=(job.get("location") or {}).get("name"),
                    # L'id dell'offerta può stare nella query (?gh_jid=...): l'URL va tenuto intero.
                    url=job["absolute_url"],
                    description=html_to_text(job.get("content")),
                    source="greenhouse",
                    posted_date=parse_date(job.get("first_published") or job.get("updated_at")),
                )
            )
    return postings
