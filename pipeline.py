# PIPELINE: entry point that runs the full ETL in sequence
# Created: 27/09/2026
# Updated: 11/10/2026 (every run recorded in pipeline_runs; scheduled runs skip a day already loaded;
#                      quality checks before the database load; logging)
# Usage (from the project root, with .venv active):  python pipeline.py
# GitHub Actions passes --trigger schedule or --trigger backup (see .github/workflows/daily.yml).

import argparse
import logging
import os
from datetime import date

from etl import runs
from etl.extract import extract
from etl.load import load_postgres, save_raw_csv
from etl.quality import verificar
from etl.transform import transform

log = logging.getLogger("pipeline")


def run(triggered_by="manual", conninfo=None):
    """Runs extract -> transform -> checks -> load and records the run. conninfo: tests pass a test database."""
    # The day the data is labelled with. On GitHub Actions, TZ=Europe/Lisbon makes this the Portuguese date.
    snapshot_date = date.today()
    # Set automatically by GitHub Actions; links the run log row to its Actions log (None locally)
    github_run_id = os.environ.get("GITHUB_RUN_ID")

    # Scheduled runs stop if today is already loaded: the first successful snapshot of the day wins,
    # and DGEG doesn't get requests whose result would be thrown away. Manual runs always go ahead.
    if triggered_by != "manual" and runs.ja_carregado(snapshot_date, conninfo):
        runs.iniciar_run(snapshot_date, triggered_by, github_run_id, status="skipped", conninfo=conninfo)
        log.info("%s is already loaded: nothing to do", snapshot_date)
        return

    run_id = runs.iniciar_run(snapshot_date, triggered_by, github_run_id, conninfo=conninfo)
    log.info("Run %d started (%s) for %s", run_id, triggered_by, snapshot_date)
    registos = None
    try:
        # 1. Get the raw records from the DGEG API (retries temporary errors)
        registos = extract()
        log.info("Extract complete: %d records", len(registos))

        # 2. Clean them into a DataFrame
        df = transform(registos)
        log.info("Transform complete: %d rows, %d columns", df.shape[0], df.shape[1])

        # 3. Raw CSV first: kept even if the checks fail, to see what was wrong
        save_raw_csv(df, snapshot_date)

        # 4. Quality checks: a bad day stops here, before touching the warehouse
        verificar(df)

        # 5. PostgreSQL
        linhas = load_postgres(df, snapshot_date, conninfo)
    except Exception as e:
        # Record the failure, then re-raise so the GitHub Actions job is still marked as failed
        rows_extracted = len(registos) if registos is not None else None
        runs.terminar_run(run_id, "failed", rows_extracted=rows_extracted, error=f"{type(e).__name__}: {e}",
                          conninfo=conninfo)
        log.error("Run %d failed: %s: %s", run_id, type(e).__name__, e)
        raise

    runs.terminar_run(run_id, "success", rows_extracted=len(registos), rows_loaded=linhas, conninfo=conninfo)
    log.info("Run %d finished: %d price rows loaded", run_id, linhas)


# Only runs when this file is executed directly ("python pipeline.py"),
# not when another file imports it
if __name__ == "__main__":
    # Timestamp, level and module on every line, so a GitHub Actions log shows when and where things happened
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Daily fuel prices ETL")
    parser.add_argument("--trigger", choices=["schedule", "backup", "manual"], default="manual",
                        help="who started the run (recorded in pipeline_runs)")
    run(parser.parse_args().trigger)
