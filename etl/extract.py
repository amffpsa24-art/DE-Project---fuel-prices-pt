# ============================================
# EXTRACT: fetches ALL records from the DGEG API, page by page
# ============================================
# Created: 27/09/2026

import time
import requests

# Base endpoint of the (undocumented) DGEG fuel prices API, found via browser DevTools
BASE_URL = "https://precoscombustiveis.dgeg.gov.pt/api/PrecoComb/PesquisarPostos"

# All fuel type IDs, so nothing gets filtered out
TIPOS_COMB = "2115,1143,1141,1142,3400,3210,3205,3405,3201,2150,2155,2105,2101"

# Tested on 27/09/2026: the API accepts 10000 per page, so ~2 requests cover all of Portugal
QTD_POR_PAGINA = 10000

# Seconds to wait before giving up on a request that hangs
TIMEOUT_SECONDS = 30

# Short pause between page requests, to be a "good citizen" towards a public server
PAUSA_ENTRE_PAGINAS = 1


def extract():
    """
    PAGINATION LOOP: requests the DGEG API page by page
    until all available records have been collected.
    Returns a list of dictionaries (one per "Posto" + "Combustivel" pair).
    """
    # List where the records of all pages are combined
    todos_registos = []
    pagina = 1

    while True:
        # Query parameters for the current page (empty values = no filter)
        params = {
            "idsTiposComb": TIPOS_COMB,
            "idMarca": "",
            "idTipoPosto": "",
            "idDistrito": "",
            "idsMunicipios": "",
            "qtdPorPagina": QTD_POR_PAGINA,
            "pagina": pagina,
        }

        # Make the request; requests builds the "?key=value&..." part of the URL for us
        response = requests.get(BASE_URL, params=params, timeout=TIMEOUT_SECONDS)

        # Stop immediately with a clear error if the API answers with 4xx/5xx
        response.raise_for_status()
        data = response.json()

        # Add this page's records to the total list
        # ("extend" instead of "append" keeps it a flat list of records)
        registos_pagina = data["resultado"]
        todos_registos.extend(registos_pagina)  # Elaborate more on this!

        # "Quantidade" was confirmed by inspection to hold the grand total,
        # repeated identically on every record
        total_registos = registos_pagina[0]["Quantidade"] if registos_pagina else 0

        print(
            f"Page {pagina}: {len(registos_pagina)} records "
            f"(accumulated: {len(todos_registos)} / {total_registos})"
        )

        # Stop when everything has been collected, or when a page comes back empty
        if len(todos_registos) >= total_registos or len(registos_pagina) == 0:
            break

        pagina += 1
        time.sleep(PAUSA_ENTRE_PAGINAS)

    return todos_registos