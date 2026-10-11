# Extract fuel price records from the DGEG API
# Created: 27/09/2026
# Updated: 11/10/2026 (retries for temporary errors, logging)

import logging
import time

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://precoscombustiveis.dgeg.gov.pt/api/PrecoComb/PesquisarPostos"

TIPOS_COMB = "2115,1143,1141,1142,3400,3210,3205,3405,3201,2150,2155,2105,2101"

QTD_POR_PAGINA = 10000
TIMEOUT_SECONDS = 30
PAUSA_ENTRE_PAGINAS = 1

# Waits before the 2nd and 3rd attempt. Temporary problems (network, DGEG overloaded) often pass in seconds;
# after 3 attempts the run fails, and the backup run tries again later.
PAUSAS_RETRY = [10, 30]


def _get_com_retries(params):
    """GET one page, retrying on temporary errors: connection problems, timeouts and 5xx responses."""
    for tentativa in range(len(PAUSAS_RETRY) + 1):
        try:
            response = requests.get(BASE_URL, params=params, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            return response
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
            # 4xx means the request itself is wrong: retrying won't help, so fail at once
            status = getattr(e.response, "status_code", None)
            temporario = status is None or status >= 500
            if not temporario or tentativa == len(PAUSAS_RETRY):
                raise
            pausa = PAUSAS_RETRY[tentativa]
            log.warning("Page %s, attempt %d failed (%s); retrying in %ds",
                        params["pagina"], tentativa + 1, e, pausa)
            time.sleep(pausa)


def extract():
    """Fetch all available fuel price records from the DGEG API."""

    todos_registos = []
    pagina = 1
    total_registos = None

    while True:
        params = {
            "idsTiposComb": TIPOS_COMB,
            "idMarca": "",
            "idTipoPosto": "",
            "idDistrito": "",
            "idsMunicipios": "",
            "qtdPorPagina": QTD_POR_PAGINA,
            "pagina": pagina,
        }

        response = _get_com_retries(params)

        data = response.json()
        registos_pagina = data.get("resultado", [])

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
        time.sleep(PAUSA_ENTRE_PAGINAS)

    return todos_registos
