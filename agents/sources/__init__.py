"""Fonti di offerte per l'agente di scouting.

Ogni modulo (adzuna, greenhouse, lever) espone `search(profile, companies)` e restituisce una
lista di JobPosting, lo stesso formato per tutte le fonti. Si usano solo API ufficiali o job board
pubbliche pensate per essere lette dai programmi: niente scraping.
"""

import html
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, TypedDict

import requests
import yaml

TIMEOUT = 20  # secondi per ogni chiamata HTTP
COMPANIES_FILE = Path(__file__).with_name("companies.yaml")
HTTP_HINTS = {401: "chiavi non valide", 403: "accesso negato", 404: "non trovato: token o URL errato?"}

log = logging.getLogger(__name__)


class JobPosting(TypedDict):
    company: str
    role: str
    location: str | None
    url: str
    description: str
    source: str
    posted_date: date | None


class SourceError(Exception):
    """Errore di una fonte. Il messaggio è sicuro da loggare: non contiene URL né chiavi."""


def get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    """GET con timeout. Gli errori diventano SourceError senza l'URL, che può contenere chiavi."""
    try:
        response = requests.get(url, params=params, timeout=TIMEOUT)
    except requests.Timeout:
        raise SourceError(f"timeout dopo {TIMEOUT}s") from None
    except requests.RequestException as exc:
        raise SourceError(f"errore di rete ({type(exc).__name__})") from None
    if response.status_code == 429:
        raise SourceError("rate limit raggiunto (HTTP 429)")
    if response.status_code >= 400:
        hint = HTTP_HINTS.get(response.status_code)
        raise SourceError(f"HTTP {response.status_code}" + (f" ({hint})" if hint else ""))
    try:
        return response.json()
    except ValueError:
        raise SourceError("risposta non in formato JSON") from None


def load_companies() -> dict[str, list[dict[str, str]]]:
    """Aziende da controllare su ogni job board, dalle sezioni greenhouse/lever di companies.yaml."""
    if not COMPANIES_FILE.exists():
        log.warning(
            "%s non trovato: Greenhouse e Lever restano senza aziende. "
            "Crealo copiando companies.example.yaml.", COMPANIES_FILE.name,
        )
        return {}
    with COMPANIES_FILE.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    companies = {}
    for board in ("greenhouse", "lever"):
        companies[board] = []
        for entry in data.get(board) or []:
            if isinstance(entry, dict) and entry.get("token"):
                token = str(entry["token"])
                companies[board].append({"token": token, "name": str(entry.get("name") or token)})
            else:
                log.warning("companies.yaml, sezione %s: voce senza token ignorata (%r)", board, entry)
    return companies


def title_matches(title: str, keyword: str) -> bool:
    """La keyword del profilo compare nel titolo dell'offerta, senza distinguere le maiuscole."""
    return keyword.casefold() in title.casefold()


def html_to_text(markup: str | None) -> str:
    """Testo semplice da HTML, anche quando l'HTML arriva a sua volta con le entità escapate."""
    text = re.sub(r"<[^>]+>", " ", html.unescape(markup or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_date(value: str | None) -> date | None:
    """Data da una stringa ISO 8601 (es. 2026-09-18T14:57:30-04:00); None se manca o non si legge."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None
