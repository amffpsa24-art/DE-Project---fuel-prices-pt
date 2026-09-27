# Dia 1 — Log do processo: Descoberta da fonte de dados (DGEG)

Data: 11-12 setembro 2026
Objetivo do dia: identificar e validar como aceder aos dados de preços de combustível da DGEG, sem escrever ainda código de produção.

---

## Passo 1 — Reconhecimento do site

**O que foi feito:** aberto o portal `precoscombustiveis.dgeg.gov.pt`, secção de pesquisa de postos, e o DevTools do browser (F12 → separador Network, filtro Fetch/XHR).

**Porquê:** a DGEG não publica uma API pública documentada. A única forma de saber que dados existem e em que formato é observar os pedidos que a própria página faz ao servidor quando o utilizador interage com os filtros — esta técnica chama-se inspeção de rede / engenharia reversa de API interna.

---

## Passo 2 — Identificação do endpoint principal

**O que foi feito:** ao pesquisar postos com filtros (distrito, tipo de posto), foi capturado o pedido real feito pelo browser:

```
GET https://precoscombustiveis.dgeg.gov.pt/api/PrecoComb/PesquisarPostos
```

com parâmetros `idsTiposComb`, `idMarca`, `idTipoPosto`, `idDistrito`, `idsMunicipios`, `qtdPorPagina`, `pagina`.

**Porquê:** este é o endpoint que devolve os dados que interessam ao projeto (postos + preços). Saber a URL exata e os parâmetros é o pré-requisito para automatizar a recolha em Python — sem isto não há ingestão possível.

---

## Passo 3 — Teste: o filtro de distrito é obrigatório?

**O que foi feito:** removido o valor de `idDistrito` da URL (deixado vazio) e o pedido repetido diretamente no browser.

**Resultado:** a resposta trouxe postos de vários distritos (Aveiro, Lisboa, Vila Real), confirmando que o filtro é opcional.

**Porquê importa:** sem esta confirmação, o plano de ingestão teria de iterar por 18 distritos separadamente. Com o filtro opcional, a recolha nacional pode ser feita com uma única sequência de pedidos paginados — simplifica bastante o desenho do `dgeg_client.py`.

---

## Passo 4 — Entender o campo `Quantidade`

**O que foi feito:** observado que o campo `Quantidade` aparece repetido, com o mesmo valor, em todas as linhas de uma mesma resposta (ex: `1101` para Aveiro, `18` para um filtro estreito em Lisboa).

**Interpretação:** não é uma quantidade de combustível em stock (não faria sentido no contexto). É o **total de registos que correspondem ao filtro aplicado**, repetido por linha em vez de aparecer uma vez só no topo da resposta — padrão comum em APIs .NET mais antigas.

**Porquê importa:** este campo é a base para calcular quantas páginas são necessárias para uma recolha completa (`páginas = ceil(Quantidade / qtdPorPagina)`), sem o qual não haveria forma de saber quando parar de paginar.

---

## Passo 5 — Confirmar a granularidade dos dados

**O que foi feito:** analisado um exemplo onde o mesmo posto (`Id: 93086`, Intermarché de Famões) aparece três vezes na mesma resposta, cada vez com um `Combustivel` diferente (Gasolina simples 95, Gasóleo simples, Gasolina especial 95) e o respetivo `Preco`, mas com os restantes campos (morada, marca, coordenadas) repetidos e idênticos.

**Conclusão:** cada linha da API representa um par **(posto, tipo de combustível)**, não um posto com todos os preços agregados dentro. Um posto real vai gerar tantas linhas quantos os combustíveis que vende.

**Porquê importa:** isto define diretamente o modelo de dados do projeto — os campos fixos do posto (nome, marca, morada, município, distrito, coordenadas, tipo de posto) mapeiam para uma tabela de dimensão (`dim_postos`), e o par combustível+preço+data mapeia para uma tabela de factos (`fact_precos`), ligados pelo `Id` do posto. Sem perceber a granularidade da resposta, o desenho das tabelas teria sido feito às cegas.

NOTA: 
{"Id": 93086, "Nome": "Intermarché de Famões", ..., "Combustivel": "Gasolina simples 95", "Preco": "2,029 €"}
{"Id": 93086, "Nome": "Intermarché de Famões", ..., "Combustivel": "Gasóleo simples", "Preco": "2,039 €"}
{"Id": 93086, "Nome": "Intermarché de Famões", ..., "Combustivel": "Gasolina especial 95", "Preco": "2,059 €"}

Repara bem: o Id, o Nome, a Morada, a Latitude/Longitude, o Municipio — tudo isso é exatamente igual nas três linhas, porque é o mesmo posto físico. A única coisa que muda entre as três linhas é o Combustivel e o Preco correspondente.

Ou seja, a API não te dá "um posto, com uma lista de preços lá dentro" (o que seria uma linha por posto, com um campo tipo precos: [{...}, {...}, {...}]). Em vez disso, dá-te uma linha nova por cada combinação de posto + tipo de combustível. Se um posto vende 5 combustíveis diferentes, esse posto vai aparecer 5 vezes na tua lista de resultados, uma vez por combustível.

É por isso que digo que a "unidade" de cada linha, a granularidade, é o par (posto, combustível), e não só o posto. Isto é o que se chama, em bases de dados, o grão de uma tabela — a pergunta "o que é que uma linha representa, exatamente?" E aqui a resposta é "um preço de um combustível específico, num posto específico, numa data específica", não "um posto".
---

## Passo 6 — Testar o volume total e o tamanho de página

**O que foi feito:** removidos todos os filtros (distrito, tipo de posto — mantendo os 13 IDs de combustível, que cobrem todos os tipos existentes) e observado `Quantidade = 13604` para Portugal inteiro. De seguida, testado `qtdPorPagina=1000` em vez de `50`.

**Porquê:** o volume total determina quantos pedidos por dia o script de ingestão vai precisar de fazer. Com 50 por página seriam 273 pedidos/dia; a confirmar-se que 1000 por página funciona, reduz para cerca de 14 pedidos/dia — mais rápido, mais simples de programar, e mais leve para o servidor da DGEG (relevante dado o aviso de uso não comercial/moderado no site).

---

## Passo 7 — Descoberta lateral: outros endpoints

**O que foi feito:** durante os testes, apareceram dois endpoints adicionais não usados para já:
- `ListarDadosPostos` — parece ser um índice mestre de postos registados, mas sem dados de preço/localização preenchidos.
- Um endpoint de municípios por distrito, disparado automaticamente ao escolher um distrito na interface.

**Porquê registar mesmo não os usando:** ficam documentados para referência futura (ex: detetar postos novos ou inativos), sem desviar o foco do essencial da v1 do pipeline.

---

## Passo 8 — Registo formal (`notes/api-discovery.md`)

**O que foi feito:** toda a informação acima consolidada num ficheiro Markdown dentro do repositório (`notes/api-discovery.md`), incluindo URL base, tabela de parâmetros, URL de exemplo completa, forma da resposta JSON, e notas sobre parsing (o campo `Preco` vem como string com vírgula decimal e símbolo de euro, precisa de conversão).

**Porquê:** este ficheiro substitui a necessidade de repetir o trabalho de reverse-engineering sempre que se voltar ao código. É também material direto para o README do projeto — mostra ao avaliador do portfolio que a fonte de dados foi investigada de forma metódica antes de qualquer linha de código de produção.

---

## Resultado do dia

Sem escrever código de ingestão, ficou definido e documentado:
- O endpoint e os parâmetros exatos a usar
- Que a recolha pode ser nacional, sem iterar por distrito
- O volume total de dados (13604 linhas, ~14 páginas com `qtdPorPagina=1000`)
- A granularidade exata da resposta (posto × combustível)
- O mapeamento inicial para o esquema `dim_postos` / `fact_precos`

**Próximo passo (Dia 2):** escrever `ingestion/dgeg_client.py` — uma função Python que, dada uma página, faz o pedido GET e devolve a lista de dicionários já parseada (incluindo a conversão do campo `Preco` de string para número).
