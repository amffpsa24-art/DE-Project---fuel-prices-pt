# PIPELINE: runs the full ETL once: extract -> bronze -> transform -> quality checks -> load
# Usage (from the project root, with .venv active):  python pipeline.py
# GitHub Actions passes --trigger schedule or --trigger backup (see .github/workflows/daily.yml).

import argparse
import logging
import os
from datetime import date

from etl.bronze import BronzeStore
from etl.extract import DgegExtractor
from etl.load import Warehouse
from etl.quality import DataQualityError, QualityChecker
from etl.runs import RunLog
from etl.transform import Transformer

log = logging.getLogger("pipeline")


class Pipeline:
    """Runs every step in order and records the run in pipeline_runs.

    Each step is an object passed in, so tests can swap any of them for a fake.
    """

    def __init__(self, extractor, transformer, checker, bronze_store, warehouse, run_log):
        self.extractor = extractor
        self.transformer = transformer
        self.checker = checker
        self.bronze_store = bronze_store
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
            warehouse=Warehouse(conninfo),
            run_log=RunLog(conninfo),
        )

    def run(self, triggered_by="manual"):
        # On GitHub Actions, TZ=Europe/Lisbon makes this the Portuguese date
        snapshot_date = date.today()
        # Set by GitHub Actions; links the run log row to its Actions log (None locally)
        github_run_id = os.environ.get("GITHUB_RUN_ID")

        # Scheduled runs stop if today is already loaded: the first successful snapshot of the day wins.
        # Manual runs always go ahead.
        if triggered_by != "manual" and self.run_log.is_loaded(snapshot_date):
            self.run_log.start(snapshot_date, triggered_by, github_run_id, status="skipped")
            log.info("%s is already loaded: nothing to do", snapshot_date)
            return

        run_id = self.run_log.start(snapshot_date, triggered_by, github_run_id)
        log.info("Run %d started (%s) for %s", run_id, triggered_by, snapshot_date)
        records = None
        try:
            # 1. Get the raw records from the DGEG API
            records = self.extractor.extract()
            log.info("Extract complete: %d records", len(records))
            if not records:
                raise DataQualityError("DGEG answered with no records")

            # 2. Bronze: DGEG's answer exactly as it came, before anything else can go wrong
            self.bronze_store.save(records, snapshot_date)

            # 3. Clean them into a DataFrame
            df = self.transformer.transform(records)
            log.info("Transform complete: %d rows, %d columns", df.shape[0], df.shape[1])

            # 4. Quality checks: a bad day stops here, before touching the warehouse
            self.checker.check(df)

            # 5. PostgreSQL
            rows_loaded = self.warehouse.load(df, snapshot_date)
        except Exception as e:
            # Record the failure, then re-raise so the GitHub Actions job is marked as failed
            rows_extracted = len(records) if records is not None else None
            self.run_log.finish(run_id, "failed", rows_extracted=rows_extracted, error=f"{type(e).__name__}: {e}")
            log.error("Run %d failed: %s: %s", run_id, type(e).__name__, e)
            raise

        self.run_log.finish(run_id, "success", rows_extracted=len(records), rows_loaded=rows_loaded)
        log.info("Run %d finished: %d price rows loaded", run_id, rows_loaded)


# Only runs when this file is executed directly ("python pipeline.py"), not when another file imports it
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Daily fuel prices ETL")
    parser.add_argument("--trigger", choices=["schedule", "backup", "manual"], default="manual",
                        help="who started the run (recorded in pipeline_runs)")
    Pipeline.default().run(parser.parse_args().trigger)
