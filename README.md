# ROI Agent — Agente de Inteligência para Marketing Digital

Agente de IA que consulta um **Marketing Data Warehouse** para responder perguntas em português sobre ROI, CAC, LTV, pipeline de vendas e atribuição de canais.

---

## Sumário

- [Arquitetura](#arquitetura)
- [Estrutura dos Arquivos](#estrutura-dos-arquivos)
- [Quick Start](#quick-start)
- [Modos de Operação](#modos-de-operação)
- [Data Warehouse de Marketing](#data-warehouse-de-marketing)
- [Catálogo de Endpoints](#catálogo-de-endpoints)
- [Modelos de Atribuição](#modelos-de-atribuição)
- [Métricas de Marketing](#métricas-de-marketing)

---

## Arquitetura

```
┌──────────────────────────────────────────────────────────────────┐
│                    CAMADA DE APRESENTAÇÃO                         │
│  CLI Interativa │  Demo Automática  │  --mock (sem API key)      │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                   CAMADA DE AGENTE (LangGraph)                    │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │                    StateGraph                             │     │
│  │                                                           │     │
│  │  Loop de Raciocínio (tool-calling loop):                  │     │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────────────┐    │     │
│  │  │ Pergunta │───▶│   LLM    │───▶│ Decide tool_call │    │     │
│  │  │ do usuário│   │ (OpenAI) │    │ based on context │    │     │
│  │  └──────────┘    └──────────┘    └────────┬─────────┘    │     │
│  │                                              │            │     │
│  │  ┌───────────────────────────────────────────▼────────┐   │     │
│  │  │            Ferramentas (via MCP)                    │   │     │
│  │  │  Geradas automaticamente do OpenAPI contract        │   │     │
│  │  │  (dw_schema, list_channels, list_campaigns,         │   │     │
│  │  │   campaign_performance, cac_analysis,               │   │     │
│  │  │   ltv_cac_ratio, pipeline_overview,                 │   │     │
│  │  │   simulate_attribution, channel_overlap,            │   │     │
│  │  │   roi_waterfall, ...)                               │   │     │
│  │  └─────────────────────────────────────────────────────┘   │     │
│  └─────────────────────────────────────────────────────────┘     │
└───────────────────────────┬──────────────────────────────────────┘
                            │  MCP (Model Context Protocol)
┌───────────────────────────▼──────────────────────────────────────┐
│                   CAMADA MCP (Model Context Protocol)             │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  mcp_server.py (FastMCP)                                 │     │
│  │  Porta 9000 · Transporte HTTP                            │     │
│  │  Lê openapi_contract.json e expõe como tools MCP        │     │
│  └──────────────────────┬──────────────────────────────────┘     │
└───────────────────────────┬──────────────────────────────────────┘
                            │  HTTP
┌───────────────────────────▼──────────────────────────────────────┐
│                   CAMADA DE DADOS (FastAPI)                       │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  mock_dw_marketing.py                                    │     │
│  │  Porta 8000 · 18 endpoints REST                          │     │
│  │                                                          │     │
│  │  ┌─────────────┐  ┌─────────────┐  ┌────────────────┐   │     │
│  │  │ dim_channel │  │dim_campaign │  │ fact_daily_spend│   │     │
│  │  │ (10 canais) │  │ (12 camps)  │  │ (~5k linhas)    │   │     │
│  │  ├─────────────┤  ├─────────────┤  ├────────────────┤   │     │
│  │  │ fact_leads  │  │ conversions │  │ fact_crm_pipeline   │     │
│  │  │ (~3k leads) │  │ (~1.2k)     │  │                │   │     │
│  │  ├─────────────┤  ├─────────────┤  ├────────────────┤   │     │
│  │  │dim_customer │  │ overlap     │  │                │   │     │
│  │  │ (500 client)│  │ (matriz)    │  │                │   │     │
│  │  └─────────────┘  └─────────────┘  └────────────────┘   │     │
│  └─────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────┘
```

### Fluxo de Execução

1. Usuário faz uma pergunta em português (ex: "Qual canal tem o melhor ROI?")
2. `agent.py` recebe a pergunta e envia ao **StateGraph** do LangGraph
3. O nó **agent** (LLM com system prompt) analisa e decide qual tool chamar
4. Se o LLM retorna `tool_calls`, o grafo vai para o nó **tools**
5. O nó **tools** executa a chamada via MCP → FastAPI (DW mock)
6. O resultado volta como `ToolMessage` para o nó **agent**
7. O LLM analisa o resultado e decide: mais tools ou resposta final
8. Quando não há mais `tool_calls`, o grafo encerra e exibe a resposta

---

## Estrutura dos Arquivos

| Arquivo | Função |
|---|---|
| **`agent.py`** | Agente principal com LangGraph + MCP. Conecta ao MCP Server, obtém tools, monta o grafo de execução (tool-calling loop) e provê interface interativa/demo. |
| **`mcp_server.py`** | Servidor MCP (FastMCP) que lê o `openapi_contract.json` e expõe todos os endpoints do DW como ferramentas MCP no transporte HTTP (porta 9000). |
| **`mock_dw_marketing.py`** | Mock do Marketing Data Warehouse em FastAPI (porta 8000). Contém dados sintéticos de 10 canais, 12 campanhas, ~5k gastos diários, ~3k leads, ~1.2k vendas com atribuição multi-touch, 500 clientes com LTV, matriz de overlap e pipeline CRM. |
| **`openapi_contract.json`** | Contrato OpenAPI 3.1 completo documentando todos os 18 endpoints do DW. Usado pelo `mcp_server.py` para gerar as ferramentas MCP automaticamente. |
| **`pyproject.toml`** | Configuração do projeto Python (dependências, versão). |

---

## Quick Start

```bash
# 1. Instale as dependências
uv sync          # ou: pip install -e .

# 2. Terminal 1 — Mock Data Warehouse
python mock_dw_marketing.py
# → http://localhost:8000/docs (Swagger)

# 3. Terminal 2 — MCP Server
python mcp_server.py
# → http://localhost:9000/mcp

# 4. Terminal 3 — Agente (modo interativo)
export OPENAI_API_KEY="sk-..."
python agent.py
```

---

## Modos de Operação

### Modo Interativo (padrão)

```bash
export OPENAI_API_KEY="sk-..."
python agent.py
```

Agente com LLM real (OpenAI GPT-4) para raciocinar, selecionar ferramentas e gerar respostas em português.

### Modo Demo

```bash
python agent.py --demo
```

Executa 8 perguntas pré-definidas automaticamente. Requer `OPENAI_API_KEY` ou use com `--mock`.

### Modo Mock (sem API key)

```bash
python agent.py --mock
```

Usa um `RunnableLambda` que simula a seleção de ferramentas baseada em palavras-chave. Ideal para testar o fluxo sem gastar tokens. **Limitação:** apenas 1 rodada de tool call, sem raciocínio multi-etapas.

```bash
python agent.py --mock --demo   # demo completa sem API key
```

---

## Data Warehouse de Marketing

### Modelo Dimensional (Star Schema)

```
                    ┌──────────────────┐
                    │   dim_channel    │
                    │  PK: id          │
                    │  nome, tipo,     │
                    │  modelo_attr,    │
                    │  cpc_medio       │
                    └────────┬─────────┘
                             │
┌─────────────────┐    ┌────▼────┐    ┌──────────────────┐
│  dim_campaign   │    │  FACT   │    │  dim_customer    │
│  PK: id         │◄───│ TABLES  │───▶│  PK: customer_id │
│  nome, canal_id │    │         │    │  canal_aquisicao │
│  objetivo,      │    └─────────┘    │  ltv_12m, ltv_tot│
│  budget, período│                   │  churn_risk      │
└─────────────────┘                   └──────────────────┘
```

### Canais de Marketing (10 canais)

| ID | Canal | Tipo | CPC Médio |
|---|---|---|---|
| 1 | Google Ads | search | R$ 2,80 |
| 2 | Meta Ads | social | R$ 1,90 |
| 3 | YouTube | video | R$ 0,45 |
| 4 | LinkedIn | social_b2b | R$ 5,50 |
| 5 | TikTok | social | R$ 1,20 |
| 6 | Email Marketing | organic | R$ 0,00 |
| 7 | Organic Search | organic | R$ 0,00 |
| 8 | Programática | display | R$ 0,80 |
| 9 | Afiliados | partnership | R$ 0,00 |
| 10 | Shopee / Marketplaces | marketplace | R$ 0,00 |

### Campanhas (12 campanhas)

Distribuídas entre os canais com objetivos variados: `conversao`, `lead`, `alcance`, `venda`, `retencao`, `branding`.

### Dados Sintéticos

- **~5.000** registros de gasto diário (fact_daily_spend)
- **~3.000** leads individuais com status (MQL → SQL → Opp → Won → Perdido)
- **~1.200** vendas com caminho de atribuição multi-touch (1-5 touchpoints)
- **500** clientes com LTV de 12 meses e LTV total
- **Matriz de overlap** entre pares de canais com lift

---

## Catálogo de Endpoints

O DW mock expõe 18 endpoints REST (FastAPI) na porta 8000:

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/v2/dw/schema` | Schema completo do DW |
| `GET` | `/v2/dw/channels` | Lista canais |
| `GET` | `/v2/dw/channels/{id}` | Detalhe do canal |
| `GET` | `/v2/dw/campaigns` | Lista campanhas (filtros: canal, objetivo) |
| `GET` | `/v2/dw/campaigns/{id}` | Detalhe da campanha |
| `GET` | `/v2/dw/campaigns/{id}/performance` | Performance completa |
| `GET` | `/v2/dw/campaigns/{id}/daily-spend` | Gasto diário |
| `GET` | `/v2/dw/leads` | Leads (filtros: campaign_id, canal, status) |
| `GET` | `/v2/dw/conversions` | Vendas com atribuição |
| `GET` | `/v2/dw/attribution-models` | Modelos disponíveis |
| `POST` | `/v2/dw/attribution/simular` | Simula atribuição |
| `GET` | `/v2/dw/pipeline` | Pipeline CRM |
| `GET` | `/v2/dw/customers` | Clientes com LTV |
| `GET` | `/v2/dw/cac-analysis` | CAC por canal + blendado |
| `GET` | `/v2/dw/ltv-cac-ratio` | LTV:CAC por canal |
| `GET` | `/v2/dw/overlap` | Sobreposição entre canais |
| `GET` | `/v2/dw/roi-waterfall` | ROI Waterfall |
| `POST` | `/v2/dw/query` | Query SQL simulada |

---

## Modelos de Atribuição

A atribuição define quanto crédito cada canal recebe por uma venda. Quando um cliente interage com múltiplos canais antes de comprar, o modelo determina a distribuição:

| Modelo | Regra | Ideal para |
|---|---|---|
| **first_click** | 100% para o primeiro canal | Entender o que atrai novos clientes |
| **last_click** | 100% para o último canal | Padrão na maioria das plataformas |
| **linear** | Igual para todos | Quando todos os canais contribuem igual |
| **time_decay** | Peso exponencial: mais crédito a canais próximos da conversão | Quando o último clique é mais decisivo |
| **data_driven** | Distribuição algorítmica simulada | Visão mais justa (usada pelo GA4) |

---

## Métricas de Marketing

### ROI — Return on Investment

```
ROI Simples (%) = (Receita - Investimento) / Investimento × 100
ROAS (R$)       = Receita / Gasto de Mídia
ROI Líquido (%) = (Lucro Líquido / (Investimento + Custos Op.)) × 100
```

### CAC — Customer Acquisition Cost

```
CAC por Canal = Investimento no Canal / Vendas do Canal
CAC Blendado  = Investimento Total / Total de Clientes
```

### LTV — Lifetime Value

```
LTV = Receita total gerada por um cliente durante todo o relacionamento
LTV:12m = Receita nos primeiros 12 meses
```

### LTV:CAC Ratio

```
LTV:CAC = LTV Médio do Canal / CAC do Canal

> 3x  → Saudável 🟢
1-3x  → Aceitável 🟡
< 1x  → Crítico 🔴
```

### Pipeline CRM

```
MQL  (Marketing Qualified Lead)  → lead qualificado pelo marketing
SQL  (Sales Qualified Lead)       → lead qualificado pelo sales
Opp  (Oportunidade)               → em negociação ativa
Won  (Ganho/Fechada)             → venda concluída

Taxa de Conversão = Won / MQL × 100
```

### ROI Waterfall

```
1. Media Spend        → gasto com anúncios (bruto)
2. + Receita          → receita atribuída às campanhas
3. = Lucro Bruto      → receita - media spend
4. - Custos Op.       → 15% do media spend (ferramentas, time)
5. = Lucro Líquido    → lucro real
6. = ROI Líquido %    → (lucro líquido / (media + custos)) × 100
```

### Channel Overlap

```
Coocorrência = % das conversões onde dois canais aparecem juntos
Lift = P(conversão | canal A + B) / P(conversão | canal A sozinho)

Lift > 1  → sinergia positiva (canais se reforçam)
Lift < 1  → canibalização (canais competem entre si)
```
