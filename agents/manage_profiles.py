"""Profili di ricerca dell'agente di scouting, da riga di comando.

Dalla root del progetto:
    python -m agents.manage_profiles add "Data Scientist" --location Roma --seniority "junior/graduate"
    python -m agents.manage_profiles list
    python -m agents.manage_profiles deactivate 2
"""

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # avviato come file (python agents/manage_profiles.py)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.exc import OperationalError  # noqa: E402

from app import db  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profili di ricerca dell'agente di scouting.")
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="aggiunge un profilo attivo")
    add.add_argument("keyword", help='ruolo da cercare nel titolo, es. "Data Scientist"')
    add.add_argument("--location", help="es. Roma, Milano, Remoto")
    add.add_argument("--seniority", help='es. "junior/graduate"')

    commands.add_parser("list", help="elenca tutti i profili")

    deactivate = commands.add_parser("deactivate", help="disattiva un profilo")
    deactivate.add_argument("id", type=int)

    args = parser.parse_args(argv)
    try:
        db.init_db()
    except OperationalError as exc:
        # La prima riga dell'errore del driver basta a capire il problema (psycopg non mostra la password).
        print(f"Database non raggiungibile: {str(exc.orig or exc).splitlines()[0]}", file=sys.stderr)
        return 1

    if args.command == "add":
        profile_id = db.add_search_profile(
            args.keyword.strip(), args.location or None, args.seniority or None
        )
        print(f"Profilo {profile_id} aggiunto e attivo.")
    elif args.command == "list":
        _print_profiles(db.get_search_profiles())
    else:
        if not db.deactivate_search_profile(args.id):
            print(f"Nessun profilo con id {args.id}.", file=sys.stderr)
            return 1
        print(f"Profilo {args.id} disattivato.")
    return 0


def _print_profiles(profiles: list[db.SearchProfile]) -> None:
    if not profiles:
        print('Nessun profilo. Esempio: python -m agents.manage_profiles add "Data Scientist" --location Roma')
        return
    rows = [("ID", "ATTIVO", "KEYWORD", "LOCATION", "SENIORITY")]
    rows += [
        (str(p.id), "sì" if p.active else "no", p.keyword, p.location or "-", p.seniority or "-")
        for p in profiles
    ]
    widths = [max(len(row[col]) for row in rows) for col in range(len(rows[0]))]
    for row in rows:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip())


if __name__ == "__main__":
    sys.exit(main())
