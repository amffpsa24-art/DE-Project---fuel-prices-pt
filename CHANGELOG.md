# Changelog

How the project changed over time, newest first. Each entry says what changed and, where it isn't obvious, why. Dates are in Lisbon time.

## Unreleased

### Planned
- Remove the CSV raw layer (`RawStore`) once Azure has a few weeks of bronze, and make `backfill.py` read the bronze JSON instead
- Explicit bronze / silver / gold layers (Phase 2)
- Databricks + Spark, Delta Lake tables, orchestration, Power BI (Phase 3)
- Move the long-term price history out of Neon before it reaches the plan's storage limit

## 2026-10-31: Bronze layer in Azure, hardening after the DGEG outage

### Added
- **Bronze layer** (`etl/bronze.py`): DGEG's answer, untouched, saved right after the extract as gzipped JSON Lines in Azure Blob Storage (`bronze/dgeg_pesquisar_postos/date=YYYY-MM-DD/`). GitHub deletes artifacts after 90 days and DGEG keeps no history, so this was the one layer that couldn't wait. If Azure fails, the day is still loaded into Neon and the run log says why bronze wasn't saved.
- **Archive workflow** (`archive-artifacts.yml`): copies the old artifact CSVs to `bronze/legacy_artifacts/` before they expire. Safe to run again.
- **Pinned dependencies** in all three requirements files, with **Dependabot** opening one grouped pull request a week.
- `DgegExtractor.disponivel()`: a one-row check that tells the missing-day issue whether DGEG is answering right now.
- A warning when fewer rows reach `fact_precos` than were staged (a day loaded out of date order quietly loses prices because of SCD Type 2).

### Changed
- **Earlier schedule:** main run 13:17 → 10:17 UTC, backup 16:17 → 13:17 UTC. GitHub was starting them 4–6 hours late, leaving only about 3 hours before midnight.
- **Longer retries:** pauses of 30 s, 2 min and 5 min (was 10 s and 30 s), so a run rides out an outage of about 8 minutes. Job timeout 15 → 20 min.
- **Request timeout 30 → 60 s.** DGEG's server gives up at 30 s, so the log now shows its HTTP 500 instead of a timeout on our side.
- **One alert per missing day:** the monitor run only fails (and sends GitHub's email) when it opens a new issue.
- Azure uses a **SAS key** with no delete permission instead of the account key.
- `backfill.py` runs the same quality checks as the daily run and skips days that fail them.

### Fixed
- An empty answer from DGEG fails with `DGEG answered with no records` instead of `KeyError: 'Preco'`.

68 tests (was 53).

## 2026-10-30: Incident, DGEG API down

Both daily runs failed. DGEG's price search (`PesquisarPostos`) returned HTTP 500 after exactly 30 seconds for every request, while the rest of their site worked. The evening monitor opened issue #1. **The day is lost**, since DGEG keeps no history. The fixes are in the 2026-10-31 entry.

## 2026-10-16: OOP refactor, missing-day alert

### Added
- **Evening monitor** (`monitor.py`, `monitor.yml`): at 18:47 and 21:47 UTC it checks `pipeline_runs` for a successful snapshot of the day. If there isn't one, it opens a GitHub issue that says why. A later check closes the issue if a late run loaded the day after all.

### Changed
- **Object-oriented ETL:** one class per step (`DgegExtractor`, `Transformer`, `QualityChecker`, `RawStore`, `Warehouse`, `RunLog`), passed into `Pipeline` so tests can swap any of them.
- **The whole day in one request:** 20,000 records per page instead of 10,000.

### Fixed
- **Page overlaps.** DGEG's sort order isn't stable, so with two pages a few rows from the end of page 1 came back at the start of page 2, and as many were skipped. The duplicate check caught it and stopped the run. One page avoids it.

## 2026-10-14

### Fixed
- `limpar_preco` returns `NaN` for a missing or empty price instead of failing, with a test.

## 2026-10-11: Run log, quality checks, retries

### Added
- **Run log** (`pipeline_runs`): one row per run with times, snapshot date, trigger, status, rows extracted and loaded, the error and the GitHub run ID. Written on its own connection, so a failed load still leaves a "failed" row.
- **Backup run** that skips a day already loaded. The first successful snapshot of the day wins.
- **Quality checks** (`etl/quality.py`) that stop a bad day before the database: 12,000–16,000 rows, all columns present, no empty required fields, prices between 0.50 and 5.00 €, no duplicated station × fuel.
- **Retries** for connection errors, timeouts and 5xx responses. A 4xx fails at once.
- **Logging** with timestamp, level and module instead of `print`.
- Published `notes/api-discovery.md` and the exploration notebook. The work logs stay private.
- `.streamlit/secrets.toml.example`.

### Changed
- **Schedule moved from 19:17 UTC to 13:17 UTC** (main) + 16:17 UTC (backup). GitHub started the 19:17 runs 3–5 hours late, some after midnight in Lisbon.
- Database tests skip within 3 seconds when no test database is running, instead of hanging.
- Dev container: Python 3.14 and all dependencies.

39 tests (was 22).

## 2026-10-08 – 2026-10-09: Tests and CI

### Added
- **pytest** suite with unit tests and database tests.
- **CI on every push** (`ci.yml`): Ruff lint and the tests against a PostgreSQL service in GitHub Actions.
- README: Testing section, CI badge, dashboard screenshot.

## 2026-10-05 – 2026-10-06: Clean-up

### Added
- Dev container for GitHub Codespaces.

### Changed
- Cleaned up the ETL, SQL scripts and workflow, and their comments.
- The `notes/` work logs are no longer tracked.

### Known gap
- **No snapshot for 2026-10-05.** GitHub started that day's run after midnight in Lisbon, so it was labelled 2026-10-06. This led to the run log and the earlier schedule on 2026-10-11.

## 2026-10-04: Phase 1 complete

The biggest day: from CSV files on a laptop to a hosted warehouse, a daily schedule and a public dashboard.

### Added
- Repository published on GitHub, with a README and the MIT License.
- **Star schema** in PostgreSQL (`sql/schema.sql`): `fact_precos` (one row per station × fuel × day) with `dim_postos`, `dim_combustivel` and `dim_data`. Prices as `NUMERIC(6,3)`, never `FLOAT`.
- **Loading through staging:** `COPY` into `stg_precos`, then `sql/load_from_staging.sql` moves it into the star schema in one transaction. Idempotent: a rerun never duplicates rows.
- `backfill.py`: reloads every raw CSV, oldest first.
- **Station history with SCD Type 2** in `dim_postos`, so old prices keep the brand and name the station had at the time. Neon was rebuilt from the raw CSVs to switch over.
- **Hosted database on Neon** and a **daily GitHub Actions workflow** (19:17 UTC), with credentials in GitHub Secrets and the raw CSV kept as an artifact.
- **Read layer:** the `vw_precos` view and a `dashboard_reader` user that can only read.
- **Streamlit dashboard** at [fuel-prices-pt.streamlit.app](https://fuel-prices-pt.streamlit.app/): map, price evolution, stations with CSV download, price changes, station history, brands.
- Architecture, ERD, medallion and roadmap diagrams.

## 2026-09-27: First pipeline

### Added
- Modular ETL in Python (`extract` → `transform` → `load`) with requests and pandas.
- Dated CSV snapshot of every price in Portugal in `data/raw/`, about 13,900 rows from 2 requests of 10,000 records each.
- First manual snapshot.

## 2026-09-11 – 2026-09-12: API discovery

No code yet. DGEG publishes no documented API, so the endpoint was found in the browser's DevTools, from the requests the price search page makes.
- `PesquisarPostos` returns every station × fuel in Portugal when the district filter is left empty.
- `Quantidade` is the total number of matching rows, repeated on every row, so it says how many pages to fetch.
- One row = one station × one fuel. That defines the grain of the fact table and the split into station and fuel dimensions.
- The page size can be raised from 50 to 1,000 and more, so a full download takes a handful of requests instead of 273.

Details in [notes/api-discovery.md](notes/api-discovery.md).
