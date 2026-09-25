"""Accesso al database: modello `applications` e operazioni di lettura/scrittura.

Il modulo non dipende da Streamlit, così lo possono importare anche gli agenti
(`from app import db`). Il backend si sceglie con DATABASE_URL: se non è impostata
si usa un file SQLite locale, altrimenti qualunque URL SQLAlchemy (es. Postgres su Supabase).
"""

import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import Date, DateTime, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, validates

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{ROOT_DIR / 'job_tracker.db'}"
STATUSES = ("Applied", "Interview", "Offer", "Rejected")

# pool_pre_ping scarta le connessioni chiuse lato server (Supabase chiude quelle inattive).
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


class Base(DeclarativeBase):
    pass


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    company: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    date_applied: Mapped[date] = mapped_column(Date, default=date.today)
    status: Mapped[str] = mapped_column(String(20), default="Applied")
    source: Mapped[str | None] = mapped_column(String(100))
    job_url: Mapped[str | None] = mapped_column(Text)
    salary_range: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    cv_version: Mapped[str | None] = mapped_column(String(100))
    cover_letter_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @validates("status")
    def _check_status(self, _key: str, value: str) -> str:
        if value not in STATUSES:
            raise ValueError(f"Status non valido: {value!r}. Valori ammessi: {', '.join(STATUSES)}")
        return value


def init_db() -> None:
    """Crea le tabelle mancanti; quelle esistenti non vengono toccate."""
    Base.metadata.create_all(engine)


def load_applications() -> pd.DataFrame:
    """Tutte le candidature, dalla più recente."""
    query = select(Application.__table__).order_by(
        Application.date_applied.desc(), Application.id.desc()
    )
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


def add_application(**fields) -> int:
    """Inserisce una candidatura (campi = colonne di Application) e ne restituisce l'id."""
    with Session(engine) as session:
        application = Application(**fields)
        session.add(application)
        session.commit()
        return application.id


def update_status(application_id: int, status: str) -> None:
    """Cambia lo status di una candidatura; updated_at si aggiorna da solo."""
    with Session(engine) as session:
        application = session.get(Application, application_id)
        if application is None:
            raise LookupError(f"Nessuna candidatura con id {application_id}")
        application.status = status
        session.commit()


def seed_if_empty() -> bool:
    """Inserisce le candidature di esempio se la tabella è vuota. True se le ha inserite."""
    with Session(engine) as session:
        if session.scalar(select(func.count()).select_from(Application)):
            return False
        session.add_all(Application(**row) for row in _sample_applications())
        session.commit()
        return True


def _sample_applications() -> list[dict]:
    """Dati di esempio con date relative a oggi, così restano verosimili."""
    today = date.today()
    return [
        {
            "company": "Kairos Labs",
            "role": "AI Engineer",
            "location": "Remoto",
            "date_applied": today - timedelta(days=41),
            "status": "Offer",
            "source": "Referral",
            "job_url": "https://example.com/jobs/kairos-labs-ai-engineer",
            "salary_range": "45-52k €",
            "notes": "Offerta scritta: 48k + welfare. Risposta entro venerdì.",
            "cv_version": "v4-ai",
            "cover_letter_url": "https://example.com/docs/cover-letter-kairos-labs",
        },
        {
            "company": "Brightwave Energia",
            "role": "Python Developer",
            "location": "Torino",
            "date_applied": today - timedelta(days=33),
            "status": "Rejected",
            "source": "Indeed",
            "job_url": "https://example.com/jobs/brightwave-python-developer",
            "salary_range": "32-38k €",
            "notes": "Scartata dopo lo screening: cercavano 3+ anni di esperienza con Django.",
            "cv_version": "v2-dev",
            "cover_letter_url": None,
        },
        {
            "company": "Nexum Pay",
            "role": "Data Analyst",
            "location": "Milano (ibrido)",
            "date_applied": today - timedelta(days=21),
            "status": "Interview",
            "source": "LinkedIn",
            "job_url": "https://example.com/jobs/nexum-pay-data-analyst",
            "salary_range": "35-42k €",
            "notes": "Colloquio HR superato; tecnico (SQL + caso pratico) la prossima settimana.",
            "cv_version": "v3-data",
            "cover_letter_url": "https://example.com/docs/cover-letter-nexum-pay",
        },
        {
            "company": "Tessera Analytics",
            "role": "Business Intelligence Analyst",
            "location": "Bologna",
            "date_applied": today - timedelta(days=14),
            "status": "Interview",
            "source": "Sito aziendale",
            "job_url": "https://example.com/jobs/tessera-bi-analyst",
            "salary_range": "33-40k €",
            "notes": "Case study su dashboard vendite da consegnare entro lunedì.",
            "cv_version": "v3-data",
            "cover_letter_url": None,
        },
        {
            "company": "Orbitale Logistica",
            "role": "Junior Data Scientist",
            "location": "Roma",
            "date_applied": today - timedelta(days=6),
            "status": "Applied",
            "source": "InfoJobs",
            "job_url": "https://example.com/jobs/orbitale-junior-data-scientist",
            "salary_range": "30-35k €",
            "notes": None,
            "cv_version": "v3-data",
            "cover_letter_url": "https://example.com/docs/cover-letter-orbitale",
        },
        {
            "company": "Atlante Assicurazioni",
            "role": "Data Engineer",
            "location": "Milano",
            "date_applied": today - timedelta(days=2),
            "status": "Applied",
            "source": "LinkedIn",
            "job_url": "https://example.com/jobs/atlante-data-engineer",
            "salary_range": "40-48k €",
            "notes": "Candidatura con Easy Apply, recruiter contattata in privato.",
            "cv_version": "v3-data",
            "cover_letter_url": None,
        },
    ]
