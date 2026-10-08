# ============================================
# Unit tests: pagination of the DGEG API, with a fake API (tests never call DGEG)
# ============================================
# Created: 07/10/2026

import pytest
import requests

import etl.extract as extract_module
from etl.extract import extract
from tests.conftest import make_record


class FakeResponse:
    """Stands in for requests' response object."""

    def __init__(self, resultado, status_code=200):
        self._resultado = resultado
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return {"status": True, "mensagem": "sucesso", "resultado": self._resultado}


@pytest.fixture
def fake_api(monkeypatch):
    """
    Replaces requests.get with a function that serves pre-built pages, one per call,
    and records the parameters of every call. Also removes the pause between pages.
    """
    calls, pages = [], []

    def fake_get(url, params=None, timeout=None):
        calls.append(dict(params))
        return pages.pop(0)

    monkeypatch.setattr(extract_module.requests, "get", fake_get)
    monkeypatch.setattr(extract_module.time, "sleep", lambda s: None)
    return calls, pages


def records(n, total):
    """n API records whose 'Quantidade' (the grand total) is `total`."""
    rs = [make_record(posto_id=i) for i in range(n)]
    for r in rs:
        r["Quantidade"] = total
    return rs


def test_extract_reads_every_page_until_the_total(fake_api):
    calls, pages = fake_api
    pages += [FakeResponse(records(3, total=5)), FakeResponse(records(2, total=5))]

    resultado = extract()

    assert len(resultado) == 5
    assert [c["pagina"] for c in calls] == [1, 2]      # asked for page 1, then page 2, then stopped


def test_extract_stops_on_an_empty_page(fake_api):
    calls, pages = fake_api
    pages += [FakeResponse([])]

    assert extract() == []
    assert len(calls) == 1


def test_extract_asks_for_all_fuels_and_no_other_filter(fake_api):
    calls, pages = fake_api
    pages += [FakeResponse(records(1, total=1))]

    extract()

    p = calls[0]
    assert len(p["idsTiposComb"].split(",")) == 13      # every fuel type ID
    assert p["idMarca"] == p["idDistrito"] == p["idsMunicipios"] == ""


def test_extract_fails_loudly_when_the_api_returns_an_error(fake_api):
    calls, pages = fake_api
    pages += [FakeResponse([], status_code=503)]

    with pytest.raises(requests.HTTPError):
        extract()