# Job Tracker

Dashboard personale per tracciare le candidature di lavoro, costruita con Streamlit. Mostra a colpo d'occhio quante candidature hai inviato e quanti colloqui e offerte hai ottenuto, e ti permette di aggiornare lo stato di ogni candidatura direttamente dalla tabella.

Il progetto è pensato per crescere: il database è condiviso e `app/db.py` non dipende da Streamlit, così i prossimi agenti (scouting offerte e generazione candidature) lavoreranno sugli stessi dati della dashboard.

## Funzionalità

- **KPI:** candidature totali, colloqui (status *Interview*), offerte e tasso di conversione (offerte / candidature).
- **Grafico a ciambella** con la distribuzione delle candidature per status.
- **Tabella** ordinata dalla candidatura più recente e filtrabile per status. Per cambiare lo status fai doppio clic sulla cella *Status* e scegli il nuovo valore: il salvataggio è immediato.
- **Form** nella barra laterale per aggiungere una candidatura a mano (azienda e ruolo sono obbligatori).
- **Due database, stesso codice:** SQLite in locale, PostgreSQL su Supabase in produzione, scelti con la variabile d'ambiente `DATABASE_URL`.

## Stack tecnologico

| Ambito | Tecnologia |
|---|---|
| Linguaggio | Python 3.11+ |
| Interfaccia | Streamlit |
| Grafici | Plotly |
| Elaborazione dati | pandas |
| Database e ORM | SQLAlchemy 2.1: SQLite in locale, PostgreSQL su Supabase in produzione |
| Driver Postgres | psycopg 3 |
| Configurazione | python-dotenv (file `.env`) |

## Struttura

```
job-tracker/
├── app/
│   ├── __init__.py
│   ├── dashboard.py              # interfaccia Streamlit
│   ├── db.py                     # modello SQLAlchemy e operazioni sul database
│   └── charts.py                 # grafici Plotly
├── agents/                       # agenti (in arrivo)
├── profile/
│   └── cv_profile.example.md     # template del profilo candidato
├── .github/workflows/            # workflow GitHub Actions (in arrivo)
├── .env.example                  # modello del file .env
├── .gitignore
├── LICENSE
├── README.md
└── requirements.txt
```

## Installazione

Serve Python 3.11 o superiore.

```bash
git clone https://github.com/giuliodamico/job-tracker.git
cd job-tracker
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configurazione

### File .env

Le credenziali stanno solo nel file `.env`, escluso da git. Crealo partendo dal modello:

```bash
cp .env.example .env
```

- **Sviluppo locale:** lascia `DATABASE_URL` vuota. La dashboard usa SQLite e crea il file `job_tracker.db` nella root del progetto.
- **Produzione su Supabase:** nel progetto Supabase apri *Connect*, scegli *Session pooler*, copia l'URI e sostituisci `[YOUR-PASSWORD]` con la password del database:

  ```
  DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
  ```

  Se la password contiene caratteri speciali (`@`, `:`, `/`, `#`…) va codificata nell'URL (es. `@` → `%40`).
  Meglio il Session pooler delle alternative: la connessione diretta richiede una rete IPv6 e il Transaction pooler non supporta i prepared statement che usa il driver psycopg.

Il codice è lo stesso nei due casi, cambia solo la variabile. La tabella `applications` viene creata automaticamente al primo avvio.

> **Supabase e sicurezza:** la tabella nasce nello schema `public`, che Supabase espone tramite la sua Data API. Dopo il primo avvio attiva la Row Level Security (Table Editor → `applications` → *Enable RLS*, oppure `alter table applications enable row level security;` nel SQL Editor). La dashboard si collega come proprietaria della tabella e continua a funzionare, mentre la tabella non è più leggibile con la chiave pubblica `anon`.

### Profilo candidato

Il profilo che useranno gli agenti sta in `profile/cv_profile.md`, escluso da git. Crealo dal template e compilalo:

```bash
cp profile/cv_profile.example.md profile/cv_profile.md
```

## Avvio

Dalla root del progetto, con l'ambiente virtuale attivo:

```bash
streamlit run app/dashboard.py
```

La dashboard si apre su http://localhost:8501.

Al primo avvio, se il database SQLite è vuoto, vengono inserite 6 candidature di esempio. Su Postgres/Supabase i dati di esempio non vengono inseriti, così il tracker reale resta pulito. Per ripartire da zero in locale: ferma la dashboard, cancella `job_tracker.db` e riavviala.

## Privacy

Il repository non contiene credenziali né dati personali. `.gitignore` esclude:

- `.env` e `.streamlit/secrets.toml`, cioè le credenziali;
- ogni database `*.db` / `*.sqlite3`, in qualunque cartella, insieme ai file temporanei di SQLite: le candidature reali restano sul tuo computer o su Supabase;
- tutta la cartella `profile/` tranne il template `cv_profile.example.md`.

I dati di esempio in `app/db.py` usano aziende inventate e link `example.com`.

## Database condiviso (per gli agenti)

`app/db.py` si importa anche fuori da Streamlit:

```python
from app import db

db.init_db()
db.add_application(company="Acme", role="Data Analyst", source="scouting-agent")
db.update_status(1, "Interview")
df = db.load_applications()
```

Lancia gli script degli agenti come moduli dalla root del progetto (es. `python -m agents.nome_agente`), così il package `app` è importabile.

## Roadmap

- [x] Dashboard Streamlit: KPI, grafico per status, tabella filtrabile con aggiornamento dello status, form per le nuove candidature
- [x] Database condiviso: SQLite in locale, PostgreSQL su Supabase in produzione
- [ ] Agente di scouting: cerca offerte in linea con il profilo (in arrivo)
- [ ] Agente di generazione candidature: prepara CV e cover letter su misura partendo da `profile/cv_profile.md` (in arrivo)

## Licenza

Distribuito con licenza MIT: vedi [LICENSE](LICENSE).
