# Unit tests: pagination of the DGEG API, with a fake API (tests never call DGEG)
# Created: 07/10/2026
# Updated: 16/10/2026 (tests grouped in classes; FakeDgegApi class instead of a dict-returning fixture)
# Why fake it: the real API changes every day, needs the internet, and shouldn't get extra traffic from tests.

import pytest
import requests

import etl.extract as extract_module
from etl.extract import DgegExtractor
from tests.conftest import make_record


# A minimal copy of requests' response: only the three things the extractor uses
class FakeResponse:
    """Stands in for requests' response object."""

    def __init__(self, resultado, status_code=200):
        self._resultado = resultado
        self.status_code = status_code

    # Same behaviour as the real one: raise on 4xx/5xx, do nothing on success
    def raise_for_status(self):
        if self.status_code >= 400:
            # response=self: like the real one, so the extractor can tell 5xx (retry) from 4xx (fail at once)
            raise requests.HTTPError(f"{self.status_code} error", response=self)

    # Same JSON shape as DGEG's answer
    def json(self):
        return {"status": True, "mensagem": "sucesso", "resultado": self._resultado}


class FakeDgegApi:
    """
    Stands in for requests.get: serves pre-built pages, one per call,
    and records the parameters of every call.
    """

    def __init__(self):
        self.calls = []   # what the extractor asked for
        self.pages = []   # what the fake API answers, in order

    def get(self, url, params=None, timeout=None):
        self.calls.append(dict(params))
        pagina = self.pages.pop(0)   # serve the next page
        if isinstance(pagina, Exception):
            raise pagina             # e.g. a dropped connection
        return pagina

    @property
    def paginas_pedidas(self):
        return [c["pagina"] for c in self.calls]


@pytest.fixture
def api(monkeypatch):
    """A FakeDgegApi in place of requests.get, and no waits (pauses, retries) during tests."""
    fake = FakeDgegApi()
    # monkeypatch swaps these only during the test, and puts the originals back afterwards
    monkeypatch.setattr(extract_module.requests, "get", fake.get)
    monkeypatch.setattr(extract_module.time, "sleep", lambda s: None)
    return fake


def records(n, total, primeiro_id=0):
    """n API records (station ids from primeiro_id on) whose 'Quantidade' (the grand total) is `total`."""
    # The API repeats the grand total on every row; the extractor uses it to know when to stop
    rs = [make_record(posto_id=i) for i in range(primeiro_id, primeiro_id + n)]
    for r in rs:
        r["Quantidade"] = total
    return rs


class TestPagination:
    def test_reads_every_page_until_the_total(self, api):
        # Total is 5, split over two pages (3 + 2): the extractor must ask for both and then stop
        api.pages += [FakeResponse(records(3, total=5)), FakeResponse(records(2, total=5, primeiro_id=3))]

        assert len(DgegExtractor().extract()) == 5
        assert api.paginas_pedidas == [1, 2]      # asked for page 1, then page 2, then stopped

    def test_stops_on_an_empty_page(self, api):
        # Safety stop: an empty page ends the loop, so a wrong total can't cause endless requests
        api.pages += [FakeResponse([])]

        assert DgegExtractor().extract() == []
        assert len(api.calls) == 1

    def test_asks_for_all_fuels_and_no_other_filter(self, api):
        # Guards the request itself: a leftover filter would silently download only part of Portugal
        api.pages += [FakeResponse(records(1, total=1))]

        DgegExtractor().extract()

        p = api.calls[0]
        assert len(p["idsTiposComb"].split(",")) == 13      # every fuel type ID
        assert p["idMarca"] == p["idDistrito"] == p["idsMunicipios"] == ""   # empty = no filter


class TestRetries:
    def test_fails_loudly_when_the_api_keeps_failing(self, api):
        # If DGEG stays down (503 on every attempt), the run must crash, not load an empty day as if it were real
        api.pages += [FakeResponse([], status_code=503)] * 3

        with pytest.raises(requests.HTTPError):
            DgegExtractor().extract()
        assert len(api.calls) == 3      # 1 attempt + 2 retries, then gives up

    def test_retries_a_temporary_error(self, api):
        # A hiccup (503, then a dropped connection) shouldn't fail the day: the next attempt succeeds
        api.pages += [FakeResponse([], status_code=503), requests.ConnectionError("reset"),
                      FakeResponse(records(2, total=2))]

        assert len(DgegExtractor().extract()) == 2
        assert api.paginas_pedidas == [1, 1, 1]   # the same page, asked three times

    def test_does_not_retry_a_client_error(self, api):
        # 4xx means our request is wrong: retrying won't fix it, so fail at once
        api.pages += [FakeResponse([], status_code=400)]

        with pytest.raises(requests.HTTPError):
            DgegExtractor().extract()
        assert len(api.calls) == 1


class TestInconsistentDownloads:
    def test_downloads_again_when_pages_overlap(self, api):
        # DGEG's order shifted between pages: station 2 comes on both, station 3 on neither (same total).
        # The extractor must notice and download everything again, from page 1
        api.pages += [FakeResponse(records(3, total=5)), FakeResponse(records(2, total=5, primeiro_id=2)),
                      FakeResponse(records(3, total=5)), FakeResponse(records(2, total=5, primeiro_id=3))]

        resultado = DgegExtractor().extract()

        assert sorted(r["Id"] for r in resultado) == [0, 1, 2, 3, 4]
        assert api.paginas_pedidas == [1, 2, 1, 2]

    def test_gives_up_and_returns_the_last_download(self, api):
        # Still overlapping after every attempt: return the data anyway, so the quality checks fail the run
        # with a clear reason (instead of a crash here)
        extractor = DgegExtractor(tentativas_extracao=2)
        for _ in range(extractor.tentativas_extracao):
            api.pages += [FakeResponse(records(3, total=5)), FakeResponse(records(2, total=5, primeiro_id=2))]

        assert len(extractor.extract()) == 5
        assert len(api.calls) == 2 * extractor.tentativas_extracao
