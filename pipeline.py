# PIPELINE: entry point that runs the full ETL in sequence
# Created: 27/09/2026
# Updated: 11/10/2026 (every run recorded in pipeline_runs; scheduled runs skip a day already loaded)
# Usage (from the project root, with .venv active):  python pipeline.py
# GitHub Actions passes --trigger schedule or --trigger backup (see .github/workflows/daily.yml).

import argparse
import os
from datetime import date

from etl import runs
from etl.extract import extract
from etl.load import load
from etl.transform import transform


def run(triggered_by="manual", conninfo=None):
    """Runs extract -> transform -> load and records the run. conninfo: tests pass a test database."""
    # The day the data is labelled with. On GitHub Actions, TZ=Europe/Lisbon makes this the Portuguese date.
    snapshot_date = date.today()
    # Set automatically by GitHub Actions; links the run log row to its Actions log (None locally)
    github_run_id = os.environ.get("GITHUB_RUN_ID")

    # Scheduled runs stop if today is already loaded: the first successful snapshot of the day wins,
    # and DGEG doesn't get requests whose result would be thrown away. Manual runs always go ahead.
    if triggered_by != "manual" and runs.ja_carregado(snapshot_date, conninfo):
        runs.iniciar_run(snapshot_date, triggered_by, github_run_id, status="skipped", conninfo=conninfo)
        print(f"{snapshot_date} is already loaded: nothing to do.")
        return

    run_id = runs.iniciar_run(snapshot_date, triggered_by, github_run_id, conninfo=conninfo)
    registos = None
    try:
        # 1. Get the raw records from the DGEG API
        registos = extract()
        print(f"Extract complete: {len(registos)} records\n")

        # 2. Clean them into a DataFrame
        df = transform(registos)
        print(f"Transform complete: {df.shape[0]} rows, {df.shape[1]} columns\n")

        # 3. Raw CSV + PostgreSQL
        linhas = load(df, snapshot_date, conninfo)
    except Exception as e:
        # Record the failure, then re-raise so the GitHub Actions job is still marked as failed
        rows_extracted = len(registos) if registos is not None else None
        runs.terminar_run(run_id, "failed", rows_extracted=rows_extracted, error=f"{type(e).__name__}: {e}",
                          conninfo=conninfo)
        raise

    runs.terminar_run(run_id, "success", rows_extracted=len(registos), rows_loaded=linhas, conninfo=conninfo)
    print("Pipeline finished.")


# Only runs when this file is executed directly ("python pipeline.py"),
# not when another file imports it
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily fuel prices ETL")
    parser.add_argument("--trigger", choices=["schedule", "backup", "manual"], default="manual",
                        help="who started the run (recorded in pipeline_runs)")
    run(parser.parse_args().trigger)
