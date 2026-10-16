# MONITOR: checks that the day's snapshot was loaded, and says why not if it wasn't
# Created: 16/10/2026
# Usage (from the project root, with .venv active):  python monitor.py
# GitHub Actions runs it every evening (see .github/workflows/monitor.yml) and opens an issue if the day is missing.
#
# Why: GitHub emails a failed run, but a day where NO run happens (a cron started after midnight, as on 05/10)
# fails nothing and sends nothing. DGEG keeps no history, so a missed day is lost for good unless someone
# notices before midnight and starts the workflow by hand.

import logging
import os
from datetime import datetime, timedelta

from etl.runs import RunLog

log = logging.getLogger("monitor")


class FreshnessMonitor:
    """Decides which day must already be loaded, and checks pipeline_runs for it."""

    # From this hour (Lisbon), today must be loaded: the main run (13:17 UTC) and the backup (16:17 UTC)
    # have had time to finish. Before it, e.g. a check that GitHub started after midnight, it checks yesterday.
    HORA_LIMITE = 18

    def __init__(self, run_log, agora=None):
        self.run_log = run_log
        self.agora = agora   # tests pass a fixed time; None = the real clock

    def dia_a_verificar(self):
        agora = self.agora or datetime.now()
        if agora.hour >= self.HORA_LIMITE:
            return agora.date()
        return agora.date() - timedelta(days=1)

    def verificar(self):
        """Returns (day, loaded, message). The message explains a missing day, for the alert."""
        dia = self.dia_a_verificar()
        if self.run_log.ja_carregado(dia):
            return dia, True, f"{dia} is loaded."

        ultimo = self.run_log.ultimo(dia)
        if ultimo is None:
            motivo = "No run recorded this day at all: GitHub probably started the scheduled runs late or skipped them."
        else:
            triggered_by, status, error = ultimo
            motivo = f"The last run ({triggered_by}) ended as **{status}**" + (f": `{error}`" if error else ".")
        mensagem = (
            f"{dia} has no successful snapshot in `pipeline_runs`.\n\n{motivo}\n\n"
            "DGEG keeps no history, so this day is lost if it isn't loaded before midnight in Lisbon: "
            "start **Actions > Daily fuel prices > Run workflow** now."
        )
        return dia, False, mensagem


def escrever_output_github(**valores):
    """Passes values to the next workflow steps (GITHUB_OUTPUT); does nothing when run locally."""
    caminho = os.environ.get("GITHUB_OUTPUT")
    if not caminho:
        return
    with open(caminho, "a", encoding="utf-8") as f:
        for chave, valor in valores.items():
            # Multi-line values need the heredoc-style syntax
            f.write(f"{chave}<<FIM\n{valor}\nFIM\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    dia, carregado, mensagem = FreshnessMonitor(RunLog()).verificar()
    (log.info if carregado else log.warning)(mensagem.replace("\n\n", " "))
    escrever_output_github(dia=dia.isoformat(), carregado=str(carregado).lower(), mensagem=mensagem)
