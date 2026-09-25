"""Dashboard Streamlit per tracciare le candidature di lavoro.

Avvio, dalla root del progetto:  streamlit run app/dashboard.py
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

# `streamlit run` mette sul path solo la cartella app/: aggiungiamo la root del progetto
# per importare il package `app`, con lo stesso import che useranno gli agenti.
ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import charts, db  # noqa: E402

st.set_page_config(page_title="Job Tracker", page_icon="💼", layout="wide")

FORM_FIELDS = (
    "company", "role", "location", "date_applied", "status", "source",
    "salary_range", "job_url", "cv_version", "cover_letter_url", "notes",
)
# Colonne mostrate in tabella, nell'ordine di visualizzazione; solo lo status è modificabile.
TABLE_COLUMNS = {
    "company": st.column_config.TextColumn("Azienda"),
    "role": st.column_config.TextColumn("Ruolo"),
    "status": st.column_config.SelectboxColumn(
        "Status", options=db.STATUSES, required=True, help="Doppio clic per cambiare lo status"
    ),
    "date_applied": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
    "location": st.column_config.TextColumn("Sede"),
    "source": st.column_config.TextColumn("Fonte"),
    "salary_range": st.column_config.TextColumn("RAL"),
    "job_url": st.column_config.LinkColumn("Annuncio", display_text="Apri"),
    "cv_version": st.column_config.TextColumn("Versione CV"),
    "cover_letter_url": st.column_config.LinkColumn("Cover letter", display_text="Apri"),
    "notes": st.column_config.TextColumn("Note", width="large"),
}


@st.cache_resource(show_spinner="Preparo il database…")
def prepare_database() -> None:
    """Una volta per processo: crea le tabelle e, solo sul SQLite locale, i dati di esempio."""
    db.init_db()
    if db.engine.dialect.name == "sqlite":
        db.seed_if_empty()


def add_application_from_form() -> None:
    values = {field: st.session_state[f"new_{field}"] for field in FORM_FIELDS}
    values = {k: (v.strip() or None) if isinstance(v, str) else v for k, v in values.items()}
    if not values["company"] or not values["role"]:
        st.session_state.form_error = "Azienda e ruolo sono obbligatori."
        return
    db.add_application(**values)
    st.session_state.flash = f"Candidatura aggiunta: {values['role']} @ {values['company']}"
    defaults = {"date_applied": date.today(), "status": db.STATUSES[0]}
    for field in FORM_FIELDS:  # svuota il form riportando i campi ai valori iniziali
        st.session_state[f"new_{field}"] = defaults.get(field, "")


def save_status_changes(view: pd.DataFrame, editor_key: str) -> None:
    for row, changes in st.session_state[editor_key]["edited_rows"].items():
        if "status" in changes:
            application = view.iloc[int(row)]
            db.update_status(int(application["id"]), changes["status"])
            st.session_state.flash = (
                f"{application['company']}: {application['status']} → {changes['status']}"
            )
    # Una key nuova ricrea l'editor da zero, sui dati appena salvati.
    st.session_state.editor_version += 1


prepare_database()
st.session_state.setdefault("editor_version", 0)
if message := st.session_state.pop("flash", None):
    st.toast(message, icon="✅")

with st.sidebar:
    st.header("Nuova candidatura")
    with st.form("new_application", border=False):
        st.text_input("Azienda *", key="new_company")
        st.text_input("Ruolo *", key="new_role")
        st.text_input("Sede", key="new_location", placeholder="Milano, Remoto…")
        st.date_input("Data candidatura", key="new_date_applied", format="DD/MM/YYYY")
        st.selectbox("Status", db.STATUSES, key="new_status")
        st.text_input("Fonte", key="new_source", placeholder="LinkedIn, Indeed, referral…")
        st.text_input("RAL", key="new_salary_range", placeholder="35-42k €")
        st.text_input("Link annuncio", key="new_job_url")
        st.text_input("Versione CV", key="new_cv_version")
        st.text_input("Link cover letter", key="new_cover_letter_url")
        st.text_area("Note", key="new_notes")
        if error := st.session_state.pop("form_error", None):
            st.error(error)
        st.form_submit_button(
            "Aggiungi candidatura", type="primary", width="stretch",
            on_click=add_application_from_form,
        )
    st.caption(f"Database: {db.engine.dialect.name}")

df = db.load_applications()
total = len(df)
interviews = int((df["status"] == "Interview").sum())
offers = int((df["status"] == "Offer").sum())
conversion = offers / total if total else 0

st.title("💼 Job Tracker")

kpis = st.columns(4)
kpis[0].metric("Candidature", total, border=True)
kpis[1].metric("Colloqui", interviews, border=True, help="Candidature ora in stato Interview")
kpis[2].metric("Offerte", offers, border=True)
kpis[3].metric(
    "Tasso di conversione", f"{conversion:.1%}".replace(".", ","),
    border=True, help="Offerte / candidature totali",
)

chart_col, table_col = st.columns([2, 3], gap="large")

with chart_col:
    st.subheader("Distribuzione per status")
    if total:
        background = "#0e1117" if st.context.theme.type == "dark" else "#ffffff"
        st.plotly_chart(charts.status_donut(df, background), config={"displayModeBar": False})
    else:
        st.info("Il grafico comparirà con la prima candidatura.")

with table_col:
    st.subheader("Candidature")
    selected = st.pills("Filtra per status", db.STATUSES, selection_mode="multi", default=db.STATUSES)
    view = df[df["status"].isin(selected)].reset_index(drop=True)
    if not total:
        st.info("Ancora nessuna candidatura: aggiungine una dal form nella barra laterale.")
    elif view.empty:
        st.info("Nessuna candidatura con gli status selezionati.")
    else:
        editor_key = f"status_editor_{st.session_state.editor_version}"
        st.data_editor(
            view,
            key=editor_key,
            on_change=save_status_changes,
            args=(view, editor_key),
            hide_index=True,
            column_order=list(TABLE_COLUMNS),
            column_config=TABLE_COLUMNS,
            disabled=[column for column in view.columns if column != "status"],
        )
