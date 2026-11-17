# EXTRACT: downloads every station x fuel price from the DGEG API

import logging
import time

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://precoscombustiveis.dgeg.gov.pt/api/PrecoComb/PesquisarPostos"

# Every fuel type DGEG knows (13 IDs)
FUEL_IDS = "2115,1143,1141,1142,3400,3210,3205,3405,3201,2150,2155,2105,2101"


class DgegExtractor:
    """Downloads every record from the DGEG API, retrying when DGEG is temporarily down."""

    def __init__(self, base_url=BASE_URL, fuel_ids=FUEL_IDS, page_size=20_000, timeout=60,
                 page_pause=1, retry_pauses=(30, 120, 300)):
        self.base_url = base_url
        self.fuel_ids = fuel_ids
        # 20,000 fits a whole day (~14,200 rows) in ONE page. With smaller pages, DGEG's unstable sort order
        # repeated some rows and skipped others (see CHANGELOG, 2026-10-16).
        self.page_size = page_size
        # DGEG gives up on a slow query at 30s; waiting 60s means the log shows DGEG's own error
        self.timeout = timeout
        self.page_pause = page_pause
        # Waits before the 2nd, 3rd and 4th attempt: together they ride out a DGEG outage of about 8 minutes
        self.retry_pauses = list(retry_pauses)

    def extract(self):
        """Fetches all records, page by page, until the total the API announced is reached."""
        records = []
        page = 1
        total = None

        while True:
            response = self._get_with_retries(self._params(page))
            page_records = response.json().get("resultado", [])
            if not page_records:
                break

            records.extend(page_records)
            # "Quantidade" holds the total number of records (repeated on every row)
            if total is None:
                total = page_records[0]["Quantidade"]
            log.info("Page %d: %d records (total: %d / %d)", page, len(page_records), len(records), total)

            if len(records) >= total:
                break
            page += 1
            time.sleep(self.page_pause)   # be gentle with DGEG's server

        if total is not None and len(records) < total:
            log.warning("Got %d records, but the API announced %d", len(records), total)
        return records

    def is_available(self):
        """One one-row request, no retries: (True, None) if DGEG answers, else (False, the error). For the monitor."""
        params = {**self._params(1), "qtdPorPagina": 1}
        try:
            requests.get(self.base_url, params=params, timeout=self.timeout).raise_for_status()
            return True, None
        except requests.RequestException as e:
            # requests adds the whole query string to the message; the alert doesn't need it
            return False, f"{type(e).__name__}: {str(e).split(' for url:')[0]}"

    def _params(self, page):
        """Query string for one page: every fuel, no other filter (empty = all of Portugal)."""
        return {
            "idsTiposComb": self.fuel_ids,
            "idMarca": "",
            "idTipoPosto": "",
            "idDistrito": "",
            "idsMunicipios": "",
            "qtdPorPagina": self.page_size,
            "pagina": page,
        }

    def _get_with_retries(self, params):
        """GETs one page, retrying temporary errors: connection problems, timeouts and 5xx responses."""
        for attempt in range(len(self.retry_pauses) + 1):
            try:
                response = requests.get(self.base_url, params=params, timeout=self.timeout)
                response.raise_for_status()
                return response
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
                # 4xx means the request itself is wrong: retrying won't help, so fail at once
                status = getattr(e.response, "status_code", None)
                temporary = status is None or status >= 500
                if not temporary or attempt == len(self.retry_pauses):
                    raise
                pause = self.retry_pauses[attempt]
                log.warning("Page %s, attempt %d failed (%s); retrying in %ds", params["pagina"], attempt + 1, e, pause)
                time.sleep(pause)
