# Unit tests: the bronze layer (DGEG's raw answer as gzipped JSON Lines), with a fake Azure container

import gzip
import json
from datetime import date, datetime

import pytest

from etl.bronze import BronzeStore
from tests.conftest import make_record

DAY = date(2026, 10, 31)
TIME = datetime(2026, 10, 31, 18, 35, 12)


class FakeContainer:
    """Stands in for Azure's ContainerClient: keeps uploads in a dict and, like Azure, refuses to overwrite."""

    def __init__(self, failures=0):
        self.blobs = {}
        self.failures = failures   # how many uploads fail before one works (Azure briefly down)

    def upload_blob(self, name, data):
        if self.failures:
            self.failures -= 1
            raise ConnectionError("Azure unreachable")
        if name in self.blobs:
            raise FileExistsError(name)
        self.blobs[name] = data


def read_back(data):
    """The records back from a gzipped JSON Lines file."""
    return [json.loads(line) for line in gzip.decompress(data).decode("utf-8").splitlines()]


class TestSave:
    def test_keeps_the_records_exactly_as_dgeg_sent_them(self, tmp_path):
        # Including the price as text and Portuguese characters: nothing transformed
        records = [make_record(posto_id=1, nome="Posto São João"), make_record(posto_id=2)]

        name = BronzeStore(tmp_path).save(records, DAY, TIME)

        assert name == "dgeg_pesquisar_postos/date=2026-10-31/dgeg_2026-10-31T183512.jsonl.gz"
        assert read_back((tmp_path / name).read_bytes()) == records

    def test_a_second_run_the_same_day_adds_a_file(self, tmp_path):
        # Append-only: a manual rerun never replaces the first answer of the day
        store = BronzeStore(tmp_path)
        store.save([make_record()], DAY, TIME)
        store.save([make_record()], DAY, TIME.replace(hour=20))

        assert len(list(tmp_path.rglob("*.jsonl.gz"))) == 2

    def test_uploads_the_same_file_to_azure(self, tmp_path):
        container = FakeContainer()
        records = [make_record()]

        name = BronzeStore(tmp_path, container).save(records, DAY, TIME)

        assert read_back(container.blobs[name]) == records
        assert container.blobs[name] == (tmp_path / name).read_bytes()

    def test_retries_a_failed_upload_once(self, tmp_path):
        container = FakeContainer(failures=1)

        name = BronzeStore(tmp_path, container, retry_pause=0).save([make_record()], DAY, TIME)

        assert name in container.blobs

    def test_a_second_failure_raises_but_keeps_the_local_copy(self, tmp_path):
        # The run fails (the backup run tries again), and the local file goes into the run's artifact
        container = FakeContainer(failures=2)

        with pytest.raises(ConnectionError):
            BronzeStore(tmp_path, container, retry_pause=0).save([make_record()], DAY, TIME)
        assert len(list(tmp_path.rglob("*.jsonl.gz"))) == 1

    def test_without_azure_settings_it_is_local_only(self, monkeypatch):
        monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "")
        monkeypatch.setattr("etl.bronze.load_dotenv", lambda *a, **k: None)   # ignore a developer's .env

        assert BronzeStore.default().container is None


class TestRead:
    def test_lists_files_oldest_first_and_reads_them_back(self, tmp_path):
        # The backfill relies on this order: days must be loaded in sequence for SCD Type 2 to be right
        store = BronzeStore(tmp_path)
        store.save([make_record(posto_id=2)], date(2026, 11, 2), datetime(2026, 11, 2, 10))
        store.save([make_record(posto_id=1)], date(2026, 11, 1), datetime(2026, 11, 1, 10))

        snapshots = list(store.snapshots())

        assert [day for day, _ in snapshots] == [date(2026, 11, 1), date(2026, 11, 2)]
        assert store.read(snapshots[0][1]) == [make_record(posto_id=1)]
