# Extract fuel price records from the DGEG API
# Created: 27/09/2026
# Updated: 11/10/2026 (retries for temporary errors, logging)
# Updated: 16/10/2026 (download everything again when the pages don't add up)
# Updated: 16/10/2026 (DgegExtractor class: settings live on the object, so tests can pass their own)

import logging
import time

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://precoscombustiveis.dgeg.gov.pt/api/PrecoComb/PesquisarPostos"

TIPOS_COMB = "2115,1143,1141,1142,3400,3210,3205,3405,3201,2150,2155,2105,2101"


class DgegExtractor:
    """Downloads every station x fuel price from the DGEG API, page by page."""

    def __init__(self, base_url=BASE_URL, tipos_comb=TIPOS_COMB, qtd_por_pagina=20_000, timeout=30,
                 pausa_entre_paginas=1, pausas_retry=(10, 30), tentativas_extracao=3, pausa_entre_extracoes=60):
        self.base_url = base_url
        self.tipos_comb = tipos_comb
        # The API pages with an offset, and its order isn't stable (stations with the same price swap places
        # between requests). With 10,000 rows per page, about half of the downloads had rows repeated across
        # the page boundary and as many skipped (16/10/2026). 20,000 fits a whole day (~14,200 rows) in ONE page,
        # so there is no boundary; DGEG accepts it.
        self.qtd_por_pagina = qtd_por_pagina
        self.timeout = timeout
        self.pausa_entre_paginas = pausa_entre_paginas
        # Waits before the 2nd and 3rd attempt of a page. Temporary problems (network, DGEG overloaded) often
        # pass in seconds; after 3 attempts the run fails, and the backup run tries again later.
        self.pausas_retry = list(pausas_retry)
        # Safety net if a day ever needs more than one page: a download whose pages overlap
        # is repeated from page 1, after a pause.
        self.tentativas_extracao = tentativas_extracao
        self.pausa_entre_extracoes = pausa_entre_extracoes

    def extract(self):
        """Fetch all available fuel price records, downloading again if the pages don't add up."""
        for tentativa in range(1, self.tentativas_extracao + 1):
            registos, total_registos = self._extract_uma_vez()
            problema = self._problema_paginas(registos, total_registos)
            if problema is None:
                return registos
            if tentativa < self.tentativas_extracao:
                log.warning("Download %d is inconsistent (%s); downloading again in %ds",
                            tentativa, problema, self.pausa_entre_extracoes)
                time.sleep(self.pausa_entre_extracoes)

        # Still wrong after every attempt: return it anyway, so the quality checks fail the run
        # and pipeline_runs records why
        log.warning("Download still inconsistent after %d attempts (%s)", self.tentativas_extracao, problema)
        return registos

    def _extract_uma_vez(self):
        """Fetch every page once. Returns the records and the total the API announced (None if nothing came)."""
        todos_registos = []
        pagina = 1
        total_registos = None

        while True:
            response = self._get_com_retries(self._params(pagina))
            registos_pagina = response.json().get("resultado", [])

            if not registos_pagina:
                break

            todos_registos.extend(registos_pagina)

            # "Quantidade" contains the total number of records returned by the API.
            if total_registos is None:
                total_registos = registos_pagina[0]["Quantidade"]

            log.info("Page %d: %d records (total: %d / %d)",
                     pagina, len(registos_pagina), len(todos_registos), total_registos)

            if len(todos_registos) >= total_registos:
                break

            pagina += 1
            time.sleep(self.pausa_entre_paginas)

        return todos_registos, total_registos

    def _params(self, pagina):
        """Query string for one page: every fuel, no other filter (empty = all of Portugal)."""
        return {
            "idsTiposComb": self.tipos_comb,
            "idMarca": "",
            "idTipoPosto": "",
            "idDistrito": "",
            "idsMunicipios": "",
            "qtdPorPagina": self.qtd_por_pagina,
            "pagina": pagina,
        }

    def _get_com_retries(self, params):
        """GET one page, retrying on temporary errors: connection problems, timeouts and 5xx responses."""
        for tentativa in range(len(self.pausas_retry) + 1):
            try:
                response = requests.get(self.base_url, params=params, timeout=self.timeout)
                response.raise_for_status()
                return response
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
                # 4xx means the request itself is wrong: retrying won't help, so fail at once
                status = getattr(e.response, "status_code", None)
                temporario = status is None or status >= 500
                if not temporario or tentativa == len(self.pausas_retry):
                    raise
                pausa = self.pausas_retry[tentativa]
                log.warning("Page %s, attempt %d failed (%s); retrying in %ds",
                            params["pagina"], tentativa + 1, e, pausa)
                time.sleep(pausa)

    @staticmethod
    def _problema_paginas(registos, total_registos):
        """Describes what is wrong with a download (rows repeated across pages, missing rows), or None if it's fine."""
        chaves = {(r["Id"], r["Combustivel"]) for r in registos}
        if len(chaves) < len(registos):
            return f"{len(registos) - len(chaves)} station x fuel rows came twice"
        if total_registos is not None and len(registos) < total_registos:
            return f"{len(registos)} rows, but the API said {total_registos}"
        return None
