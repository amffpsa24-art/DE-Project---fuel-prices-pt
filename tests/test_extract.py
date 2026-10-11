
# Unit tests: pagination of the DGEG API, with a fake API (tests never call DGEG)
# Created: 07/10/2026
# Why fake it: the real API changes every day, needs the internet, and shouldn't get extra traffic from tests.

import pytest
import requests

import etl.extract as extract_module
from etl.extract import extract
from tests.conftest import make_record


# A minimal copy of requests' response: only the three things extract() uses
class FakeResponse:
    """Stands in for requests' response object."""

    def __init__(self, resultado, status_code=200):
        self._resultado = resultado
        self.status_code = status_code

    # Same behaviour as the real one: raise on 4xx/5xx, do nothing on success
    def raise_for_status(self):
        if self.status_code >= 400:
            # response=self: like the real one, so extract() can tell 5xx (retry) from 4xx (fail at once)
            raise requests.HTTPError(f"{self.status_code} error", response=self)

    # Same JSON shape as DGEG's answer
    def json(self):
        return {"status": True, "mensagem": "sucesso", "resultado": self._resultado}


@pytest.fixture
def fake_api(monkeypatch):
    """
    Replaces requests.get with a function that serves pre-built pages, one per call,
    and records the parameters of every call. Also removes the pause between pages.
    """
    # calls: what extract() asked for. pages: what the fake API answers, in order.
    calls, pages = [], []

    def fake_get(url, params=None, timeout=None):
        calls.append(dict(params))
        pagina = pages.pop(0)   # serve the next page
        if isinstance(pagina, Exception):
            raise pagina        # e.g. a dropped connection
        return pagina

    # monkeypatch swaps these only during the test, and puts the originals back afterwards
    monkeypatch.setattr(extract_module.requests, "get", fake_get)
    monkeypatch.setattr(extract_module.time, "sleep", lambda s: None)   # no waits in tests (pauses, retries)
    return calls, pages


def records(n, total):
    """n API records whose 'Quantidade' (the grand total) is `total`."""
    # The API repeats the grand total on every row; extract() uses it to know when to stop
    rs = [make_record(posto_id=i) for i in range(n)]
    for r in rs:
        r["Quantidade"] = total
    return rs


def test_extract_reads_every_page_until_the_total(fake_api):
    # Total is 5, split over two pages (3 + 2): extract() must ask for both and then stop
    calls, pages = fake_api
    pages += [FakeResponse(records(3, total=5)), FakeResponse(records(2, total=5))]

    resultado = extract()

    assert len(resultado) == 5
    assert [c["pagina"] for c in calls] == [1, 2]      # asked for page 1, then page 2, then stopped


def test_extract_stops_on_an_empty_page(fake_api):
    # Safety stop: an empty page ends the loop, so a wrong total can't cause endless requests
    calls, pages = fake_api
    pages += [FakeResponse([])]

    assert extract() == []
    assert len(calls) == 1


def test_extract_asks_for_all_fuels_and_no_other_filter(fake_api):
    # Guards the request itself: a leftover filter would silently download only part of Portugal
    calls, pages = fake_api
    pages += [FakeResponse(records(1, total=1))]

    extract()

    p = calls[0]
    assert len(p["idsTiposComb"].split(",")) == 13      # every fuel type ID
    assert p["idMarca"] == p["idDistrito"] == p["idsMunicipios"] == ""   # empty = no filter


def test_extract_fails_loudly_when_the_api_keeps_failing(fake_api):
    # If DGEG stays down (503 on every attempt), the run must crash, not load an empty day as if it were real
    calls, pages = fake_api
    pages += [FakeResponse([], status_code=503)] * 3

    with pytest.raises(requests.HTTPError):
        extract()
    assert len(calls) == 3      # 1 attempt + 2 retries, then gives up


def test_extract_retries_a_temporary_error(fake_api):
    # A hiccup (503, then a dropped connection) shouldn't fail the day: the next attempt succeeds
    calls, pages = fake_api
    pages += [FakeResponse([], status_code=503), requests.ConnectionError("reset"), FakeResponse(records(2, total=2))]

    assert len(extract()) == 2
    assert [c["pagina"] for c in calls] == [1, 1, 1]   # the same page, asked three times


def test_extract_does_not_retry_a_client_error(fake_api):
    # 4xx means our request is wrong: retrying won't fix it, so fail at once
    calls, pages = fake_api
    pages += [FakeResponse([], status_code=400)]

    with pytest.raises(requests.HTTPError):
        extract()
    assert len(calls) == 1
