# PIPELINE: entry point that runs the full ETL in sequence
# Created: 27/09/2026
# Updated: 11/10/2026 (every run recorded in pipeline_runs; scheduled runs skip a day already loaded;
#                      quality checks before the database load; logging)
# Updated: 16/10/2026 (Pipeline class: each step is an object passed in, so tests can swap any of them)
# Updated: 31/10/2026 (bronze layer: DGEG's raw answer saved right after the extract, and uploaded to Azure)
# Usage (from the project root, with .venv active):  python pipeline.py
# GitHub Actions passes --trigger schedule or --trigger backup (see .github/workflows/daily.yml).

import argparse
import logging
import os
from datetime import date

from etl.bronze import BronzeStore
from etl.extract import DgegExtractor
from etl.load import RawStore, Warehouse
from etl.quality import QualityChecker
from etl.runs import RunLog
from etl.transform import Transformer

log = logging.getLogger("pipeline")


class BronzeError(Exception):
    """The day was loaded, but DGEG's raw answer didn't reach the bronze layer."""


class Pipeline:
    """Runs extract -> bronze -> transform -> checks -> load, and records every run in pipeline_runs."""

    def __init__(self, extractor, transformer, checker, raw_store, warehouse, run_log, bronze_store):
        self.extractor = extractor
        self.transformer = transformer
        self.checker = checker
        self.bronze_store = bronze_store
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
            bronze_store=BronzeStore.default(),
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

            # 2. Bronze: DGEG's answer exactly as it came, before anything else can go wrong
            erro_bronze = self._guardar_bronze(registos, snapshot_date)

            # 3. Clean them into a DataFrame
            df = self.transformer.transform(registos)
            log.info("Transform complete: %d rows, %d columns", df.shape[0], df.shape[1])

            # 4. Raw CSV first: kept even if the checks fail, to see what was wrong
            self.raw_store.save(df, snapshot_date)

            # 5. Quality checks: a bad day stops here, before touching the warehouse
            self.checker.verificar(df)

            # 6. PostgreSQL
            linhas = self.warehouse.load(df, snapshot_date)
        except Exception as e:
            # Record the failure, then re-raise so the GitHub Actions job is still marked as failed
            rows_extracted = len(registos) if registos is not None else None
            self.run_log.terminar(run_id, "failed", rows_extracted=rows_extracted, error=f"{type(e).__name__}: {e}")
            log.error("Run %d failed: %s: %s", run_id, type(e).__name__, e)
            raise

        if erro_bronze is not None:
            # The day is loaded (the monitor stays quiet), but the job must still turn red so GitHub emails:
            # the raw JSON is only in this run's artifact, which GitHub deletes after 90 days
            mensagem = f"Bronze not saved: {type(erro_bronze).__name__}: {erro_bronze}"
            self.run_log.terminar(run_id, "success", rows_extracted=len(registos), rows_loaded=linhas, error=mensagem)
            raise BronzeError(f"{mensagem}. The day is loaded; copy data/bronze/ from this run's artifact to Azure.")

        self.run_log.terminar(run_id, "success", rows_extracted=len(registos), rows_loaded=linhas)
        log.info("Run %d finished: %d price rows loaded", run_id, linhas)

    def _guardar_bronze(self, registos, snapshot_date):
        """Saves the raw answer. A failure (e.g. Azure down) doesn't stop the load, or the day would be lost
        everywhere: it's logged and returned, and run() fails the job once the day is loaded."""
        try:
            self.bronze_store.save(registos, snapshot_date)
            return None
        except Exception as e:
            log.error("Bronze save failed, the load goes ahead: %s: %s", type(e).__name__, e)
            return e


# Only runs when this file is executed directly ("python pipeline.py"),
# not when another file imports it
if __name__ == "__main__":
    # Timestamp, level and module on every line, so a GitHub Actions log shows when and where things happened
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Daily fuel prices ETL")
    parser.add_argument("--trigger", choices=["schedule", "backup", "manual"], default="manual",
                        help="who started the run (recorded in pipeline_runs)")
    Pipeline.default().run(parser.parse_args().trigger)
