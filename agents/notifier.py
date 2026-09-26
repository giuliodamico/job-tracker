"""Report delle nuove offerte su Telegram e lettura dei bottoni Approva/Scarta.

I bottoni si leggono in polling (getUpdates) a ogni avvio dello scout: nessun webhook e nessun
server sempre acceso. Telegram conserva i bottoni premuti per 24 ore, quindi lo scout va avviato
almeno una volta al giorno; meglio più spesso con `--updates-only`, che non chiama Claude.
"""

import html
import logging
import os
import time

import requests

from app import db
from app.db import Listing

API_URL = "https://api.telegram.org/bot{token}/{method}"
TIMEOUT = 30  # secondi
REQUIRED_ENV = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
# callback_data del bottone -> (nuovo status, riga aggiunta al messaggio)
ACTIONS = {"approve": ("Approved", "✅ Approvata"), "discard": ("Discarded", "❌ Scartata")}

log = logging.getLogger(__name__)


class TelegramError(Exception):
    """Errore dell'API Telegram. Il messaggio non contiene il token del bot."""


def is_configured() -> bool:
    return all(os.getenv(name) for name in REQUIRED_ENV)


def send_report(listings: list[Listing]) -> None:
    """Un messaggio di riepilogo, poi un messaggio per offerta con i bottoni Approva/Scarta."""
    count = len(listings)
    _send(f"🔎 <b>{count} {'nuova offerta' if count == 1 else 'nuove offerte'}</b> dallo scouting")
    for listing in listings:
        time.sleep(1)  # Telegram chiede di non superare circa un messaggio al secondo per chat
        try:
            _send(_render(listing), reply_markup=_buttons(listing.id))
        except TelegramError as exc:
            log.error("Telegram, offerta %d non inviata: %s", listing.id, exc)


def process_updates() -> int:
    """Applica i bottoni premuti dall'ultimo avvio. Restituisce quante offerte ha aggiornato."""
    changed = 0
    offset = None
    while True:
        # Chiedere gli aggiornamenti successivi a `offset` conferma a Telegram quelli già gestiti.
        params = {"timeout": 0} if offset is None else {"timeout": 0, "offset": offset}
        updates = _call("getUpdates", **params)
        if not updates:
            return changed
        for update in updates:
            offset = update["update_id"] + 1
            callback = update.get("callback_query")
            if callback and _apply_button(callback):
                changed += 1


def _apply_button(callback: dict) -> bool:
    message = callback.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    if str(chat_id) != os.environ["TELEGRAM_CHAT_ID"]:
        return False  # bottoni da altre chat: ignorati
    action, _, raw_id = (callback.get("data") or "").partition(":")
    if action not in ACTIONS or not raw_id.isdigit():
        return False

    status, label = ACTIONS[action]
    listing = db.set_listing_status(int(raw_id), status)
    if listing is None:
        log.warning("Telegram: bottone per un'offerta che non esiste più (id %s)", raw_id)
        return False
    log.info("Telegram: %s · %s -> %s", listing.company, listing.role, status)
    try:
        # Stesso testo più l'esito, senza bottoni: in chat si vede cosa è stato registrato.
        _call(
            "editMessageText",
            chat_id=chat_id,
            message_id=message["message_id"],
            text=f"{_render(listing)}\n\n<b>{label}</b>",
            parse_mode="HTML",
            link_preview_options={"is_disabled": True},
        )
    except TelegramError as exc:
        log.warning("Telegram: messaggio non aggiornato (%s), lo status è comunque salvato", exc)
    return True


def _render(listing: Listing) -> str:
    return "\n".join(
        [
            f"<b>{html.escape(listing.company)}</b> · {html.escape(listing.role)}",
            f"📍 {html.escape(listing.location or 'sede non indicata')} · ⭐ {listing.relevance_score}/100",
            f"<i>{html.escape(listing.relevance_reason or '')}</i>",
            f'<a href="{html.escape(listing.job_url)}">Apri l\'annuncio</a>',
        ]
    )


def _buttons(listing_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Approva", "callback_data": f"approve:{listing_id}"},
                {"text": "❌ Scarta", "callback_data": f"discard:{listing_id}"},
            ]
        ]
    }


def _send(text: str, reply_markup: dict | None = None) -> None:
    payload = {
        "chat_id": os.environ["TELEGRAM_CHAT_ID"],
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    _call("sendMessage", **payload)


def _call(method: str, **payload):
    """Chiamata all'API Telegram; su rate limit (429) aspetta quanto indicato e riprova una volta."""
    url = API_URL.format(token=os.environ["TELEGRAM_BOT_TOKEN"], method=method)
    for attempt in (1, 2):
        try:
            response = requests.post(url, json=payload, timeout=TIMEOUT)
            data = response.json()
        except requests.Timeout:
            raise TelegramError(f"{method}: timeout dopo {TIMEOUT}s") from None
        except (requests.RequestException, ValueError) as exc:
            # Niente str(exc): conterrebbe l'URL, e quindi il token del bot.
            raise TelegramError(f"{method}: {type(exc).__name__}") from None
        if data.get("ok"):
            return data["result"]
        retry_after = (data.get("parameters") or {}).get("retry_after")
        if response.status_code == 429 and retry_after and attempt == 1:
            time.sleep(min(retry_after, 60))
            continue
        raise TelegramError(f"{method}: {data.get('description') or f'HTTP {response.status_code}'}")
