# Day 4 Log: Git housekeeping + PostgreSQL setup

**Date:** 04/10/2026

**Goal:** clean up what Git tracks, publish the repo on GitHub, and get a local PostgreSQL database ready for the star schema.

**Starting point (end of Day 3):**
- Modular ETL working, saving dated CSV snapshots to `data/raw/`
- README written, but no GitHub remote yet and no database

---

## 1. Git housekeeping

- [x] `.gitignore` is spelled `.gitignore` (no dot in the middle). A file named `.git.ignore` is silently ignored by Git.
- [x] Added `*.code-workspace` to `.gitignore`: VS Code workspace settings are editor-specific, not part of the project
- [x] Decided to **track** `docs/` (the README shows `docs/images/architecture.png` and `roadmap.png`), so removed the `docs/` rule again
- [x] Added `.env` to `.gitignore` so database credentials never reach GitHub
- [x] Repo pushed to GitHub: https://github.com/amffpsa24-art/fuel-prices-pt (branch renamed `master` → `main`)

Commits today:

| Commit | Message |
|---|---|
| `ff6019f` | Ignore VS Code workspace files |
| `b9f7252` | Track docs images and stop ignoring docs folder |
| `1ae5d73` | Add README |

**Habit learned:** after saving a change, run `git status` and read it before committing:
- `modified`: tracked file changed → check it with `git diff <file>`
- `untracked`: new file Git doesn't know about yet → decide: commit it, or add it to `.gitignore`
- `deleted`: tracked file removed

## 2. PostgreSQL installation

- [x] Installed **PostgreSQL 18.6** with winget:
  ```
  winget install --id PostgreSQL.PostgreSQL.18 --exact
  ```
  Also installs **pgAdmin 4** (graphical client). Stack Builder was skipped.
- [x] Runs as the Windows service `postgresql-x64-18`, starts automatically on boot, port `5432`
- [x] Created the project database:
  ```sql
  CREATE DATABASE fuel_prices ENCODING 'UTF8';
  ```

## 3. Credentials

- Superuser `postgres` has a random 24-character password
- Stored in `.env` in the project root (git-ignored, **never commit it, never paste it into notes**):
  ```
  PGHOST=localhost
  PGPORT=5432
  PGUSER=postgres
  PGPASSWORD=<see .env>
  PGDATABASE=fuel_prices
  ```
- Also stored in `%APPDATA%\postgresql\pgpass.conf`, PostgreSQL's standard password file, so `psql` connects without asking. Format: `host:port:database:user:password`

## 4. Terminal setup + problems solved

| Problem | Cause | Fix |
|---|---|---|
| `psql : The term 'psql' is not recognized` | PostgreSQL's `bin` folder wasn't on PATH, and VS Code terminals keep the PATH from when VS Code was opened | Added `C:\Program Files\PostgreSQL\18\bin` to the user PATH, then **fully closed and reopened VS Code**. Quick fix for one terminal: `$env:Path += ";C:\Program Files\PostgreSQL\18\bin"` |
| Couldn't type the password | psql hides password input on purpose: nothing appears, not even `***` | Created `pgpass.conf` so no password is asked. (If ever needed: paste with right-click/Ctrl+V and press Enter, even though nothing shows.) |
| `WARNING: Console code page (850) differs from Windows code page (1252)` | Terminal and psql use different character sets; breaks Portuguese accents (Gasóleo, Évora…) | Created PowerShell profile `Documentos\WindowsPowerShell\profile.ps1` with `chcp 1252 \| Out-Null`, applied to every new terminal |

## 5. Useful psql commands

Connect: `psql -U postgres -d fuel_prices`

| Command | What it does |
|---|---|
| `\conninfo` | Current database, user and port |
| `\l` | List databases |
| `\dt` | List tables |
| `\d <table>` | Show a table's columns |
| `\q` | Quit |

---

## Next: the star schema

- [ ] Write the `CREATE TABLE` statements (dimensions first, then facts):
  - `dim_postos`: Id, Nome, Marca, TipoPosto, Morada, Localidade, CodPostal, Municipio, Distrito, Latitude, Longitude
  - `dim_combustivel`: fuel types
  - `dim_data`: day, weekday, month, year
  - `fact_precos`: station, fuel, date, price
- [ ] Add a Python PostgreSQL driver to `requirements.txt` (e.g. `psycopg` + `SQLAlchemy`) and read the connection settings from `.env`
- [ ] Change `load()` to write into PostgreSQL (keep the CSV snapshot as the raw copy)
- [ ] Update the README roadmap: tick "PostgreSQL star schema" when done
