# PIPELINE: entry point that runs the full ETL in sequence
# Created: 27/09/2026
# Updated: 11/10/2026 (every run recorded in pipeline_runs; scheduled runs skip a day already loaded;
#                      quality checks before the database load; logging)
# Updated: 16/10/2026 (Pipeline class: each step is an object passed in, so tests can swap any of them)
# Usage (from the project root, with .venv active):  python pipeline.py
# GitHub Actions passes --trigger schedule or --trigger backup (see .github/workflows/daily.yml).

import argparse
import logging
import os
from datetime import date

from etl.extract import DgegExtractor
from etl.load import RawStore, Warehouse
from etl.quality import QualityChecker
from etl.runs import RunLog
from etl.transform import Transformer

log = logging.getLogger("pipeline")


class Pipeline:
    """Runs extract -> transform -> checks -> load, and records every run in pipeline_runs."""

    def __init__(self, extractor, transformer, checker, raw_store, warehouse, run_log):
        self.extractor = extractor
        self.transformer = transformer
        self.checker = checker
        self.raw_store = raw_store
        self.warehouse = warehouse
        self.run_log = run_log

    @classmethod
    def default(cls, conninfo=None):
        """The production setup. conninfo: None = the real database (.env or the environment)."""
        return cls(
            extractor=DgegExtractor(),
            transformer=Transformer(),
            checker=QualityChecker(),
            raw_store=RawStore(),
            warehouse=Warehouse(conninfo),
            run_log=RunLog(conninfo),
        )

    def run(self, triggered_by="manual"):
        # The day the data is labelled with. On GitHub Actions, TZ=Europe/Lisbon makes this the Portuguese date.
        snapshot_date = date.today()
        # Set automatically by GitHub Actions; links the run log row to its Actions log (None locally)
        github_run_id = os.environ.get("GITHUB_RUN_ID")

        # Scheduled runs stop if today is already loaded: the first successful snapshot of the day wins,
        # and DGEG doesn't get requests whose result would be thrown away. Manual runs always go ahead.
        if triggered_by != "manual" and self.run_log.ja_carregado(snapshot_date):
            self.run_log.iniciar(snapshot_date, triggered_by, github_run_id, status="skipped")
            log.info("%s is already loaded: nothing to do", snapshot_date)
            return

        run_id = self.run_log.iniciar(snapshot_date, triggered_by, github_run_id)
        log.info("Run %d started (%s) for %s", run_id, triggered_by, snapshot_date)
        registos = None
        try:
            # 1. Get the raw records from the DGEG API (retries temporary errors)
            registos = self.extractor.extract()
            log.info("Extract complete: %d records", len(registos))

            # 2. Clean them into a DataFrame
            df = self.transformer.transform(registos)
            log.info("Transform complete: %d rows, %d columns", df.shape[0], df.shape[1])

            # 3. Raw CSV first: kept even if the checks fail, to see what was wrong
            self.raw_store.save(df, snapshot_date)

            # 4. Quality checks: a bad day stops here, before touching the warehouse
            self.checker.verificar(df)

            # 5. PostgreSQL
            linhas = self.warehouse.load(df, snapshot_date)
        except Exception as e:
            # Record the failure, then re-raise so the GitHub Actions job is still marked as failed
            rows_extracted = len(registos) if registos is not None else None
            self.run_log.terminar(run_id, "failed", rows_extracted=rows_extracted, error=f"{type(e).__name__}: {e}")
            log.error("Run %d failed: %s: %s", run_id, type(e).__name__, e)
            raise

        self.run_log.terminar(run_id, "success", rows_extracted=len(registos), rows_loaded=linhas)
        log.info("Run %d finished: %d price rows loaded", run_id, linhas)


# Only runs when this file is executed directly ("python pipeline.py"),
# not when another file imports it
if __name__ == "__main__":
    # Timestamp, level and module on every line, so a GitHub Actions log shows when and where things happened
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Daily fuel prices ETL")
    parser.add_argument("--trigger", choices=["schedule", "backup", "manual"], default="manual",
                        help="who started the run (recorded in pipeline_runs)")
    Pipeline.default().run(parser.parse_args().trigger)
