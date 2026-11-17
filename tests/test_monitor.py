# Unit tests: the evening check that a day was loaded (no database: a fake run log)

from datetime import date, datetime

import pytest

from monitor import FreshnessMonitor


class FakeRunLog:
    """Stands in for RunLog: the days loaded, and the last run of each day as (triggered_by, status, error)."""

    def __init__(self, loaded=(), last_runs=None):
        self.loaded = set(loaded)
        self.last_runs = last_runs or {}

    def is_loaded(self, snapshot_date):
        return snapshot_date in self.loaded

    def last_run(self, snapshot_date):
        return self.last_runs.get(snapshot_date)


class FakeDgeg:
    """Stands in for DgegExtractor.is_available(): a fixed answer, no network."""

    def __init__(self, ok, error):
        self.answer = (ok, error)

    def is_available(self):
        return self.answer


TODAY, YESTERDAY = date(2026, 10, 16), date(2026, 10, 15)


class TestWhichDay:
    @pytest.mark.parametrize(
        "now, expected",
        [
            (datetime(2026, 10, 16, 19, 47), TODAY),    # the evening check, on time
            (datetime(2026, 10, 16, 23, 59), TODAY),    # started late, still the same day
            (datetime(2026, 10, 17, 1, 30), TODAY),     # started after midnight: checks the day that just ended
        ],
    )
    def test_checks_the_day_that_should_be_loaded(self, now, expected):
        assert FreshnessMonitor(FakeRunLog(), now).day_to_check() == expected


class TestCheck:
    now = datetime(2026, 10, 16, 19, 47)

    def test_a_loaded_day_is_fine(self):
        day, loaded, _ = FreshnessMonitor(FakeRunLog(loaded=[TODAY]), self.now).check()

        assert (day, loaded) == (TODAY, True)

    def test_a_day_with_no_run_at_all_is_reported(self):
        # The case GitHub never emails about: nothing ran, so nothing failed
        _, loaded, message = FreshnessMonitor(FakeRunLog(loaded=[YESTERDAY]), self.now).check()

        assert loaded is False
        assert "No run recorded" in message

    def test_a_failed_day_reports_the_error(self):
        # The alert says why, so the next step is obvious without opening the logs
        run_log = FakeRunLog(last_runs={TODAY: ("schedule", "failed", "DataQualityError: 5 duplicated station x fuel rows")})

        _, loaded, message = FreshnessMonitor(run_log, self.now).check()

        assert loaded is False
        assert "(schedule) ended as **failed**" in message
        assert "5 duplicated" in message
        assert "Run workflow" in message

    def test_says_a_manual_run_should_work_when_dgeg_answers(self):
        monitor = FreshnessMonitor(FakeRunLog(), self.now, dgeg=FakeDgeg(True, None))

        _, _, message = monitor.check()

        assert "DGEG is answering" in message
        assert "Run workflow** now" in message

    def test_says_to_wait_when_dgeg_is_down(self):
        # As on 30/10/2026: a manual run would fail the same way, so the alert says to wait for DGEG
        monitor = FreshnessMonitor(FakeRunLog(), self.now, dgeg=FakeDgeg(False, "HTTPError: 500 Server Error"))

        _, _, message = monitor.check()

        assert "DGEG is **not answering**" in message
        assert "HTTPError: 500" in message
        assert "as soon as DGEG answers again" in message
