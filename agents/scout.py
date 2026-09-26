"""Agente di scouting: cerca offerte nuove per i profili attivi, le valuta con Claude, salva quelle
pertinenti nella tabella `listings` e manda il report su Telegram.

Dalla root del progetto:
    python -m agents.scout                  # giro completo
    python -m agents.scout --updates-only   # registra solo i bottoni premuti su Telegram
"""

import argparse
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType

if __package__ in (None, ""):  # avviato come file (python agents/scout.py)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic  # noqa: E402

from agents import notifier, scorer  # noqa: E402
from agents.sources import JobPosting, SourceError, adzuna, greenhouse, lever, load_companies  # noqa: E402
from app import db  # noqa: E402

SOURCES = (adzuna, greenhouse, lever)
SCORING_WORKERS = 4
# Errori di configurazione (chiave, permessi, modello): inutile provare con le altre offerte.
FATAL_API_ERRORS = (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError)

log = logging.getLogger("scout")

Found = tuple[db.SearchProfile, JobPosting]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    logging.getLogger("httpx2").setLevel(logging.WARNING)  # l'SDK Anthropic logga ogni richiesta
    db.init_db()

    telegram = notifier.is_configured()
    if telegram:
        try:
            log.info("Telegram: %d offerte aggiornate dai bottoni", notifier.process_updates())
        except notifier.TelegramError as exc:
            log.error("Telegram, lettura dei bottoni non riuscita: %s", exc)
    else:
        log.warning("Telegram non configurato (%s): niente report né bottoni", ", ".join(notifier.REQUIRED_ENV))
    if args.updates_only:
        return 0

    profiles = db.get_search_profiles(active_only=True)
    if not profiles:
        log.warning("Nessun profilo attivo: aggiungine uno con python -m agents.manage_profiles add")
        return 0
    if not os.getenv("ANTHROPIC_API_KEY"):
        log.error("ANTHROPIC_API_KEY mancante: senza Claude le offerte non si possono valutare")
        return 1

    found = _collect(profiles)
    fresh = _only_new(found)
    log.info("Offerte trovate: %d, mai viste prima: %d", len(found), len(fresh))
    if not fresh:
        return 0

    try:
        relevant = _score_and_save(fresh, args.min_score)
    except FATAL_API_ERRORS as exc:
        log.error("Claude API: %s. Le offerte verranno valutate al prossimo avvio.", exc)
        return 1

    if relevant and telegram:
        try:
            notifier.send_report(relevant)
        except notifier.TelegramError as exc:
            log.error("Telegram, report non inviato: %s", exc)
    return 0


def _collect(profiles: list[db.SearchProfile]) -> list[Found]:
    """Interroga le fonti in parallelo; dentro ogni fonte i profili passano uno alla volta."""
    sources = []
    for source in SOURCES:
        missing = [name for name in getattr(source, "REQUIRED_ENV", ()) if not os.getenv(name)]
        if missing:
            log.warning("%s saltata: mancano %s", _name(source), ", ".join(missing))
        else:
            sources.append(source)

    companies = load_companies()
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        batches = pool.map(lambda source: _search_source(source, profiles, companies), sources)
        return [item for batch in batches for item in batch]


def _search_source(source: ModuleType, profiles: list[db.SearchProfile], companies: dict) -> list[Found]:
    found = []
    for profile in profiles:
        try:
            postings = source.search(profile, companies)
        except SourceError as exc:
            log.warning("%s, profilo %r: %s", _name(source), profile.keyword, exc)
            continue
        except Exception:  # un errore imprevisto in una fonte non deve fermare le altre
            log.exception("%s, profilo %r: errore imprevisto", _name(source), profile.keyword)
            continue
        log.info("%s, profilo %r: %d offerte", _name(source), profile.keyword, len(postings))
        found.extend((profile, posting) for posting in postings)
    return found


def _only_new(found: list[Found]) -> list[Found]:
    """Toglie le offerte già in `listings` e i doppioni dello stesso giro (stesso URL)."""
    seen = db.listing_urls()
    fresh = []
    for profile, posting in found:
        if posting["url"] not in seen:
            seen.add(posting["url"])
            fresh.append((profile, posting))
    return fresh


def _score_and_save(items: list[Found], min_score: int) -> list[db.Listing]:
    """Valuta le offerte con Claude e le salva: New sopra soglia, Discarded sotto (fuori dal report)."""
    relevant, below = [], 0
    with ThreadPoolExecutor(max_workers=SCORING_WORKERS) as pool:
        futures = [(pool.submit(scorer.score, posting, profile), profile, posting) for profile, posting in items]
        for future, profile, posting in futures:
            label = f"{posting['company']} · {posting['role']}"
            try:
                relevance = future.result()
            except FATAL_API_ERRORS:
                pool.shutdown(cancel_futures=True)
                raise
            except (anthropic.APIError, scorer.ScoringError) as exc:
                # Non salvata: al prossimo avvio risulta ancora nuova e viene rivalutata.
                log.warning("Valutazione non riuscita, riprovo al prossimo avvio: %s (%s)", label, exc)
                continue

            # Sotto soglia: scartata in silenzio, ma salvata perché la deduplica non la rivaluti.
            status = "New" if relevance.score >= min_score else "Discarded"
            listing = db.add_listing(
                company=posting["company"],
                role=posting["role"],
                location=posting["location"],
                description=posting["description"],
                job_url=posting["url"],
                source=posting["source"],
                relevance_score=relevance.score,
                relevance_reason=relevance.reason,
                status=status,
            )
            if status == "New":
                relevant.append(listing)
                log.info("Nuova (%d): %s", relevance.score, label)
            else:
                below += 1
                log.info("Sotto soglia (%d < %d), scartata: %s. %s", relevance.score, min_score, label, relevance.reason)
    log.info("Nel report: %d, sotto soglia: %d", len(relevant), below)
    return relevant


def _name(source: ModuleType) -> str:
    return source.__name__.rsplit(".", 1)[-1]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agente di scouting delle offerte di lavoro.")
    parser.add_argument(
        "--min-score",
        type=int,
        default=int(os.getenv("SCOUT_MIN_SCORE") or 50),
        help="punteggio minimo (0-100) per finire nel report; di default SCOUT_MIN_SCORE, altrimenti 50",
    )
    parser.add_argument(
        "--updates-only",
        action="store_true",
        help="registra solo i bottoni Approva/Scarta premuti su Telegram, senza cercare offerte",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
