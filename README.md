# Fuel Prices PT

A daily ETL pipeline that collects the price of every fuel at every petrol station in Portugal, building a price history that the official source does not keep.

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

The pipeline follows a classic **extract → transform → load** structure, with each step in its own module:

| Step | File | What it does |
|---|---|---|
| Extract | [`etl/extract.py`](etl/extract.py) | Paginated requests to the DGEG API until every record is collected |
| Transform | [`etl/transform.py`](etl/transform.py) | Converts the JSON records into a pandas DataFrame and parses prices into numbers |
| Load | [`etl/load.py`](etl/load.py) | Writes a dated CSV snapshot, one file per run, never overwriting earlier days |
| Orchestration | [`pipeline.py`](pipeline.py) | Runs the three steps in sequence |

Example run:

```
Page 1: 10000 records (accumulated: 10000 / 13627)
Page 2: 3627 records (accumulated: 13627 / 13627)
Extract complete: 13627 records

Transform complete: 13627 rows, 16 columns

Saved 13627 rows to data/raw/fuel_prices_2026-10-04.csv
Pipeline finished.
```

### Design decisions

- **Append-only snapshots.** Each run adds a new dated file and never edits old ones, so history accumulates and can't be accidentally overwritten.
- **Raw values kept during transformation.** The original price string is kept next to the parsed number, so any parsing problem can be traced back to the source value. Only the clean column will go into the final tables.
- **Total read at runtime.** The record count changes daily, so the pipeline reads it from the API on every run instead of hardcoding it.

## Planned data model

The raw data is one flat table with station details repeated on every row. The next step models it as a **star schema** in PostgreSQL:

- `fact_precos`: one row per station, fuel type and day, with the price
- `dim_postos`: station details (name, brand, address, municipality, district, coordinates)
- `dim_combustivel`: fuel types
- `dim_data`: calendar attributes (day, weekday, month, year)

Dimensions are loaded before facts, so every price row points to existing station, fuel and date records.

## Roadmap

![Roadmap](docs/images/roadmap.png)

**Phase 1: Local MVP** *(in progress)*
- [x] Discover and document the DGEG API
- [x] Modular ETL in Python (requests, pandas)
- [x] Daily, dated CSV snapshots
- [ ] PostgreSQL star schema
- [ ] Streamlit dashboard
- [ ] Daily scheduling with GitHub Actions

**Phase 2: Cloud storage**
- [ ] Raw layer in Azure Blob Storage / Data Lake
- [ ] Bronze / silver / gold layers

**Phase 3: Distributed processing**
- [ ] Databricks + Spark transformations
- [ ] Delta Lake tables
- [ ] Orchestration with Databricks Workflows or Azure Data Factory
- [ ] Power BI dashboard

## Project structure

```
fuel-prices-pt/
├── etl/
│   ├── extract.py       # API requests and pagination
│   ├── transform.py     # cleaning and parsing
│   └── load.py          # dated CSV snapshots
├── pipeline.py          # runs the full ETL
├── notebooks/           # initial API exploration
├── notes/               # API discovery notes and work logs
├── docs/images/         # architecture and roadmap diagrams
└── requirements.txt
```

The `data/` folder is created when the pipeline runs and is excluded from version control.

## How to run

Requires Python 3.10+.

```bash
git clone https://github.com/amffpsa24-art/fuel-prices-pt.git
cd fuel-prices-pt

python -m venv .venv
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python pipeline.py
```

The output appears in `data/raw/`.

## Tech stack

**Now:** Python, requests, pandas, Git/GitHub
**Planned:** PostgreSQL, Streamlit, GitHub Actions, Azure, Databricks, Spark, Delta Lake

## Author

**André Francisco**: mechanical engineer (MSc, Instituto Superior Técnico) moving into data engineering.
[LinkedIn](https://www.linkedin.com/in/your-profile)
