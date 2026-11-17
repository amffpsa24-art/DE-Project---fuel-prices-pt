# Unit tests: downloading from the DGEG API, with a fake API (tests never call DGEG)
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
    """Stands in for requests.get: serves pre-built pages, one per call, and records every call's parameters."""

    def __init__(self):
        self.calls = []   # what the extractor asked for
        self.pages = []   # what the fake API answers, in order

    def get(self, url, params=None, timeout=None):
        self.calls.append(dict(params))
        page = self.pages.pop(0)   # serve the next page
        if isinstance(page, Exception):
            raise page             # e.g. a dropped connection
        return page

    @property
    def pages_requested(self):
        return [c["pagina"] for c in self.calls]


@pytest.fixture
def api(monkeypatch):
    """A FakeDgegApi in place of requests.get, and no waits (pauses, retries) during tests."""
    fake = FakeDgegApi()
    # monkeypatch swaps these only during the test, and puts the originals back afterwards
    monkeypatch.setattr(extract_module.requests, "get", fake.get)
    monkeypatch.setattr(extract_module.time, "sleep", lambda s: None)
    return fake


def records(n, total, first_id=0):
    """n API records (station ids from first_id on) whose 'Quantidade' (the grand total) is `total`."""
    # The API repeats the grand total on every row; the extractor uses it to know when to stop
    rs = [make_record(posto_id=i) for i in range(first_id, first_id + n)]
    for r in rs:
        r["Quantidade"] = total
    return rs


class TestPagination:
    def test_reads_every_page_until_the_total(self, api):
        # Total is 5, split over two pages (3 + 2): the extractor must ask for both and then stop
        api.pages += [FakeResponse(records(3, total=5)), FakeResponse(records(2, total=5, first_id=3))]

        assert len(DgegExtractor().extract()) == 5
        assert api.pages_requested == [1, 2]

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
        api.pages += [FakeResponse([], status_code=503)] * 4

        with pytest.raises(requests.HTTPError):
            DgegExtractor().extract()
        assert len(api.calls) == 4      # 1 attempt + 3 retries, then gives up

    def test_retries_a_temporary_error(self, api):
        # A hiccup (503, then a dropped connection) shouldn't fail the day: the next attempt succeeds
        api.pages += [FakeResponse([], status_code=503), requests.ConnectionError("reset"),
                      FakeResponse(records(2, total=2))]

        assert len(DgegExtractor().extract()) == 2
        assert api.pages_requested == [1, 1, 1]   # the same page, asked three times

    def test_does_not_retry_a_client_error(self, api):
        # 4xx means our request is wrong: retrying won't fix it, so fail at once
        api.pages += [FakeResponse([], status_code=400)]

        with pytest.raises(requests.HTTPError):
            DgegExtractor().extract()
        assert len(api.calls) == 1


class TestIsAvailable:
    def test_dgeg_answering(self, api):
        api.pages += [FakeResponse(records(1, total=1))]

        assert DgegExtractor().is_available() == (True, None)
        assert api.calls[0]["qtdPorPagina"] == 1   # a one-row request, not the whole day

    def test_dgeg_down_is_reported_once_without_retries(self, api):
        # The monitor only wants to know if DGEG is up now: one try, and the error for the alert
        api.pages += [FakeResponse([], status_code=500)]

        ok, error = DgegExtractor().is_available()

        assert ok is False
        assert "HTTPError: 500" in error
        assert len(api.calls) == 1
