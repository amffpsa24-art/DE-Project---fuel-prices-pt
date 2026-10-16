# ============================================
# Database tests: the run log (pipeline_runs) and skipping a day that's already loaded
# ============================================
# Created: 11/10/2026
# Updated: 16/10/2026 (tests grouped in classes; fakes passed to Pipeline instead of monkeypatched)
# The whole pipeline runs here, but with a fake extractor (no call to DGEG) and the test database.

from datetime import date

import psycopg
import pytest
import requests

from etl.load import RawStore, Warehouse
from etl.quality import DataQualityError, QualityChecker
from etl.runs import RunLog
from etl.transform import Transformer
from pipeline import Pipeline
from tests.conftest import make_record, query


class FakeExtractor:
    """Stands in for DgegExtractor: returns `registos` (or raises it, if it's an exception) and counts its calls."""

    def __init__(self):
        self.registos = [make_record(posto_id=1), make_record(posto_id=2, nome="Posto B")]
        self.chamadas = 0

    def extract(self):
        self.chamadas += 1
        if isinstance(self.registos, Exception):
            raise self.registos   # simulate DGEG failing
        return self.registos


class NoChecks:
    """Stands in for QualityChecker when a test needs a bad day to reach the database."""

    def verificar(self, df):
        pass


@pytest.fixture
def extractor():
    return FakeExtractor()


@pytest.fixture
def pipeline(db, extractor, tmp_path):
    """The real pipeline on the test database, with the fake extractor and the raw CSV in a temporary folder."""
    return Pipeline(
        extractor=extractor,
        transformer=Transformer(),
        checker=QualityChecker(min_registos=1),   # small samples instead of a full day's ~13,500 rows
        raw_store=RawStore(tmp_path),
        warehouse=Warehouse(db),
        run_log=RunLog(db),
    )


def runs_log(db):
    """Every row of the run log, oldest first, with the columns the tests check."""
    return query(db, """
        SELECT triggered_by, status, rows_extracted, rows_loaded, error IS NOT NULL, finished_at IS NOT NULL
        FROM pipeline_runs ORDER BY run_id
    """)


class TestSuccessfulRuns:
    def test_a_successful_run_is_recorded(self, db, pipeline):
        pipeline.run("schedule")

        # (trigger, status, rows extracted, rows loaded, has error, finished)
        assert runs_log(db) == [("schedule", "success", 2, 2, False, True)]

    def test_a_scheduled_run_skips_a_day_already_loaded(self, db, pipeline, extractor):
        # The backup run must not call DGEG again when the main run already loaded today
        pipeline.run("schedule")
        pipeline.run("backup")

        assert extractor.chamadas == 1
        assert [r[:2] for r in runs_log(db)] == [("schedule", "success"), ("backup", "skipped")]

    def test_a_manual_run_always_goes_ahead(self, db, pipeline, extractor):
        # Manual runs never skip (e.g. rerunning on purpose); idempotency keeps the data unchanged
        pipeline.run("schedule")
        pipeline.run("manual")

        assert extractor.chamadas == 2
        assert [r[:2] for r in runs_log(db)] == [("schedule", "success"), ("manual", "success")]
        assert query(db, "SELECT COUNT(*) FROM fact_precos")[0][0] == 2


class TestFailedRuns:
    def test_a_failed_load_is_still_recorded_as_failed(self, db, pipeline, extractor):
        # The key design point: the load's transaction rolls back, but the run log row survives,
        # because it's written on a separate connection.
        # The quality checks would catch a negative price first, so they're switched off here
        # to make the database itself reject it (CHECK preco > 0) inside the transaction.
        pipeline.checker = NoChecks()
        extractor.registos = [make_record(posto_id=1), make_record(posto_id=2, preco="-1,000 €")]

        with pytest.raises(psycopg.errors.CheckViolation):
            pipeline.run("schedule")

        assert runs_log(db) == [("schedule", "failed", 2, None, True, True)]
        assert query(db, "SELECT COUNT(*) FROM fact_precos")[0][0] == 0   # the load itself left nothing behind

    def test_a_failed_extract_is_recorded_as_failed(self, db, pipeline, extractor):
        extractor.registos = requests.HTTPError("503 error")

        with pytest.raises(requests.HTTPError):
            pipeline.run("schedule")

        (error,) = query(db, "SELECT error FROM pipeline_runs")[0]
        assert error == "HTTPError: 503 error"   # the message is kept, to see why at a glance
        # ...and RunLog.ultimo hands it to the evening monitor, for the alert
        assert RunLog(db).ultimo(date.today()) == ("schedule", "failed", "HTTPError: 503 error")

    def test_a_failed_run_does_not_count_as_loaded(self, db, pipeline, extractor):
        # After a failure, the backup run must try again instead of skipping
        extractor.registos = requests.HTTPError("503 error")
        with pytest.raises(requests.HTTPError):
            pipeline.run("schedule")

        extractor.registos = [make_record(posto_id=1)]
        pipeline.run("backup")

        assert [r[:2] for r in runs_log(db)] == [("schedule", "failed"), ("backup", "success")]

    def test_a_day_failing_the_quality_checks_is_not_loaded(self, db, pipeline, extractor, tmp_path):
        # A price parsed as 11.64 stops the run before the database: nothing loaded, the run recorded as failed
        extractor.registos = [make_record(posto_id=1), make_record(posto_id=2, preco="11,64 €")]

        with pytest.raises(DataQualityError):
            pipeline.run("schedule")

        assert runs_log(db) == [("schedule", "failed", 2, None, True, True)]
        assert query(db, "SELECT COUNT(*) FROM fact_precos")[0][0] == 0
        # The raw CSV is still saved, to see what was wrong
        assert len(list(tmp_path.glob("fuel_prices_*.csv"))) == 1
