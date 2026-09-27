# Day 3 Plan: GitHub + README

**Goal:** have the project public on GitHub with a proper README, ready to link in job applications.

**Starting point (end of Day 2, 27/09/2026):**
- Modular ETL working: `python pipeline.py` → `extract()` → `transform()` → `load()`
- ~13,900 records extracted in 2 API requests, saved as dated CSV snapshots in `data/raw/`
- First local commit done (14 files, branch `master`)

---

## 1. Housekeeping (~10 min)

- [ ] Run `git status` and confirm "working tree clean"
- [ ] Add to `notes/api-discovery.md`:
  - `qtdPorPagina=10000` accepted by the API (tested 27/09/2026), so a full extraction takes 2 requests
  - Total record count changes over time (13,604 → 14,118 → 13,881), so always read `Quantidade` at runtime, never hardcode it
- [ ] Tidy `notes/`:
  - Decide on `Step 1.py`, `htlm_pull.py`, `API_pull.py`: delete, or move to `notes/archive/`
  - Rename files with spaces (`Step 1.py` → `step_1.py`)

## 2. Push to GitHub (~20 min)

- [ ] On github.com, create a new **empty** repository (e.g. `fuel-prices-pt`)
  - Do NOT tick "Add a README" or "Add .gitignore". Both already exist locally, and ticking them causes a conflict on the first push.
- [ ] Rename the local branch to GitHub's default:
  ```
  git branch -M main
  ```
- [ ] Connect the local repo to GitHub and push:
  ```
  git remote add origin <repo URL>
  git push -u origin main
  ```
  A browser window will ask for the GitHub login on the first push.
- [ ] Refresh the repo page on GitHub and confirm the files are there (and that `data/` and `.venv/` are NOT)

## 3. Write the README (~30 min)

Sections to cover:

- [ ] **Title and one-line description:** what the project does
- [ ] **Motivation:** portfolio project for the transition into data engineering
- [ ] **Data source:** the DGEG fuel prices API, undocumented, discovered via browser DevTools (Network tab)
- [ ] **Architecture:** the three phases
  - Phase 1: Python + PostgreSQL + Streamlit + GitHub Actions *(in progress)*
  - Phase 2: Azure Blob Storage raw layer, bronze/silver/gold
  - Phase 3: Databricks/Spark, Delta Lake, orchestration
- [ ] **Project structure:** folder tree
- [ ] **How to run:**
  ```
  git clone <repo URL>
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  python pipeline.py
  ```
- [ ] **Roadmap:** checklist, with done items ticked

Then commit and push:
```
git add .
git commit -m "Add README"
git push
```

## 4. Stretch, if time allows (~10 min)

- [ ] Pin package versions: run `pip freeze`, copy the exact `requests` and `pandas` versions into `requirements.txt`
- [ ] Create `requirements-dev.txt` with `ipykernel` (needed for the notebook, not for the pipeline)

---

## After Day 3: the database step

- Install PostgreSQL locally
- Design the tables:
  - `dim_postos`: station-level fields (Id, Nome, Marca, TipoPosto, Morada, Localidade, CodPostal, Municipio, Distrito, Latitude, Longitude)
  - `fact_precos`: per-snapshot fields (Id as foreign key, Combustivel, Preco_num, DataAtualizacao)
- Change `load()` to write into PostgreSQL instead of CSV
- Then: schedule the pipeline to run daily