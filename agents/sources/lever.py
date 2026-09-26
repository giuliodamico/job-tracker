"""Lever: job board pubbliche delle aziende in companies.yaml (API senza autenticazione)."""

import logging
from datetime import date, datetime, timezone
from functools import cache

from agents.sources import JobPosting, SourceError, get_json, html_to_text, title_matches
from app.db import SearchProfile

POSTINGS_URL = "https://api.lever.co/v0/postings/{token}"

log = logging.getLogger(__name__)


@cache
def _postings(token: str) -> list[dict]:
    """Tutte le offerte di una board. In cache: con più profili la board si scarica una volta."""
    return get_json(POSTINGS_URL.format(token=token), {"mode": "json"})


def search(profile: SearchProfile, companies: dict) -> list[JobPosting]:
    """Offerte delle aziende Lever con la keyword del profilo nel titolo."""
    postings = []
    for company in companies.get("lever", []):
        try:
            items = _postings(company["token"])
        except SourceError as exc:
            log.warning("Lever, %s: %s", company["name"], exc)
            continue
        for item in items:
            if not title_matches(item["text"], profile.keyword):
                continue
            postings.append(
                JobPosting(
                    company=company["name"],
                    role=item["text"].strip(),
                    location=_location(item),
                    url=item["hostedUrl"],
                    description=_description(item),
                    source="lever",
                    posted_date=_posted_date(item.get("createdAt")),
                )
            )
    return postings


def _location(item: dict) -> str | None:
    """Sedi dell'offerta più la modalità di lavoro, es. "London, Stockholm · hybrid"."""
    categories = item.get("categories") or {}
    places = ", ".join(categories.get("allLocations") or []) or categories.get("location")
    workplace = item.get("workplaceType")
    if workplace == "unspecified":
        workplace = None
    return " · ".join(part for part in (places, workplace) if part) or None


def _description(item: dict) -> str:
    """Descrizione, sezioni (requisiti, responsabilità...) e note finali in un unico testo."""
    parts = [item.get("descriptionPlain")]
    parts += [f"{section['text']}: {html_to_text(section.get('content'))}" for section in item.get("lists") or []]
    parts.append(item.get("additionalPlain"))
    return "\n".join(part.strip() for part in parts if part)


def _posted_date(created_at_ms: int | None) -> date | None:
    """Lever indica la data di creazione in millisecondi dall'epoch."""
    if not created_at_ms:
        return None
    return datetime.fromtimestamp(created_at_ms / 1000, tz=timezone.utc).date()
