# RUN LOG: records every pipeline run in pipeline_runs, for monitoring
# Created: 11/10/2026
#
# Each function opens its OWN connection with autocommit, separate from the load's transaction.
# Why: if a load fails, its transaction is rolled back. A "failed" row written inside it would be
# rolled back too, and failures would become invisible.

import psycopg

from etl.load import resolver_conninfo


def ja_carregado(snapshot_date, conninfo=None):
    """True if a run already loaded this day successfully."""
    with psycopg.connect(resolver_conninfo(conninfo)) as conn:
        row = conn.execute(
            "SELECT 1 FROM pipeline_runs WHERE snapshot_date = %s AND status = 'success' LIMIT 1",
            (snapshot_date,),
        ).fetchone()
    return row is not None


def iniciar_run(snapshot_date, triggered_by, github_run_id=None, status="running", conninfo=None):
    """Adds the run's row and returns its run_id. A skipped run is recorded as already finished."""
    with psycopg.connect(resolver_conninfo(conninfo), autocommit=True) as conn:
        return conn.execute(
            """
            INSERT INTO pipeline_runs (snapshot_date, triggered_by, github_run_id, status, finished_at)
            VALUES (%s, %s, %s, %s, CASE WHEN %s THEN now() END)
            RETURNING run_id
            """,
            (snapshot_date, triggered_by, github_run_id, status, status != "running"),
        ).fetchone()[0]


def terminar_run(run_id, status, rows_extracted=None, rows_loaded=None, error=None, conninfo=None):
    """Closes the run's row with its outcome."""
    with psycopg.connect(resolver_conninfo(conninfo), autocommit=True) as conn:
        conn.execute(
            """
            UPDATE pipeline_runs
            SET finished_at = now(), status = %s, rows_extracted = %s, rows_loaded = %s, error = %s
            WHERE run_id = %s
            """,
            (status, rows_extracted, rows_loaded, error, run_id),
        )
