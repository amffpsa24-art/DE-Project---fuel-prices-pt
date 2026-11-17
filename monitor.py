# MONITOR: checks that the day's snapshot was loaded, and says why not if it wasn't
# Usage (from the project root, with .venv active):  python monitor.py
# GitHub Actions runs it every evening (see .github/workflows/monitor.yml) and opens an issue if the day is missing.
#
# GitHub emails about a failed run, but a day where NO run happens sends nothing.
# DGEG keeps no history, so a missed day is lost unless someone starts the workflow by hand before midnight.

import logging
import os
from datetime import datetime, timedelta

from etl.extract import DgegExtractor
from etl.runs import RunLog

log = logging.getLogger("monitor")


class FreshnessMonitor:
    """Decides which day must already be loaded, and checks pipeline_runs for it."""

    # From this hour (Lisbon), today must be loaded. Before it (e.g. a check GitHub started after midnight),
    # it checks yesterday.
    CUTOFF_HOUR = 18

    def __init__(self, run_log, now=None, dgeg=None):
        self.run_log = run_log
        self.now = now     # tests pass a fixed time; None = the real clock
        # Anything with is_available() -> (ok, error), to say in the alert whether a manual run can work now.
        # None = don't check
        self.dgeg = dgeg

    def day_to_check(self):
        now = self.now or datetime.now()
        if now.hour >= self.CUTOFF_HOUR:
            return now.date()
        return now.date() - timedelta(days=1)

    def check(self):
        """Returns (day, loaded, message). The message explains a missing day, for the alert."""
        day = self.day_to_check()
        if self.run_log.is_loaded(day):
            return day, True, f"{day} is loaded."

        last = self.run_log.last_run(day)
        if last is None:
            reason = "No run recorded this day at all: GitHub probably started the scheduled runs late or skipped them."
        else:
            triggered_by, status, error = last
            reason = f"The last run ({triggered_by}) ended as **{status}**" + (f": `{error}`" if error else ".")

        dgeg_status, when = "", "now"
        if self.dgeg is not None:
            ok, error = self.dgeg.is_available()
            if ok:
                dgeg_status = "DGEG is answering right now, so a manual run should work.\n\n"
            else:
                dgeg_status = f"DGEG is **not answering** right now (`{error}`), so a manual run would fail too.\n\n"
                when = "as soon as DGEG answers again"
        message = (
            f"{day} has no successful snapshot in `pipeline_runs`.\n\n{reason}\n\n{dgeg_status}"
            "DGEG keeps no history, so this day is lost if it isn't loaded before midnight in Lisbon: "
            f"start **Actions > Daily fuel prices > Run workflow** {when}."
        )
        return day, False, message


def write_github_output(**values):
    """Passes values to the next workflow steps (GITHUB_OUTPUT); does nothing when run locally."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        for key, value in values.items():
            # Multi-line values need the heredoc-style syntax
            f.write(f"{key}<<EOF\n{value}\nEOF\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    day, loaded, message = FreshnessMonitor(RunLog(), dgeg=DgegExtractor()).check()
    (log.info if loaded else log.warning)(message.replace("\n\n", " "))
    write_github_output(day=day.isoformat(), loaded=str(loaded).lower(), message=message)
