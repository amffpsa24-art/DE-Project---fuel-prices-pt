# Unit tests: the bronze layer (DGEG's raw answer as gzipped JSON Lines), with a fake Azure container
# Created: 31/10/2026

import gzip
import json
from datetime import date, datetime

import pytest

from etl.bronze import BronzeStore
from tests.conftest import make_record

DIA = date(2026, 10, 31)
HORA = datetime(2026, 10, 31, 18, 35, 12)


class FakeContainer:
    """Stands in for Azure's ContainerClient: keeps uploads in a dict and, like Azure, refuses to overwrite."""

    def __init__(self):
        self.blobs = {}

    def upload_blob(self, name, data):
        if name in self.blobs:
            raise FileExistsError(name)
        self.blobs[name] = data


def ler(dados):
    """The records back from a gzipped JSON Lines file."""
    return [json.loads(linha) for linha in gzip.decompress(dados).decode("utf-8").splitlines()]


class TestBronzeStore:
    def test_keeps_the_records_exactly_as_dgeg_sent_them(self, tmp_path):
        # Including the price as text and Portuguese characters: nothing transformed
        registos = [make_record(posto_id=1, nome="Posto São João"), make_record(posto_id=2)]

        nome = BronzeStore(tmp_path).save(registos, DIA, HORA)

        assert nome == "dgeg_pesquisar_postos/date=2026-10-31/dgeg_2026-10-31T183512.jsonl.gz"
        assert ler((tmp_path / nome).read_bytes()) == registos

    def test_a_second_run_the_same_day_adds_a_file(self, tmp_path):
        # Append-only: a manual rerun never replaces the first answer of the day
        store = BronzeStore(tmp_path)
        store.save([make_record()], DIA, HORA)
        store.save([make_record()], DIA, HORA.replace(hour=20))

        assert len(list(tmp_path.rglob("*.jsonl.gz"))) == 2

    def test_uploads_the_same_file_to_azure(self, tmp_path):
        container = FakeContainer()
        registos = [make_record()]

        nome = BronzeStore(tmp_path, container).save(registos, DIA, HORA)

        assert ler(container.blobs[nome]) == registos
        assert container.blobs[nome] == (tmp_path / nome).read_bytes()

    def test_an_azure_failure_still_leaves_the_local_copy(self, tmp_path):
        # The local file goes into the run's artifact, so the upload can be redone by hand
        container = FakeContainer()
        container.blobs[BronzeStore().nome(DIA, HORA)] = b"already there"

        with pytest.raises(FileExistsError):
            BronzeStore(tmp_path, container).save([make_record()], DIA, HORA)
        assert len(list(tmp_path.rglob("*.jsonl.gz"))) == 1

    def test_without_azure_settings_it_is_local_only(self, monkeypatch):
        monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "")
        monkeypatch.setattr("etl.bronze.load_dotenv", lambda *a, **k: None)   # ignore a developer's .env

        assert BronzeStore.default().container is None
