"""
precoscombustiveis.dgeg.gov.pt/estatistica/postos/
Abre as DevTools (F12 ou Ctrl+Shift+I) e clica no separador Network. Deixa a página aberta com o DevTools a gravar.
No separador Network há botões de filtro (All, Fetch/XHR, JS, CSS...). Clica em Fetch/XHR para esconderes o ruído de imagens e CSS
Clica no ícone de 'limpar' (🚫) na Network tab para começares do zero. Depois, na página, escolhe um distrito (ex: Lisboa) e clica em 'Procurar'.
Deve aparecer um novo pedido na lista do Network — provavelmente com um nome tipo 'Pesquisa' ou 'GetPostos' ou parecido. Clica nele. Vê o separador 'Headers' para confirmares a URL completa e o método (GET ou POST), e os 'Payload'/'Query String Parameters' para veres que parâmetros foram enviados (distrito, tipo de combustível, etc.).


Headers
Request URL
https://precoscombustiveis.dgeg.gov.pt/api/PrecoComb/PesquisarPostos?idsTiposComb=2115%2C1143%2C1141%2C1142%2C3400%2C3210%2C3205%2C3405%2C3201%2C2150%2C2155%2C2105%2C2101&idMarca=&idTipoPosto=&idDistrito=11&idsMunicipios=&qtdPorPagina=50&pagina=1
Request Method
GET
Status Code
200 OK
Remote Address
13.81.123.99:443
Referrer Policy
strict-origin-when-cross-origin

Payload
idsTiposComb
2115,1143,1141,1142,3400,3210,3205,3405,3201,2150,2155,2105,2101
idMarca
idTipoPosto
idDistrito
11
idsMunicipios
qtdPorPagina
50
pagina
1
"""
"""
SCHEMA to MAP my Data from. -> Table: dim_postos.
Json Files  - Distrito Lisboa + Combustiveis 13
ENDPOINT: https://precoscombustiveis.dgeg.gov.pt/api/PrecoComb/PesquisarPostos?idsTiposComb=2115%2C1143%2C1141%2C1142%2C3400%2C3210%2C3205%2C3405%2C3201%2C2150%2C2155%2C2105%2C2101&idMarca=&idTipoPosto=&idDistrito=11&idsMunicipios=&qtdPorPagina=50&pagina=1

2. request:
Filtros: 
    Combustível: 13
    Distrito: Lisboa
    Município: Null
    Tipo de Posto: Auto-Estrada
    Marca: Null
https://precoscombustiveis.dgeg.gov.pt/api/PrecoComb/PesquisarPostos?idsTiposComb=2115%2C1143%2C1141%2C1142%2C3400%2C3210%2C3205%2C3405%2C3201%2C2150%2C2155%2C2105%2C2101&idMarca=&idTipoPosto=1&idDistrito=11&idsMunicipios=&qtdPorPagina=50&pagina=1

3. Request: 
Filtros: 
    Combustível: 13
    Distrito: Lisboa
    Município: Null
    Tipo de Posto: Área comercial (Hipermercados)
    Marca: Null
 https://precoscombustiveis.dgeg.gov.pt/api/PrecoComb/PesquisarPostos?idsTiposComb=2115%2C1143%2C1141%2C1142%2C3400%2C3210%2C3205%2C3405%2C3201%2C2150%2C2155%2C2105%2C2101&idMarca=&idTipoPosto=2&idDistrito=11&idsMunicipios=&qtdPorPagina=50&pagina=1  

4. Request:
Filtros: 
    Combustível: 13
    Distrito: Lisboa
    Município: Null
    Tipo de Posto: Outros
    Marca: Null
https://precoscombustiveis.dgeg.gov.pt/api/PrecoComb/PesquisarPostos?idsTiposComb=2115%2C1143%2C1141%2C1142%2C3400%2C3210%2C3205%2C3405%2C3201%2C2150%2C2155%2C2105%2C2101&idMarca=&idTipoPosto=3&idDistrito=11&idsMunicipios=&qtdPorPagina=50&pagina=1


5. 
https://precoscombustiveis.dgeg.gov.pt/api/PrecoComb/PesquisarPostos?idsTiposComb=2115%2C1143%2C1141%2C1142%2C3400%2C3210%2C3205%2C3405%2C3201%2C2150%2C2155%2C2105%2C2101&idMarca=&idTipoPosto=&idDistrito=&idsMunicipios=&qtdPorPagina=50&pagina=1
Filtros: 
    Combustível: 13
    Distrito: Null
    Município: Null
    Tipo de Posto: Null
    Marca: Null
Ex. 
    "status": true,
    "mensagem": "sucesso",
    "resultado": [
        {
            "Id": 93702,
            "Nome": "PRIO  Montalegre",
            "TipoPosto": "Outro",
            "Municipio": "Montalegre",
            "Preco": "1,139 €",
            "Marca": "PRIO",
            "Combustivel": "Gasóleo especial",
            "DataAtualizacao": "2026-09-09 13:40",
            "Distrito": "Vila Real",
            "Morada": "Av. Nuno Álvares Pereira",
            "Localidade": "Montalegre",
            "CodPostal": "5470-203",
            "Latitude": 41.8233,
            "Longitude": -7.790686,
            "Quantidade": 13604
        },
        {
            "Id": 94625,
            "Nome": "ASOTA-EXP.A.S.COMB.LUB.OTA LDA",
            "TipoPosto": "Outro",
            "Municipio": "Alenquer",
            "Preco": "1,164 €",
            "Marca": "GALP",
            "Combustivel": "Gasóleo colorido",
            "DataAtualizacao": "2026-09-12 00:00",
            "Distrito": "Lisboa",
            "Morada": "IC2 Km 41 - Ota",
            "Localidade": "Ota",
            "CodPostal": "2580-243",
            "Latitude": 39.09391,
            "Longitude": -8.99221,
            "Quantidade": 13604
"""