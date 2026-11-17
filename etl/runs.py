# RUN LOG: records every pipeline run in pipeline_runs, for monitoring
#
# Each method opens its OWN connection, separate from the load's transaction. If a load fails, its transaction
# is rolled back; a "failed" row written inside it would be rolled back too, and failures would be invisible.

import psycopg

from etl.load import resolve_conninfo


class RunLog:
    """The pipeline_runs table: one row per run, with its trigger, outcome and row counts."""

    def __init__(self, conninfo=None):
        self.conninfo = resolve_conninfo(conninfo)

    def is_loaded(self, snapshot_date):
        """True if a run already loaded this day successfully."""
        with psycopg.connect(self.conninfo) as conn:
            row = conn.execute(
                "SELECT 1 FROM pipeline_runs WHERE snapshot_date = %s AND status = 'success' LIMIT 1",
                (snapshot_date,),
            ).fetchone()
        return row is not None

    def last_run(self, snapshot_date):
        """The day's most recent run as (triggered_by, status, error), or None if no run recorded it."""
        with psycopg.connect(self.conninfo) as conn:
            return conn.execute(
                """
                SELECT triggered_by, status, error FROM pipeline_runs
                WHERE snapshot_date = %s ORDER BY run_id DESC LIMIT 1
                """,
                (snapshot_date,),
            ).fetchone()

    def start(self, snapshot_date, triggered_by, github_run_id=None, status="running"):
        """Adds the run's row and returns its run_id. A skipped run is recorded as already finished."""
        with psycopg.connect(self.conninfo, autocommit=True) as conn:
            return conn.execute(
                """
                INSERT INTO pipeline_runs (snapshot_date, triggered_by, github_run_id, status, finished_at)
                VALUES (%s, %s, %s, %s, CASE WHEN %s THEN now() END)
                RETURNING run_id
                """,
                (snapshot_date, triggered_by, github_run_id, status, status != "running"),
            ).fetchone()[0]

    def finish(self, run_id, status, rows_extracted=None, rows_loaded=None, error=None):
        """Closes the run's row with its outcome."""
        with psycopg.connect(self.conninfo, autocommit=True) as conn:
            conn.execute(
                """
                UPDATE pipeline_runs
                SET finished_at = now(), status = %s, rows_extracted = %s, rows_loaded = %s, error = %s
                WHERE run_id = %s
                """,
                (status, rows_extracted, rows_loaded, error, run_id),
            )
