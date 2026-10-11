# ============================================
# Database tests: the run log (pipeline_runs) and skipping a day that's already loaded
# ============================================
# Created: 11/10/2026
# The whole pipeline runs here, but with a fake extract (no call to DGEG) and the test database.

import psycopg
import pytest
import requests

import etl.load as load_module
import pipeline
from tests.conftest import make_record, query


@pytest.fixture
def fake_extract(monkeypatch, tmp_path):
    """
    Replaces the DGEG extract with one that returns `registos` and counts its calls.
    Also sends the raw CSV to a temporary folder instead of data/raw.
    """
    estado = {"registos": [make_record(posto_id=1), make_record(posto_id=2, nome="Posto B")], "chamadas": 0}

    def extract():
        estado["chamadas"] += 1
        if isinstance(estado["registos"], Exception):
            raise estado["registos"]   # simulate DGEG failing
        return estado["registos"]

    # pipeline did "from etl.extract import extract", so the name to replace lives in pipeline
    monkeypatch.setattr(pipeline, "extract", extract)
    monkeypatch.setattr(load_module, "PASTA_RAW", tmp_path)
    return estado


def runs_log(db):
    """Every row of the run log, oldest first, with the columns the tests check."""
    return query(db, """
        SELECT triggered_by, status, rows_extracted, rows_loaded, error IS NOT NULL, finished_at IS NOT NULL
        FROM pipeline_runs ORDER BY run_id
    """)


def test_a_successful_run_is_recorded(db, fake_extract):
    pipeline.run("schedule", conninfo=db)

    # (trigger, status, rows extracted, rows loaded, has error, finished)
    assert runs_log(db) == [("schedule", "success", 2, 2, False, True)]


def test_a_scheduled_run_skips_a_day_already_loaded(db, fake_extract):
    # The backup run must not call DGEG again when the main run already loaded today
    pipeline.run("schedule", conninfo=db)
    pipeline.run("backup", conninfo=db)

    assert fake_extract["chamadas"] == 1
    assert [r[:2] for r in runs_log(db)] == [("schedule", "success"), ("backup", "skipped")]


def test_a_manual_run_always_goes_ahead(db, fake_extract):
    # Manual runs never skip (e.g. rerunning on purpose); idempotency keeps the data unchanged
    pipeline.run("schedule", conninfo=db)
    pipeline.run("manual", conninfo=db)

    assert fake_extract["chamadas"] == 2
    assert [r[:2] for r in runs_log(db)] == [("schedule", "success"), ("manual", "success")]
    assert query(db, "SELECT COUNT(*) FROM fact_precos")[0][0] == 2


def test_a_failed_load_is_still_recorded_as_failed(db, fake_extract):
    # The key design point: the load's transaction rolls back, but the run log row survives,
    # because it's written on a separate connection
    fake_extract["registos"] = [make_record(posto_id=1), make_record(posto_id=2, preco="-1,000 €")]

    with pytest.raises(psycopg.errors.CheckViolation):
        pipeline.run("schedule", conninfo=db)

    assert runs_log(db) == [("schedule", "failed", 2, None, True, True)]
    assert query(db, "SELECT COUNT(*) FROM fact_precos")[0][0] == 0   # the load itself left nothing behind


def test_a_failed_extract_is_recorded_as_failed(db, fake_extract):
    fake_extract["registos"] = requests.HTTPError("503 error")

    with pytest.raises(requests.HTTPError):
        pipeline.run("schedule", conninfo=db)

    (error,) = query(db, "SELECT error FROM pipeline_runs")[0]
    assert error == "HTTPError: 503 error"   # the message is kept, to see why at a glance


def test_a_failed_run_does_not_count_as_loaded(db, fake_extract):
    # After a failure, the backup run must try again instead of skipping
    fake_extract["registos"] = requests.HTTPError("503 error")
    with pytest.raises(requests.HTTPError):
        pipeline.run("schedule", conninfo=db)

    fake_extract["registos"] = [make_record(posto_id=1)]
    pipeline.run("backup", conninfo=db)

    assert [r[:2] for r in runs_log(db)] == [("schedule", "failed"), ("backup", "success")]
