# BRONZE: keeps DGEG's answer exactly as it came, one gzipped JSON Lines file per run, locally and in Azure
# Created: 31/10/2026
#
# Why: DGEG keeps no history, so its raw answer is the one dataset that can't be rebuilt. The CSV in data/raw/
# is the data after the transform, and GitHub keeps it only 90 days. Databricks (Phase 3) will read this layer:
# JSON Lines (one record per line) under date=YYYY-MM-DD/ folders is what Spark reads without extra options.

import gzip
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from azure.storage.blob import ContainerClient
from dotenv import load_dotenv

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Local copy: also uploaded as the run's GitHub artifact, so a failed Azure upload can be redone by hand
PASTA_BRONZE = PROJECT_ROOT / "data" / "bronze"


class BronzeStore:
    """One file per run, e.g. dgeg_pesquisar_postos/date=2026-10-31/dgeg_2026-10-31T183512.jsonl.gz. Never overwrites."""

    PREFIXO = "dgeg_pesquisar_postos"

    def __init__(self, pasta=PASTA_BRONZE, container=None):
        self.pasta = Path(pasta)
        # Anything with upload_blob(name, data): an Azure ContainerClient, or a fake in tests. None = local only
        self.container = container

    @classmethod
    def default(cls):
        """The local folder, plus Azure when AZURE_STORAGE_CONNECTION_STRING is set (GitHub Secret or .env).
        It should be a SAS connection string without Delete: the job only ever adds files (see README)."""
        load_dotenv(PROJECT_ROOT / ".env")
        conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        if not conn:
            log.info("Azure not configured: the raw JSON is kept locally only")
            return cls()
        container = os.environ.get("AZURE_STORAGE_CONTAINER", "bronze")
        return cls(container=ContainerClient.from_connection_string(conn, container))

    def nome(self, snapshot_date, capturado_em):
        return (f"{self.PREFIXO}/date={snapshot_date.isoformat()}/"
                f"dgeg_{capturado_em.strftime('%Y-%m-%dT%H%M%S')}.jsonl.gz")

    def save(self, registos, snapshot_date, capturado_em=None):
        """Writes the records exactly as DGEG sent them, then uploads them. Returns the file's name in the layer."""
        nome = self.nome(snapshot_date, capturado_em or datetime.now())
        # ensure_ascii=False: Portuguese characters stay as they are (UTF-8), like everywhere else in the project
        linhas = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in registos)
        dados = gzip.compress(linhas.encode("utf-8"))

        caminho = self.pasta / nome
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(dados)
        log.info("Saved %d raw records to %s (%d KB)", len(registos), caminho, len(dados) // 1024)

        if self.container is not None:
            # overwrite=False (the default): an existing name raises instead of replacing it, so the layer is append-only
            self.container.upload_blob(nome, dados)
            log.info("Uploaded to Azure: %s", nome)
        return nome
