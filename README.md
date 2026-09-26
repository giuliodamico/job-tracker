# Job Tracker

Dashboard personale per tracciare le candidature di lavoro, costruita con Streamlit. Mostra a colpo d'occhio quante candidature hai inviato e quanti colloqui e offerte hai ottenuto, e ti permette di aggiornare lo stato di ogni candidatura direttamente dalla tabella.

Accanto alla dashboard c'è un agente di scouting: ogni giorno cerca nuove offerte per le posizioni che imposti, le valuta con Claude e ti manda su Telegram quelle pertinenti, da approvare o scartare con un tocco.

Il database è condiviso e `app/db.py` non dipende da Streamlit, così gli agenti lavorano sugli stessi dati della dashboard.

## Funzionalità

- **KPI:** candidature totali, colloqui (status *Interview*), offerte e tasso di conversione (offerte / candidature).
- **Grafico a ciambella** con la distribuzione delle candidature per status.
- **Tabella** ordinata dalla candidatura più recente e filtrabile per status. Per cambiare lo status fai doppio clic sulla cella *Status* e scegli il nuovo valore: il salvataggio è immediato.
- **Form** nella barra laterale per aggiungere una candidatura a mano (azienda e ruolo sono obbligatori).
- **Due database, stesso codice:** SQLite in locale, PostgreSQL su Supabase in produzione, scelti con la variabile d'ambiente `DATABASE_URL`.
- **Agente di scouting:** cerca offerte su Adzuna e sulle job board Greenhouse e Lever delle aziende che scegli, scarta quelle già viste, assegna a ogni nuova offerta un punteggio di pertinenza con Claude e invia su Telegram quelle sopra soglia, con i bottoni Approva e Scarta.

## Stack tecnologico

| Ambito | Tecnologia |
|---|---|
| Linguaggio | Python 3.11+ |
| Interfaccia | Streamlit |
| Grafici | Plotly |
| Elaborazione dati | pandas |
| Database e ORM | SQLAlchemy 2.1: SQLite in locale, PostgreSQL su Supabase in produzione |
| Driver Postgres | psycopg 3 |
| Configurazione | python-dotenv (file `.env`), PyYAML (aziende monitorate) |
| Valutazione offerte | API Claude (`claude-sonnet-5`) con l'SDK `anthropic` |
| Fonti di offerte | API Adzuna, job board API di Greenhouse e Lever (via `requests`) |
| Notifiche | API dei bot Telegram, in polling |

## Struttura

```
job-tracker/
├── app/
│   ├── __init__.py
│   ├── dashboard.py              # interfaccia Streamlit
│   ├── db.py                     # modello SQLAlchemy e operazioni sul database
│   └── charts.py                 # grafici Plotly
├── agents/
│   ├── scout.py                  # agente di scouting: ricerca, valutazione, report
│   ├── manage_profiles.py        # gestione delle ricerche attive da riga di comando
│   ├── scorer.py                 # punteggio di pertinenza con Claude
│   ├── notifier.py               # report e bottoni Telegram
│   └── sources/
│       ├── adzuna.py
│       ├── greenhouse.py
│       ├── lever.py
│       └── companies.example.yaml  # aziende da monitorare (esempio)
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

Il codice è lo stesso nei due casi, cambia solo la variabile. Le tabelle (`applications`, `search_profiles`, `listings`) vengono create automaticamente al primo avvio.

> **Supabase e sicurezza:** le tabelle nascono nello schema `public`, che Supabase espone tramite la sua Data API. Dopo il primo avvio attiva la Row Level Security su tutte e tre (Table Editor → *Enable RLS*, oppure nel SQL Editor `alter table applications enable row level security;` e lo stesso per `search_profiles` e `listings`). Dashboard e agenti si collegano come proprietari delle tabelle e continuano a funzionare, mentre le tabelle non sono più leggibili con la chiave pubblica `anon`.

Le chiavi dell'agente di scouting sono spiegate nella sezione [Agente di scouting](#agente-di-scouting).

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

## Agente di scouting

A ogni avvio l'agente:

1. registra i bottoni Approva/Scarta premuti su Telegram dall'avvio precedente;
2. per ogni ricerca attiva interroga in parallelo Adzuna, Greenhouse e Lever;
3. scarta le offerte già viste, confrontando l'URL con la tabella `listings`;
4. chiede a Claude un punteggio di pertinenza da 0 a 100, con una frase di motivazione;
5. salva le offerte con status `New` se superano la soglia (default 50), altrimenti le scarta in silenzio con status `Discarded`: restano solo nel log e nel database, così non vengono rivalutate;
6. se ci sono offerte `New`, le invia su Telegram. Se non ce ne sono, non manda nulla.

Si usano solo API ufficiali o job board pubbliche pensate per essere lette dai programmi: niente scraping.

### Chiavi (.env)

| Variabile | Dove si prende |
|---|---|
| `ANTHROPIC_API_KEY` | [platform.claude.com](https://platform.claude.com), sezione API keys |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | registrazione gratuita su [developer.adzuna.com](https://developer.adzuna.com). Senza, Adzuna viene saltata |
| `TELEGRAM_BOT_TOKEN` | crea un bot con [@BotFather](https://t.me/BotFather) (`/newbot`) |
| `TELEGRAM_CHAT_ID` | scrivi un messaggio qualsiasi al tuo bot, poi apri `https://api.telegram.org/bot<TOKEN>/getUpdates` e copia il valore di `"chat":{"id":...}` |
| `SCOUT_MIN_SCORE` | facoltativa, soglia del report (default 50) |

### Aziende e ricerche

Le aziende da controllare su Greenhouse e Lever stanno in `agents/sources/companies.yaml`, escluso da git perché rivela chi stai monitorando. Crealo dall'esempio e modificalo:

```bash
cp agents/sources/companies.example.yaml agents/sources/companies.yaml
```

Le ricerche stanno nel database e si gestiscono da riga di comando:

```bash
python -m agents.manage_profiles add "Data Scientist" --location Roma --seniority "junior/graduate"
python -m agents.manage_profiles list
python -m agents.manage_profiles deactivate 2
```

Su Greenhouse e Lever la keyword viene cercata nel titolo delle offerte di tutte le aziende in elenco, in qualunque sede: sono poi località e seniority a pesare nel punteggio di Claude. Usa keyword specifiche ("Data Scientist" più che "Data"), perché ogni offerta nuova costa una chiamata a Claude.

### Avvio

```bash
python -m agents.scout                    # giro completo
python -m agents.scout --min-score 70     # soglia diversa solo per questo avvio
python -m agents.scout --updates-only     # registra solo i bottoni premuti, senza chiamare Claude
```

Telegram conserva i bottoni premuti per 24 ore: l'agente va avviato almeno una volta al giorno. Conviene lanciare `--updates-only` anche più spesso, per esempio ogni ora: non costa nulla.

## Privacy

Il repository non contiene credenziali né dati personali. `.gitignore` esclude:

- `.env` e `.streamlit/secrets.toml`, cioè le credenziali;
- ogni database `*.db` / `*.sqlite3`, in qualunque cartella, insieme ai file temporanei di SQLite: le candidature reali restano sul tuo computer o su Supabase;
- tutta la cartella `profile/` tranne il template `cv_profile.example.md`;
- `agents/sources/companies.yaml`, l'elenco delle aziende che monitori (resta solo l'esempio).

Le ricerche impostate con `manage_profiles` e le offerte trovate stanno nel database, non nel repository.

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
- [x] Agente di scouting: offerte da Adzuna, Greenhouse e Lever, valutate con Claude, report Telegram con Approva/Scarta
- [ ] Agente di generazione candidature: prepara CV e cover letter su misura partendo da `profile/cv_profile.md` (in arrivo)

## Licenza

Distribuito con licenza MIT: vedi [LICENSE](LICENSE).
