# Descoberta de endpoints — DGEG (Preços de Combustíveis)

Base URL: https://precoscombustiveis.dgeg.gov.pt/api/PrecoComb/

## Endpoint principal: PesquisarPostos

GET /PesquisarPostos

### Parâmetros
| Parâmetro       | Obrigatório? | Descrição                                              |
|-----------------|--------------|----------------------------------------------------------|
| idsTiposComb    | Não          | IDs de combustível separados por vírgula. Vazio = provavelmente ainda filtra, usar os 13 IDs conhecidos para apanhar tudo: 2115,1143,1141,1142,3400,3210,3205,3405,3201,2150,2155,2105,2101 |
| idMarca         | Não          | ID da marca. Vazio = todas |
| idTipoPosto     | Não          | 1 = Auto-estrada, 2 = Área comercial (Hipermercados), 3 = Outros. Vazio = todos |
| idDistrito      | Não          | Vazio = Portugal inteiro (confirmado) |
| idsMunicipios   | Não          | Vazio = todos |
| qtdPorPagina    | Sim          | Testado 50 e 1000, ambos funcionam. Usar 1000 para minimizar nº de pedidos |
| pagina          | Sim          | Começa em 1 |

### URL de exemplo (Portugal inteiro, todos os combustíveis, página 1, 1000 por página)
https://precoscombustiveis.dgeg.gov.pt/api/PrecoComb/PesquisarPostos?idsTiposComb=2115%2C1143%2C1141%2C1142%2C3400%2C3210%2C3205%2C3405%2C3201%2C2150%2C2155%2C2105%2C2101&idMarca=&idTipoPosto=&idDistrito=&idsMunicipios=&qtdPorPagina=1000&pagina=1

### Total de registos (11 set 2026, sem filtro)
Quantidade = 13604 (repetido em todas as linhas do resultado)
Com qtdPorPagina=1000 → 14 páginas para cobrir Portugal inteiro

### Forma da resposta -> Resultado é aa lista de dicionarios, Chave no dicionario, de resposta JSON
{
  "status": true,
  "mensagem": "sucesso",
  "resultado": [
    {
      "Id": 93702,
      "Nome": "PRIO Montalegre",
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
    }
  ]
}

### Notas importantes
- Cada linha = par (posto, tipo de combustível). O mesmo Id de posto aparece várias vezes, uma por combustível vendido.
- Campo "Preco" vem como string com vírgula decimal e símbolo de euro (ex: "1,139 €") — precisa de parsing antes de gravar como número.
- Campo "Quantidade" NÃO é stock de combustível — é o total de linhas que correspondem ao filtro atual (usado para paginação).
- Sem autenticação necessária, sem headers especiais testados até agora.
- Não há campo "totalPaginas" explícito — calcula-se com ceil(Quantidade / qtdPorPagina).

## Endpoint secundário: ListarDadosPostos (não usado por agora)

GET /ListarDadosPostos?qtdPorPagina=9999&pagina=1&orderDesc=

Parece ser um índice mestre de postos registados (Codigo, Nome, DataRegisto, Id), mas
sem dados de preço/morada preenchidos (tudo null). Pode ser útil no futuro para detetar
postos novos/inativos, mas não é necessário para a v1 do pipeline.

## Endpoint auxiliar: municípios por distrito (não usado por agora)

Disparado ao escolher um distrito na UI antes de pesquisar. Devolve lista de municípios
com Id + IdDistrito. Não é necessário porque idDistrito e idsMunicipios vazios já
devolvem Portugal inteiro.



------
------
# Testado qtdPorPagina = 10000. API aceitou e devolveu exatamente 10000 registos sem erro. de 140000 reduz a paginação para 2 pedidos em vez de 14.