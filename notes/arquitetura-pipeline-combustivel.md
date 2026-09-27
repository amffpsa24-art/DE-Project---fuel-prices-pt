# Arquitetura — Pipeline de Preços de Combustível (Portugal)

## 1. Fonte de dados: o que existe realmente

A DGEG **não tem uma API pública documentada e estável**. O que existe:

- **`precoscombustiveis.dgeg.gov.pt/estatistica/postos/`** — página de pesquisa com filtros (distrito, município, tipo de posto, marca) e botão **"Exportar para CSV"**. É a via mais estável e "legítima" para obter a lista de postos e preços atuais.
- **Endpoint interno usado pelo mapa** (não documentado, descoberto via DevTools do browser): algo como `GetDadosPostoMapa?id={id}&f=json`, que devolve os combustíveis e preços de um posto específico. Útil para polling granular por posto, mas é um endpoint de front-end, não uma API pública com contrato — pode mudar sem aviso.
- O portal também publica **estatísticas agregadas** (preço médio diário, etc.) numa secção `/estatistica/`, mas isso é agregado, não ao nível do posto.
- Nota de ToS do site: *"proibida a sua utilização para fins comerciais"* — para portfolio/uso pessoal não é problema, mas não é uma base para produto comercial, e vale a pena ser "bom cidadão" (poucos pedidos, com atraso entre eles, user-agent identificável, cache agressivo).

**Implicação prática:** antes de escrever uma linha de código de ingestão, o primeiro passo real do projeto é abrir o DevTools (Network tab) no portal, filtrar por XHR/Fetch, e mapear:
1. O endpoint de **pesquisa/listagem** (o que alimenta o botão "Exportar CSV" ou a tabela de resultados) — para obter todos os postos de uma vez.
2. O endpoint de **detalhe por posto** (o `GetDadosPostoMapa`) — para preços atualizados.

Isto é trabalho de reverse-engineering leve, não de "encontrar a doc da API" — e é em si uma competência relevante para DE (lidar com fontes de dados imperfeitas é o dia a dia real do trabalho).

---

## 2. Princípio geral: 3 fases, não 1 arquitetura

Dado o teu nível atual (Python/SQL confortável, Spark/Databricks/Azure em aprendizagem), construir logo a stack completa (Azure + Databricks + Delta + ADF) sem nunca teres dados fluindo é o erro clássico — arriscas meses em setup de infraestrutura sem nunca teres um dashboard a funcionar. A sequência recomendada:

| Fase | Objetivo | O que prova |
|---|---|---|
| **Fase 1 — MVP local** | Pipeline ponta-a-ponta simples, a correr | Sabes construir um pipeline completo, mesmo que simples |
| **Fase 2 — Cloud + Lake** | Introduzir Azure Blob + Delta Lake | Sabes trabalhar com armazenamento em camadas (raw/bronze/silver/gold) |
| **Fase 3 — Spark/Databricks/Orquestração** | Substituir processamento pandas por Spark, orquestrar com Databricks Workflows/ADF | Sabes a stack-alvo completa |

Cada fase é **funcional isoladamente** — no fim da Fase 1 já tens algo apresentável no GitHub. Isto é importante para candidaturas: um projeto simples mas completo bate um projeto ambicioso mas a meio.

---

## 3. Fase 1 — MVP (Python + SQL + dashboard básico)

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│ DGEG (site) │ ──▶ │ ingest.py     │ ──▶ │ PostgreSQL   │ ──▶ │ Streamlit /  │
│ endpoints   │     │ (requests +   │     │ (raw + fact  │     │ Plotly Dash  │
│ (postos +   │     │  retries +    │     │  table)      │     │ dashboard    │
│  preços)    │     │  logging)     │     │              │     │              │
└─────────────┘     └──────────────┘     └─────────────┘     └──────────────┘
                            │
                            ▼
                    scheduler: cron local
                    ou GitHub Actions
                    (1x/dia)
```

**Componentes:**
- **Ingestão (`ingest.py`)**: pull dos postos + preços, grava um snapshot JSON bruto por execução (com timestamp) e faz upsert numa tabela `postos` (dimensão) e insert numa tabela `precos_historico` (facto, append-only).
- **Storage**: PostgreSQL (já conheces). Duas tabelas mínimas:
  - `dim_postos(id_posto, nome, marca, morada, concelho, distrito, lat, lon)`
  - `fact_precos(id_posto, tipo_combustivel, preco, data_recolha)`
- **Agendamento**: GitHub Actions com cron schedule (`.github/workflows/ingest.yml`), correndo 1x/dia — é grátis, versionado, e **mostra competência de CI/CD** no portfolio sem precisares de servidor próprio.
- **Dashboard**: Streamlit ligado ao Postgres — 3 visões mínimas: evolução de preço médio por concelho, comparação entre marcas, posto mais barato por área.

**Porquê começar aqui e não em Azure:** consegues ter isto a correr e a acumular dados reais em 1-2 semanas, o que já te dá histórico suficiente para os gráficos de evolução temporal terem piada quando avançares para as fases seguintes.

---

## 4. Fase 2 — Introduzir camada cloud e conceitos de Data Lake

```
DGEG ──▶ ingest.py ──▶ Azure Blob Storage (raw/, partitionado por data)
                              │
                              ▼
                    transform.py (pandas, corre localmente ou em
                    Azure Function) — lê raw JSON, limpa, valida
                              │
                              ▼
                    Delta Lake (tabelas bronze/silver/gold)
                    ou continua em Postgres como "gold" por agora
                              │
                              ▼
                        Streamlit/Power BI
```

Aqui introduzes:
- **Raw layer real**: os JSON brutos da DGEG vão para Blob Storage, particionados `raw/ano=2026/mes=09/dia=10/`, antes de qualquer transformação — prática padrão de DE (nunca perdes o dado original).
- **Conceito bronze/silver/gold**: bronze = raw ingerido tal-e-qual, silver = limpo e validado (tipos corretos, deduplicado), gold = agregado para consumo (preço médio por concelho/dia, por marca/dia).
- Podes manter o Postgres como camada "gold" nesta fase — não precisas de saltar logo para Delta Lake só para ter a palavra no CV; introduz Delta quando fizeres sentido com Spark na Fase 3.

---

## 5. Fase 3 — Stack alvo completa

```
Azure Data Factory (schedule) ──▶ pull DGEG ──▶ Azure Data Lake (raw)
                                                        │
                                                        ▼
                                          Databricks (Spark) — Workflows
                                          bronze ──▶ silver ──▶ gold
                                          (Delta Lake tables)
                                                        │
                                                        ▼
                                          Power BI / Streamlit-on-Delta
```

- **Ingestão**: passa de script Python local para Azure Data Factory (pipeline com Web Activity a chamar o endpoint, ou copy activity), ou mantém o script Python mas correndo como Databricks Job — ambas são defensáveis em entrevista.
- **Processamento**: notebooks Databricks em PySpark — mesmo com o volume de dados desta fonte (não é big data, são ~4000-7000 postos em Portugal), o valor aqui é **demonstrar competência técnica em Spark**, não resolver um problema de volume real. É legítimo dizeres isso em entrevista: "escolhi Spark/Databricks para demonstrar a stack, sabendo que o volume não o exige."
- **Orquestração**: Databricks Workflows (mais simples de configurar) ou ADF (mais "enterprise", mais peso no CV se a vaga é Azure-heavy).
- **Delta Lake**: tabelas bronze/silver/gold geridas com merge/upsert (para lidar com atualizações de preço do mesmo posto).

---

## 6. Estrutura de repositório para portfolio

```
fuel-prices-pt/
├── README.md                 ← contexto, arquitetura (diagrama), como correr, screenshots do dashboard
├── docs/
│   └── architecture.md       ← este documento, evoluído
├── ingestion/
│   ├── ingest.py
│   └── dgeg_client.py        ← wrapper dos endpoints DGEG (isolado = fácil de testar/mockar)
├── transform/
│   └── transform.py
├── dashboard/
│   └── app.py                ← Streamlit
├── .github/workflows/
│   └── ingest.yml            ← GitHub Actions cron
├── tests/
├── requirements.txt
└── data/                     ← .gitignored, ou pequena amostra para demo
```

**README deve incluir:** motivação, diagrama de arquitetura, decisões técnicas e trade-offs (ex: "porquê Postgres na Fase 1 e não já Delta Lake"), como correr localmente, e um GIF/screenshot do dashboard.

---

## 7. Próximo passo imediato

Antes de escrever `ingest.py`, o trabalho é: abrir o portal DGEG, DevTools → Network, filtrar postos por um distrito, e capturar o request exato que devolve a lista (URL, método, parâmetros, forma da resposta). Posso ajudar-te a escrever esse `dgeg_client.py` assim que tiveres esse endpoint mapeado — ou, se preferires, começamos já por explorar o endpoint conhecido (`GetDadosPostoMapa`) para validar a forma dos dados de um posto individual antes de ires atrás do endpoint de listagem.
