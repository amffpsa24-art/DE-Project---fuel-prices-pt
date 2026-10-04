# Fuel Prices PT

A daily ETL pipeline that collects the price of every fuel at every petrol station in Portugal and models it as a star schema in a hosted PostgreSQL database, building a price history that the official source does not keep. It runs automatically every day on GitHub Actions.

![Phase 1 architecture](docs/images/architecture.png)

## Why this project

Portugal's Directorate-General for Energy and Geology (DGEG) publishes current fuel prices for every station in the country at [precoscombustiveis.dgeg.gov.pt](https://precoscombustiveis.dgeg.gov.pt). It only shows the **current** price: when a station updates, the previous value is gone.

This pipeline takes a snapshot every day and stores it, turning a "right now" view into a historical dataset. That makes it possible to answer questions the source can't, such as how prices evolve by brand, region or station over time.

I built it as a portfolio project while moving from mechanical engineering into data engineering, to practise the full lifecycle of a pipeline: data discovery, extraction, transformation, storage, modelling, scheduling and visualisation.

## Data source

The DGEG website has no documented public API. I found the endpoint the site uses internally by inspecting its network traffic in the browser's DevTools:

```
GET https://precoscombustiveis.dgeg.gov.pt/api/PrecoComb/PesquisarPostos
```

Key findings (full details in [`notes/api-discovery.md`](notes/api-discovery.md)):

- Each record is one **(station, fuel type)** pair, so a station selling 4 fuels appears 4 times, with its details repeated.
- The `Quantidade` field holds the **total number of records** for the query (repeated on every row), which is what drives pagination.
- The API accepts up to 10,000 records per page, so a full national extraction takes **2 requests** (~13,600–14,100 records, varying day to day).
- Prices arrive as Portuguese-formatted text (`"1,164 €"`) and need parsing.

The data belongs to DGEG. Their terms allow personal, non-commercial use; this project is a non-commercial learning exercise and keeps request volume minimal (one run per day, with a pause between pages).

## How it works

The pipeline follows an **extract → transform → load** structure, with each step in its own module:

| Step | File | What it does |
|---|---|---|
| Extract | [`etl/extract.py`](etl/extract.py) | Paginated requests to the DGEG API until every record is collected |
| Transform | [`etl/transform.py`](etl/transform.py) | Converts the JSON records into a pandas DataFrame and parses prices into numbers |
| Load | [`etl/load.py`](etl/load.py) | Saves a dated raw CSV, then loads PostgreSQL through a staging table |
| Orchestration | [`pipeline.py`](pipeline.py) | Runs the three steps in sequence |
| Scheduling | [`.github/workflows/daily.yml`](.github/workflows/daily.yml) | Runs the pipeline every day on GitHub Actions |

Example run:

```
Page 1: 10000 records (accumulated: 10000 / 13627)
Page 2: 3627 records (accumulated: 13627 / 13627)
Extract complete: 13627 records

Transform complete: 13627 rows, 16 columns

Saved 13627 rows to data/raw/fuel_prices_2026-10-04.csv
Staged 13627 rows in stg_precos
Loaded PostgreSQL: 13627 price rows for 2026-10-04
Pipeline finished.
```

## Medallion architecture

![Medallion architecture](docs/images/medallion.png)

The data moves through three layers, following the **medallion** pattern. Each layer builds on the previous one, and the raw layer is never edited:

| Layer | Purpose | Phase 1 (today) |
|---|---|---|
| **Bronze** | Faithful copy of the source, kept for reprocessing | A dated CSV per run: `data/raw/` locally, a GitHub Actions artifact in the cloud |
| **Silver** | Cleaned, typed data in one consistent format | `stg_precos`: typed staging table in PostgreSQL, refilled on every run |
| **Gold** | Business-ready model for analysis | The star schema in Neon: `fact_precos` and three dimensions |

If the gold layer ever needs rebuilding, it can be reloaded from bronze with [`backfill.py`](backfill.py).

Phase 1 is a lightweight version of the pattern: the bronze CSV already includes the parsed price column next to the original text, and the silver layer is a staging table rather than a stored history. Phase 2 makes the layers explicit in Azure, with untouched API responses in bronze and cleaned Delta Lake tables in silver.

## Automation

The pipeline runs every day on **GitHub Actions** ([`daily.yml`](.github/workflows/daily.yml)) and writes to a **hosted PostgreSQL database on [Neon](https://neon.com)**, so it runs without any local machine switched on.

- **Schedule:** every day at 19:17 UTC, in the evening so most stations have published the day's prices. It can also be started manually from the Actions tab.
- **Credentials:** the database connection comes from **GitHub Secrets**, exposed to the job as environment variables. No password is stored in the code or the repository.
- **Raw snapshots:** GitHub's machines are wiped after each run, so the day's CSV is uploaded as a **workflow artifact**, kept for 90 days. The upload runs even if the database step fails, so the raw data is never lost to a load error.
- **Correct dates:** the job runs with the `Europe/Lisbon` time zone, so each snapshot gets the Portuguese date.
- **Safe reruns:** because loads are idempotent, a retried or manual run on the same day never duplicates data.

## Data model

![Star schema](docs/images/star_schema.png)

A **star schema** in PostgreSQL, defined in [`sql/schema.sql`](sql/schema.sql):

| Table | One row = | Key |
|---|---|---|
| `fact_precos` | one station × fuel × snapshot day | (`data_key`, `posto_id`, `combustivel_id`) |
| `dim_postos` | one station | DGEG station `Id` |
| `dim_combustivel` | one fuel type | generated ID |
| `dim_data` | one calendar day | integer date, e.g. `20261004` |

`fact_precos` is a **periodic snapshot fact table**: every station's price is recorded every day, even when it hasn't changed, so "what was the price on day X?" is a simple lookup.

The day's rows are bulk-copied (`COPY`) into the staging table, then [`sql/load_from_staging.sql`](sql/load_from_staging.sql) loads the dimensions first and the fact table second.

### Design decisions

- **Idempotent loads.** The fact table's primary key is (day, station, fuel), and inserts use `ON CONFLICT DO NOTHING`. Rerunning the pipeline on the same day never creates duplicates.
- **One transaction per run.** Staging, dimensions and facts load together: if any step fails, nothing from that run is kept.
- **Dimensions before facts.** Foreign keys guarantee every price points to an existing station, fuel and date.
- **Two dates per price.** `data_key` is when the pipeline captured the price; `data_atualizacao` is when the station last changed it. An old `data_atualizacao` flags a possibly stale price.
- **Exact prices.** Prices are `NUMERIC(6,3)`, not floating point, so values are stored exactly.
- **Station changes overwrite (SCD Type 1).** `dim_postos` keeps the latest details of each station, plus `primeira_vez` / `ultima_vez`, the first and latest day it appeared. A station whose `ultima_vez` stops advancing has probably closed.
- **Append-only bronze layer.** Each run adds a new dated CSV and never edits old ones.

### Example query

Average simple diesel price per district, on the latest day loaded:

```sql
SELECT p.distrito,
       ROUND(AVG(f.preco), 3) AS preco_medio,
       COUNT(*)               AS postos
FROM fact_precos f
JOIN dim_postos      p USING (posto_id)
JOIN dim_combustivel c USING (combustivel_id)
WHERE c.nome = 'Gasóleo simples'
  AND f.data_key = (SELECT MAX(data_key) FROM fact_precos)
GROUP BY p.distrito
ORDER BY preco_medio;
```

### Text encoding

All files and tables use **UTF-8**, so Portuguese characters (`ç`, `ã`, `ó`...) are stored exactly as DGEG sends them. Excel on Windows doesn't assume UTF-8 when a CSV is double-clicked and may show `Ã§` instead of `ç`. The data is correct: open the file with **Data → From Text/CSV** and choose **65001: Unicode (UTF-8)** as the file origin.

## Roadmap

![Roadmap](docs/images/roadmap.png)

**Phase 1: MVP** *(in progress)*
- [x] Discover and document the DGEG API
- [x] Modular ETL in Python (requests, pandas)
- [x] Daily, dated CSV snapshots
- [x] PostgreSQL star schema with idempotent loads
- [x] Hosted PostgreSQL (Neon) + daily scheduling with GitHub Actions
- [ ] Streamlit dashboard

**Phase 2: Cloud storage**
- [ ] Bronze layer in Azure Data Lake (untouched API responses)
- [ ] Explicit bronze / silver / gold layers

**Phase 3: Distributed processing**
- [ ] Databricks + Spark transformations
- [ ] Delta Lake tables
- [ ] Orchestration with Databricks Workflows or Azure Data Factory
- [ ] Power BI dashboard

## Project structure

```
├── .github/workflows/
│   └── daily.yml               # daily schedule on GitHub Actions
├── etl/
│   ├── extract.py              # API requests and pagination
│   ├── transform.py            # cleaning and parsing
│   └── load.py                 # bronze CSV + PostgreSQL load
├── sql/
│   ├── schema.sql              # star schema: tables, keys, constraints
│   └── load_from_staging.sql   # staging → dimensions → fact table
├── pipeline.py                 # runs the full ETL
├── backfill.py                 # loads existing raw CSVs into PostgreSQL
├── notebooks/                  # initial API exploration
├── notes/                      # API discovery notes and work logs
├── docs/images/                # diagrams
├── .env.example                # template for database settings
└── requirements.txt
```

The `data/` folder is created when the pipeline runs and is excluded from version control, as are all `.env` files except the template.

## How to run

Requires Python 3.14 (the version it was built and tested with) and PostgreSQL (tested with 18 locally, and Neon).

**1. Get the code and install dependencies**

```bash
git clone https://github.com/amffpsa24-art/DE-Project---fuel-prices-pt.git
cd DE-Project---fuel-prices-pt

python -m venv .venv
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

**2. Set up the database**

Use a local PostgreSQL or a hosted one such as Neon. Create a database, then the tables:

```bash
psql -U postgres -c "CREATE DATABASE fuel_prices ENCODING 'UTF8';"   # local only
psql "<your connection string>" -f sql/schema.sql
```

Copy `.env.example` to `.env` and fill in your connection settings. For a hosted database, include `PGSSLMODE=require`.

**3. Run**

```bash
python pipeline.py    # today's snapshot: raw CSV + database
python backfill.py    # optional: load any older CSVs from data/raw/
```

Both are safe to rerun: rows that already exist are skipped.

**4. Optional: schedule it on your own fork**

Add four repository secrets under **Settings → Secrets and variables → Actions**: `PGHOST`, `PGUSER`, `PGPASSWORD` and `PGDATABASE`. The workflow in `.github/workflows/daily.yml` then runs every day, or on demand from the Actions tab.

## Tech stack

**Now:** Python, requests, pandas, PostgreSQL, psycopg, SQL, Neon, GitHub Actions, Git/GitHub
**Planned:** Streamlit, Azure Data Lake, Databricks, Spark, Delta Lake, Power BI

## Author

**André Francisco**: mechanical engineer (MSc, Instituto Superior Técnico) moving into data engineering.
[LinkedIn](https://www.linkedin.com/in/your-profile)
