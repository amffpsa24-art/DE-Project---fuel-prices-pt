# ============================================
# Unit tests: the evening check that a day was loaded (no database: a fake run log)
# ============================================
# Created: 16/10/2026

from datetime import date, datetime

import pytest

from monitor import FreshnessMonitor


class FakeRunLog:
    """Stands in for RunLog: the days loaded, and the last run of each day as (triggered_by, status, error)."""

    def __init__(self, carregados=(), ultimos=None):
        self.carregados = set(carregados)
        self.ultimos = ultimos or {}

    def ja_carregado(self, snapshot_date):
        return snapshot_date in self.carregados

    def ultimo(self, snapshot_date):
        return self.ultimos.get(snapshot_date)


HOJE, ONTEM = date(2026, 10, 16), date(2026, 10, 15)


class TestWhichDay:
    @pytest.mark.parametrize(
        "agora, esperado",
        [
            (datetime(2026, 10, 16, 19, 47), HOJE),    # the evening check, on time
            (datetime(2026, 10, 16, 23, 59), HOJE),    # started late, still the same day
            (datetime(2026, 10, 17, 1, 30), HOJE),     # started after midnight: checks the day that just ended
        ],
    )
    def test_checks_the_day_that_should_be_loaded(self, agora, esperado):
        assert FreshnessMonitor(FakeRunLog(), agora).dia_a_verificar() == esperado


class TestVerificar:
    agora = datetime(2026, 10, 16, 19, 47)

    def test_a_loaded_day_is_fine(self):
        dia, carregado, _ = FreshnessMonitor(FakeRunLog(carregados=[HOJE]), self.agora).verificar()

        assert (dia, carregado) == (HOJE, True)

    def test_a_day_with_no_run_at_all_is_reported(self):
        # The case GitHub never emails about: nothing ran, so nothing failed
        _, carregado, mensagem = FreshnessMonitor(FakeRunLog(carregados=[ONTEM]), self.agora).verificar()

        assert carregado is False
        assert "No run recorded" in mensagem

    def test_a_failed_day_reports_the_error(self):
        # The alert says why, so the next step is obvious without opening the logs
        run_log = FakeRunLog(ultimos={HOJE: ("schedule", "failed", "DataQualityError: 5 duplicated station x fuel rows")})

        _, carregado, mensagem = FreshnessMonitor(run_log, self.agora).verificar()

        assert carregado is False
        assert "(schedule) ended as **failed**" in mensagem
        assert "5 duplicated" in mensagem
        assert "Run workflow" in mensagem
