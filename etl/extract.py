# Extract fuel price records from the DGEG API
# Created: 27/09/2026

import time

import requests

BASE_URL = "https://precoscombustiveis.dgeg.gov.pt/api/PrecoComb/PesquisarPostos"

TIPOS_COMB = "2115,1143,1141,1142,3400,3210,3205,3405,3201,2150,2155,2105,2101"

QTD_POR_PAGINA = 10000
TIMEOUT_SECONDS = 30
PAUSA_ENTRE_PAGINAS = 1


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

        response = requests.get(
            BASE_URL,
            params=params,
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        data = response.json()
        registos_pagina = data.get("resultado", [])

        if not registos_pagina:
            break

        todos_registos.extend(registos_pagina)

        # "Quantidade" contains the total number of records returned by the API.
        if total_registos is None:
            total_registos = registos_pagina[0]["Quantidade"]

        print(
            f"Page {pagina}: {len(registos_pagina)} records "
            f"(total: {len(todos_registos)} / {total_registos})"
        )

        if len(todos_registos) >= total_registos:
            break

        pagina += 1
        time.sleep(PAUSA_ENTRE_PAGINAS)

    return todos_registos