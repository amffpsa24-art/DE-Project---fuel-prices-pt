# BRONZE: keeps DGEG's answer exactly as it came, one gzipped JSON Lines file per run, locally and in Azure
#
# DGEG keeps no history, so its raw answer is the one dataset that can't be rebuilt.
# JSON Lines under date=YYYY-MM-DD/ folders is what Spark reads directly (Phase 3: Databricks).

import gzip
import json
import logging
import os
import time
from datetime import date, datetime
from pathlib import Path

from azure.storage.blob import ContainerClient
from dotenv import load_dotenv

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Local copy: also uploaded as the run's GitHub artifact, and what backfill.py reads
BRONZE_FOLDER = PROJECT_ROOT / "data" / "bronze"


class BronzeStore:
    """One file per run, e.g. dgeg_pesquisar_postos/date=2026-10-31/dgeg_2026-10-31T183512.jsonl.gz. Never overwrites."""

    PREFIX = "dgeg_pesquisar_postos"

    def __init__(self, folder=BRONZE_FOLDER, container=None, retry_pause=30):
        self.folder = Path(folder)
        # Anything with upload_blob(name, data): an Azure ContainerClient, or a fake in tests. None = local only
        self.container = container
        self.retry_pause = retry_pause

    @classmethod
    def default(cls):
        """The local folder, plus Azure when AZURE_STORAGE_CONNECTION_STRING is set (GitHub Secret or .env).
        It should be a SAS connection string without Delete permission (see README)."""
        load_dotenv(PROJECT_ROOT / ".env")
        conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        if not conn:
            log.info("Azure not configured: the raw JSON is kept locally only")
            return cls()
        container = os.environ.get("AZURE_STORAGE_CONTAINER", "bronze")
        return cls(container=ContainerClient.from_connection_string(conn, container))

    def blob_name(self, snapshot_date, captured_at):
        return (f"{self.PREFIX}/date={snapshot_date.isoformat()}/"
                f"dgeg_{captured_at.strftime('%Y-%m-%dT%H%M%S')}.jsonl.gz")

    def save(self, records, snapshot_date, captured_at=None):
        """Writes the records exactly as DGEG sent them, then uploads them. Returns the file's name in the layer."""
        name = self.blob_name(snapshot_date, captured_at or datetime.now())
        # ensure_ascii=False: Portuguese characters stay as they are (UTF-8)
        lines = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
        data = gzip.compress(lines.encode("utf-8"))

        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        log.info("Saved %d raw records to %s (%d KB)", len(records), path, len(data) // 1024)

        if self.container is not None:
            self._upload(name, data)
        return name

    def _upload(self, name, data):
        """Uploads to Azure, trying twice. A second failure fails the run, and the backup run tries again."""
        for attempt in (1, 2):
            try:
                # overwrite=False (the default): an existing name raises instead of being replaced
                self.container.upload_blob(name, data)
                log.info("Uploaded to Azure: %s", name)
                return
            except Exception as e:
                if attempt == 2:
                    raise
                log.warning("Azure upload failed (%s: %s); retrying in %ds", type(e).__name__, e, self.retry_pause)
                time.sleep(self.retry_pause)

    def snapshots(self):
        """Every local file as (date, path), oldest first. A day can have several files (one per run)."""
        for path in sorted(self.folder.glob(f"{self.PREFIX}/date=*/*.jsonl.gz")):
            # ".../date=2026-10-31/..." -> 2026-10-31
            yield date.fromisoformat(path.parent.name.removeprefix("date=")), path

    @staticmethod
    def read(path):
        """The records of one file, exactly as DGEG sent them."""
        lines = gzip.decompress(Path(path).read_bytes()).decode("utf-8").splitlines()
        return [json.loads(line) for line in lines]
