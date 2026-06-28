"""
Marketing Data Warehouse – Mock API
====================================
Simula um Data Warehouse real de marketing com:

  - Atribuição multi-touch (last_click, first_click, linear, time_decay)
  - Pipeline completo (MQL → SQL → Opp → Won)
  - LTV por canal e coorte
  - CAC blendado e por canal
  - Sobreposição de canais (channel overlap)
  - ROI Waterfall

Uso: uvicorn mock_dw_marketing:app --port 8000
Docs: http://localhost:8000/docs
"""

import math
import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

random.seed(42)

# ──────────────────────────────────────────────
#  DIMENSIONS
# ──────────────────────────────────────────────

CHANNELS = [
    {"id": 1, "nome": "Google Ads",       "tipo": "search",     "modelo_atribuicao": "data_driven",  "cpc_medio": 2.80},
    {"id": 2, "nome": "Meta Ads",         "tipo": "social",     "modelo_atribuicao": "time_decay",   "cpc_medio": 1.90},
    {"id": 3, "nome": "YouTube",          "tipo": "video",     "modelo_atribuicao": "linear",        "cpc_medio": 0.45,  "vpc_medio": 0.02},
    {"id": 4, "nome": "LinkedIn",         "tipo": "social_b2b", "modelo_atribuicao": "first_click",  "cpc_medio": 5.50},
    {"id": 5, "nome": "TikTok",           "tipo": "social",     "modelo_atribuicao": "last_click",   "cpc_medio": 1.20},
    {"id": 6, "nome": "Email Marketing",  "tipo": "organic",   "modelo_atribuicao": "last_click",   "cpc_medio": 0.00},
    {"id": 7, "nome": "Organic Search",   "tipo": "organic",   "modelo_atribuicao": "linear",        "cpc_medio": 0.00},
    {"id": 8, "nome": "Programática",     "tipo": "display",   "modelo_atribuicao": "time_decay",    "cpc_medio": 0.80,  "cpm_medio": 12.0},
    {"id": 9, "nome": "Afiliados",        "tipo": "partnership","modelo_atribuicao": "last_click",   "cpc_medio": 0.00,  "comissao_pct": 12.0},
    {"id":10, "nome": "Shopee / Marketplaces","tipo": "marketplace","modelo_atribuicao": "last_click","cpc_medio": 0.00, "comissao_pct": 18.0},
]

CAMPANHAS_MOCK = [
    {"id": 1,  "nome": "Google Ads - Inverno 2026",   "canal_id": 1, "objetivo": "conversao", "budget_total": 15000, "inicio": "2026-04-01", "fim": "2026-06-30"},
    {"id": 2,  "nome": "Meta Ads - Coleção Verão",     "canal_id": 2, "objetivo": "conversao", "budget_total": 24000, "inicio": "2026-05-01", "fim": "2026-07-31"},
    {"id": 3,  "nome": "YouTube - Branding Institucional","canal_id": 3, "objetivo": "alcance", "budget_total": 9000,  "inicio": "2026-03-01", "fim": "2026-06-30"},
    {"id": 4,  "nome": "LinkedIn - Geração Demanda B2B","canal_id": 4, "objetivo": "lead",   "budget_total": 36000, "inicio": "2026-01-01", "fim": "2026-12-31"},
    {"id": 5,  "nome": "TikTok - Desafio Viral",       "canal_id": 5, "objetivo": "alcance", "budget_total": 6000,  "inicio": "2026-05-15", "fim": "2026-07-15"},
    {"id": 6,  "nome": "Email CRM - Base Ativa",       "canal_id": 6, "objetivo": "retencao","budget_total": 3000,  "inicio": "2026-01-01", "fim": "2026-12-31"},
    {"id": 7,  "nome": "SEO - Blog Corporativo",       "canal_id": 7, "objetivo": "branding","budget_total": 6000,  "inicio": "2026-01-01", "fim": "2026-12-31"},
    {"id": 8,  "nome": "Programática - Retargeting",   "canal_id": 8, "objetivo": "conversao","budget_total": 12000,"inicio": "2026-04-01", "fim": "2026-06-30"},
    {"id": 9,  "nome": "Afiliados - Rede de Parceiros", "canal_id": 9, "objetivo": "venda",  "budget_total": 8000,  "inicio": "2026-02-01", "fim": "2026-12-31"},
    {"id": 10, "nome": "Shopee - Vitrine Premium",     "canal_id":10, "objetivo": "venda",  "budget_total": 5000,  "inicio": "2026-05-01", "fim": "2026-07-31"},
    {"id": 11, "nome": "Google Ads - Remarketing",     "canal_id": 1, "objetivo": "conversao","budget_total": 8000,  "inicio": "2026-05-01", "fim": "2026-07-31"},
    {"id": 12, "nome": "Meta Ads - Lead Gen",          "canal_id": 2, "objetivo": "lead",   "budget_total": 12000, "inicio": "2026-03-01", "fim": "2026-06-30"},
]

# ──────────────────────────────────────────────
#  FACT TABLES  (mock data gen)
# ──────────────────────────────────────────────

DAILY_SPEND = []
LEADS = []
CONVERSIONS = []
PIPELINE = []
CUSTOMERS = []
OVERLAP = []

def generate_mock_data():
    today = date(2026, 6, 20)

    # Daily spend for last 180 days
    for camp in CAMPANHAS_MOCK:
        start = date.fromisoformat(camp["inicio"])
        end = min(date.fromisoformat(camp["fim"]), today)
        d = start
        while d <= end:
            base = camp["budget_total"] / 90
            noise = random.uniform(0.5, 1.8)
            spend = round(base * noise, 2)
            DAILY_SPEND.append({
                "campaign_id": camp["id"],
                "canal_id": camp["canal_id"],
                "data": d.isoformat(),
                "spend": spend,
                "impressions": int(spend * random.randint(80, 400)),
                "clicks": int(spend * random.randint(15, 60)),
            })
            d += timedelta(days=1)

    # Leads (~3000)
    lead_id = 0
    for camp in CAMPANHAS_MOCK:
        num = random.randint(40, 400)
        for _ in range(num):
            lead_id += 1
            day_offset = random.randint(0, min(180, (today - date.fromisoformat(camp["inicio"])).days))
            lead_date = date.fromisoformat(camp["inicio"]) + timedelta(days=day_offset)
            LEADS.append({
                "lead_id": lead_id,
                "campaign_id": camp["id"],
                "canal_id": camp["canal_id"],
                "data": lead_date.isoformat(),
                "status": random.choices(
                    ["mql", "sql", "oportunidade", "convertido", "perdido"],
                    weights=[20, 15, 10, 25, 30]
                )[0],
                "custo_lead": round(random.uniform(5, 120), 2),
            })

    # Conversions (~1200 sales) with multi-touch attribution paths
    conv_id = 0
    for camp in CAMPANHAS_MOCK:
        num = random.randint(10, 200)
        for _ in range(num):
            conv_id += 1
            day_offset = random.randint(7, 90)
            conv_date = date.fromisoformat(camp["inicio"]) + timedelta(days=day_offset)
            if conv_date > today:
                continue
            revenue = round(random.uniform(50, 8000), 2)
            # Attribution path: 1-5 touchpoints before conversion
            path_length = random.randint(1, 5)
            channel_ids = [camp["canal_id"]]
            for _ in range(path_length - 1):
                channel_ids.append(random.choice([1, 2, 3, 4, 5, 6, 7, 8]))
            random.shuffle(channel_ids)

            CONVERSIONS.append({
                "conv_id": conv_id,
                "campaign_id": camp["id"],
                "canal_primary": camp["canal_id"],
                "attribution_path": channel_ids,
                "data": conv_date.isoformat(),
                "receita": revenue,
                "itens": random.randint(1, 5),
                "status": "won",
                "days_to_convert": random.randint(1, 60),
            })

    # Pipeline CRM
    for camp in CAMPANHAS_MOCK:
        for stage in ["mql", "sql", "oportunidade", "won"]:
            count = random.randint(5, 80)
            for _ in range(count):
                PIPELINE.append({
                    "campaign_id": camp["id"],
                    "canal_id": camp["canal_id"],
                    "estagio": stage,
                    "valor": round(random.uniform(100, 15000), 2),
                    "data_criacao": (today - timedelta(days=random.randint(1, 120))).isoformat(),
                })

    # Customers with LTV
    for i in range(1, 500):
        canal = random.choice(CHANNELS)
        camp = random.choice(CAMPANHAS_MOCK)
        first_purchase = today - timedelta(days=random.randint(30, 720))
        CUSTOMERS.append({
            "customer_id": i,
            "canal_aquisicao": canal["id"],
            "campaign_aquisicao": camp["id"],
            "data_primeira_compra": first_purchase.isoformat(),
            "total_compras": random.randint(1, 20),
            "ltv_12m": round(random.uniform(100, 12000), 2),
            "ltv_total": round(random.uniform(200, 30000), 2),
            "churn_risk": random.choice(["low", "medium", "high"]),
            "ultima_compra": (first_purchase + timedelta(days=random.randint(30, 400))).isoformat(),
        })

    # Channel overlap (pairwise correlation)
    for i, ch1 in enumerate(CHANNELS):
        for ch2 in CHANNELS[i+1:]:
            if random.random() < 0.4:
                OVERLAP.append({
                    "canal_a": ch1["id"],
                    "canal_b": ch2["id"],
                    "nome_a": ch1["nome"],
                    "nome_b": ch2["nome"],
                    "coocorrencia_pct": round(random.uniform(5, 60), 1),
                    "lift": round(random.uniform(1.0, 3.5), 2),
                })

generate_mock_data()


# ──────────────────────────────────────────────
#  AUX FUNCTIONS
# ──────────────────────────────────────────────

def get_campaign(id_: int):
    for c in CAMPANHAS_MOCK:
        if c["id"] == id_:
            return c
    raise HTTPException(404, f"Campanha {id_} não encontrada")

def get_channel(id_: int):
    for c in CHANNELS:
        if c["id"] == id_:
            return c
    raise HTTPException(404, f"Canal {id_} não encontrado")

def filter_date(items, data_field: str, start: date, end: date):
    return [i for i in items if start <= date.fromisoformat(i[data_field]) <= end]

def apply_attribution(path: List[int], receita: float, model: str) -> dict[int, float]:
    """Distribui receita entre canais conforme modelo de atribuição."""
    weights = {}
    n = len(path)
    if model == "first_click":
        weights[path[0]] = receita
    elif model == "last_click":
        weights[path[-1]] = receita
    elif model == "linear":
        share = round(receita / n, 2)
        for ch in path:
            weights[ch] = weights.get(ch, 0) + share
    elif model == "time_decay":
        total_w = sum(2 ** i for i in range(n))
        for i, ch in enumerate(path):
            weights[ch] = weights.get(ch, 0) + round(receita * (2 ** i) / total_w, 2)
    else:  # data_driven (simulated)
        share = round(receita / n, 2)
        for ch in path:
            weights[ch] = weights.get(ch, 0) + share
    return weights


# ──────────────────────────────────────────────
#  SCHEMAS
# ──────────────────────────────────────────────

class ChannelOut(BaseModel):
    id: int
    nome: str
    tipo: str
    modelo_atribuicao: str
    cpc_medio: float

class CampaignOut(BaseModel):
    id: int
    nome: str
    canal: str
    objetivo: str
    budget_total: float
    inicio: str
    fim: str

class DailySpendOut(BaseModel):
    data: str
    spend: float
    impressions: int
    clicks: int

class LeadOut(BaseModel):
    lead_id: int
    data: str
    status: str
    custo_lead: float
    campaign_id: int
    canal_nome: Optional[str] = None

class ConversionOut(BaseModel):
    conv_id: int
    data: str
    receita: float
    itens: int
    dias_para_converter: int
    attribution_path: List[int]
    canais_credito: Optional[dict] = None

class PipelineStage(BaseModel):
    estagio: str
    quantidade: int
    valor_total: float

class CustomerOut(BaseModel):
    customer_id: int
    canal_aquisicao: int
    ltv_12m: float
    ltv_total: float
    total_compras: int
    churn_risk: str

class CacAnalysisItem(BaseModel):
    canal: str
    investimento: float
    leads: int
    vendas: int
    cac: float

class LtvCacRatio(BaseModel):
    canal: str
    cac: float
    ltv_medio_12m: float
    ratio: float
    saude: str

class OverlapOut(BaseModel):
    canal_a: str
    canal_b: str
    coocorrencia_pct: float
    lift: float

    class Config:
        json_schema_extra = {
            "example": {
                "canal_a": "Google Ads",
                "canal_b": "Meta Ads",
                "coocorrencia_pct": 35.2,
                "lift": 1.85,
            }
        }

class RoiWaterfall(BaseModel):
    etapa: str
    valor: float

class AttributeSimulationRequest(BaseModel):
    campaign_id: int
    modelo: str = Field("data_driven", description="first_click | last_click | linear | time_decay | data_driven")

class AttributeSimulationResponse(BaseModel):
    campanha: str
    modelo: str
    distribuicao: dict

# ──────────────────────────────────────────────
#  APP
# ──────────────────────────────────────────────

app = FastAPI(
    title="Marketing Data Warehouse – Mock API",
    description="Data Warehouse de Marketing completo com atribuição multi-touch, "
                "pipeline CRM, LTV:CAC, channel overlap e ROI Waterfall.",
    version="2.0.0",
)


# ─────  SCHEMA  ─────

@app.get("/v2/dw/schema", tags=["Meta"])
def dw_schema():
    return {
        "data_warehouse": "marketing_dw",
        "versao": "2.0",
        "tabelas": {
            "dim_channel": "Canais de marketing com metadata",
            "dim_campaign": "Campanhas com objetivo, budget, período",
            "fact_daily_spend": "Gasto diário por campanha (impressões, cliques, spend)",
            "fact_leads": "Leads individuais com status do pipeline",
            "fact_conversions": "Vendas com caminho de atribuição multi-touch",
            "fact_crm_pipeline": "Funil CRM (MQL → SQL → Opp → Won)",
            "dim_customer": "Clientes com LTV real e predito",
            "fact_channel_overlap": "Matriz de sobreposição entre canais",
        },
        "conceitos_marketing": {
            "atribuicao": [
                "first_click: 100% do crédito ao primeiro canal",
                "last_click: 100% do crédito ao último canal",
                "linear: crédito igual entre todos os canais do path",
                "time_decay: mais crédito aos canais mais próximos da conversão",
                "data_driven: distribuição simulada baseada em dados históricos",
            ],
            "pipeline": "MQL → SQL → Oportunidade → Won (fechada)",
            "ltv_cac_ratio": ">3x saudável, 1-3x aceitável, <1x crítico",
            "channel_overlap": "coocorrência entre canais em paths de conversão",
        },
        "total_registros": {
            "dim_channel": len(CHANNELS),
            "dim_campaign": len(CAMPANHAS_MOCK),
            "fact_daily_spend": len(DAILY_SPEND),
            "fact_leads": len(LEADS),
            "fact_conversions": len(CONVERSIONS),
            "dim_customer": len(CUSTOMERS),
            "fact_channel_overlap": len(OVERLAP),
        },
    }


# ─────  CHANNELS  ─────

@app.get("/v2/dw/channels", tags=["Channels"])
def list_channels():
    return [ChannelOut(**ch) for ch in CHANNELS]

@app.get("/v2/dw/channels/{channel_id}", tags=["Channels"])
def get_channel_detail(channel_id: int):
    ch = get_channel(channel_id)
    return ChannelOut(**ch)


# ─────  CAMPAIGNS  ─────

@app.get("/v2/dw/campaigns", tags=["Campaigns"])
def list_campaigns(canal: Optional[int] = None, objetivo: Optional[str] = None):
    res = []
    for c in CAMPANHAS_MOCK:
        if canal and c["canal_id"] != canal:
            continue
        if objetivo and c["objetivo"] != objetivo:
            continue
        ch = get_channel(c["canal_id"])
        res.append(CampaignOut(
            id=c["id"], nome=c["nome"], canal=ch["nome"],
            objetivo=c["objetivo"], budget_total=c["budget_total"],
            inicio=c["inicio"], fim=c["fim"],
        ))
    return res

@app.get("/v2/dw/campaigns/{campaign_id}", tags=["Campaigns"])
def get_campaign_detail(campaign_id: int):
    c = get_campaign(campaign_id)
    ch = get_channel(c["canal_id"])
    return CampaignOut(
        id=c["id"], nome=c["nome"], canal=ch["nome"],
        objetivo=c["objetivo"], budget_total=c["budget_total"],
        inicio=c["inicio"], fim=c["fim"],
    )


# ─────  DAILY SPEND  ─────

@app.get("/v2/dw/campaigns/{campaign_id}/daily-spend", tags=["Spend"])
def campaign_daily_spend(
    campaign_id: int,
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    get_campaign(campaign_id)
    items = [s for s in DAILY_SPEND if s["campaign_id"] == campaign_id]
    if start:
        items = [s for s in items if s["data"] >= start]
    if end:
        items = [s for s in items if s["data"] <= end]
    return [
        DailySpendOut(data=s["data"], spend=s["spend"],
                      impressions=s["impressions"], clicks=s["clicks"])
        for s in sorted(items, key=lambda x: x["data"])
    ]


# ─────  LEADS  ─────

@app.get("/v2/dw/leads", tags=["Leads"])
def list_leads(
    campaign_id: Optional[int] = None,
    canal: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = Query(50, le=500),
):
    items = LEADS
    if campaign_id:
        items = [l for l in items if l["campaign_id"] == campaign_id]
    if canal:
        items = [l for l in items if l["canal_id"] == canal]
    if status:
        items = [l for l in items if l["status"] == status]
    out = []
    for l in items[:limit]:
        ch = get_channel(l["canal_id"])
        out.append(LeadOut(
            lead_id=l["lead_id"], data=l["data"],
            status=l["status"], custo_lead=l["custo_lead"],
            campaign_id=l["campaign_id"], canal_nome=ch["nome"],
        ))
    return out


# ─────  CONVERSIONS  ─────

@app.get("/v2/dw/conversions", tags=["Conversions"])
def list_conversions(
    campaign_id: Optional[int] = None,
    canal: Optional[int] = None,
    modelo: str = Query("last_click", description="Modelo de atribuição"),
    limit: int = Query(50, le=500),
):
    items = CONVERSIONS
    if campaign_id:
        items = [c for c in items if c["campaign_id"] == campaign_id]
    if canal:
        items = [c for c in items if canal in c["attribution_path"]]

    out = []
    for conv in items[:limit]:
        creditos = apply_attribution(conv["attribution_path"], conv["receita"], modelo)
        out.append(ConversionOut(
            conv_id=conv["conv_id"], data=conv["data"],
            receita=conv["receita"], itens=conv["itens"],
            dias_para_converter=conv["days_to_convert"],
            attribution_path=conv["attribution_path"],
            canais_credito=creditos,
        ))
    return out


# ─────  ATTRIBUTION  ─────

@app.get("/v2/dw/attribution-models", tags=["Attribution"])
def attribution_models():
    return [
        {"modelo": "first_click", "descricao": "100% do crédito ao primeiro canal do path"},
        {"modelo": "last_click",  "descricao": "100% do crédito ao último canal do path"},
        {"modelo": "linear",      "descricao": "Crédito igual distribuído entre todos os canais"},
        {"modelo": "time_decay",  "descricao": "Peso exponencial: mais crédito aos canais próximos à conversão"},
        {"modelo": "data_driven", "descricao": "Distribuição algorítmica baseada em dados históricos (simulado)"},
    ]

@app.post("/v2/dw/attribution/simular", tags=["Attribution"])
def simulate_attribution(req: AttributeSimulationRequest):
    """Simula como a receita de uma campanha seria distribuída entre canais
    com diferentes modelos de atribuição."""
    convs = [c for c in CONVERSIONS if c["campaign_id"] == req.campaign_id][:50]
    camp = get_campaign(req.campaign_id)
    # Aggregate credits by channel
    total_credits = {}
    for conv in convs:
        creditos = apply_attribution(conv["attribution_path"], conv["receita"], req.modelo)
        for ch, val in creditos.items():
            total_credits[ch] = round(total_credits.get(ch, 0) + val, 2)
    # Map channel IDs to names
    distribuicao = {}
    for ch_id, valor in sorted(total_credits.items(), key=lambda x: -x[1]):
        ch = get_channel(ch_id)
        distribuicao[ch["nome"]] = valor

    return AttributeSimulationResponse(
        campanha=camp["nome"],
        modelo=req.modelo,
        distribuicao=distribuicao,
    )


# ─────  PIPELINE  ─────

@app.get("/v2/dw/pipeline", tags=["Pipeline"])
def pipeline_overview(
    campaign_id: Optional[int] = None,
    canal: Optional[int] = None,
):
    items = PIPELINE
    if campaign_id:
        items = [p for p in items if p["campaign_id"] == campaign_id]
    if canal:
        items = [p for p in items if p["canal_id"] == canal]

    stages = {}
    for p in items:
        s = p["estagio"]
        if s not in stages:
            stages[s] = {"quantidade": 0, "valor_total": 0.0}
        stages[s]["quantidade"] += 1
        stages[s]["valor_total"] += p["valor"]

    order = ["mql", "sql", "oportunidade", "won"]
    return [
        PipelineStage(estagio=s, quantidade=stages[s]["quantidade"],
                       valor_total=round(stages[s]["valor_total"], 2))
        for s in order if s in stages
    ]


# ─────  CUSTOMERS / LTV  ─────

@app.get("/v2/dw/customers", tags=["Customers"])
def list_customers(
    canal: Optional[int] = None,
    churn_risk: Optional[str] = None,
    limit: int = Query(50, le=500),
):
    items = CUSTOMERS
    if canal:
        items = [c for c in items if c["canal_aquisicao"] == canal]
    if churn_risk:
        items = [c for c in items if c["churn_risk"] == churn_risk]
    return [
        CustomerOut(
            customer_id=c["customer_id"],
            canal_aquisicao=c["canal_aquisicao"],
            ltv_12m=c["ltv_12m"],
            ltv_total=c["ltv_total"],
            total_compras=c["total_compras"],
            churn_risk=c["churn_risk"],
        )
        for c in items[:limit]
    ]


# ─────  CAC ANALYSIS  ─────

@app.get("/v2/dw/cac-analysis", tags=["Analytics"])
def cac_analysis():
    """CAC blendado e por canal."""
    result = []
    for ch in CHANNELS:
        campanhas_do_canal = [c for c in CAMPANHAS_MOCK if c["canal_id"] == ch["id"]]
        camp_ids = [c["id"] for c in campanhas_do_canal]
        invest = sum(
            s["spend"] for s in DAILY_SPEND
            if s["canal_id"] == ch["id"]
        )
        leads = len([l for l in LEADS if l["canal_id"] == ch["id"]])
        vendas = len([c for c in CONVERSIONS if c["canal_primary"] == ch["id"]])
        cac = round(invest / vendas, 2) if vendas else None
        result.append(CacAnalysisItem(
            canal=ch["nome"],
            investimento=round(invest, 2),
            leads=leads,
            vendas=vendas,
            cac=cac or 0,
        ))
    blended_invest = sum(r.investimento for r in result)
    blended_vendas = sum(r.vendas for r in result)
    blended_cac = round(blended_invest / blended_vendas, 2) if blended_vendas else 0
    return {
        "por_canal": result,
        "blended": {
            "investimento_total": round(blended_invest, 2),
            "vendas_total": blended_vendas,
            "cac_blendado": blended_cac,
        },
    }


# ─────  LTV:CAC RATIO  ─────

@app.get("/v2/dw/ltv-cac-ratio", tags=["Analytics"])
def ltv_cac_ratio():
    """LTV:CAC ratio por canal. >3x saudável."""
    cac_data = cac_analysis()
    ratios = []
    for item in cac_data["por_canal"]:
        ch = [c for c in CHANNELS if c["nome"] == item.canal][0]
        customers_ch = [c for c in CUSTOMERS if c["canal_aquisicao"] == ch["id"]]
        avg_ltv = (
            round(sum(c["ltv_12m"] for c in customers_ch) / len(customers_ch), 2)
            if customers_ch else 0
        )
        cac_val = item.cac if item.cac > 0 else 1
        ratio = round(avg_ltv / cac_val, 2) if cac_val else 0
        saude = "saudável" if ratio >= 3 else ("aceitável" if ratio >= 1 else "crítico")
        ratios.append(LtvCacRatio(
            canal=item.canal,
            cac=item.cac,
            ltv_medio_12m=avg_ltv,
            ratio=ratio,
            saude=saude,
        ))
    return ratios


# ─────  CHANNEL OVERLAP  ─────

@app.get("/v2/dw/overlap", tags=["Analytics"])
def channel_overlap():
    result = []
    for o in OVERLAP:
        result.append(OverlapOut(
            canal_a=o["nome_a"],
            canal_b=o["nome_b"],
            coocorrencia_pct=o["coocorrencia_pct"],
            lift=o["lift"],
        ))
    return result


# ─────  ROI WATERFALL  ─────

@app.get("/v2/dw/roi-waterfall", tags=["Analytics"])
def roi_waterfall(campaign_id: Optional[int] = None):
    """Demonstra o ROI Waterfall: de media_spend → lucro líquido."""
    if campaign_id:
        spend_items = [s for s in DAILY_SPEND if s["campaign_id"] == campaign_id]
        convs = [c for c in CONVERSIONS if c["campaign_id"] == campaign_id]
        camp = get_campaign(campaign_id)
        ch = get_channel(camp["canal_id"])
        label = f"{camp['nome']} ({ch['nome']})"
    else:
        spend_items = DAILY_SPEND
        convs = CONVERSIONS
        label = "Todos os canais (consolidado)"

    total_spend = round(sum(s["spend"] for s in spend_items), 2)
    total_revenue = round(sum(c["receita"] for c in convs), 2)
    gross_profit = round(total_revenue - total_spend, 2)
    # Assume 15% operational costs
    op_cost = round(total_spend * 0.15, 2)
    net_profit = round(gross_profit - op_cost, 2)
    net_roi = round((net_profit / (total_spend + op_cost)) * 100, 2) if (total_spend + op_cost) else 0

    return {
        "campanha": label,
        "waterfall": [
            RoiWaterfall(etapa="1. Media Spend Total", valor=total_spend),
            RoiWaterfall(etapa="2. Receita Atribuída", valor=total_revenue),
            RoiWaterfall(etapa="3. Lucro Bruto (Receita - Media)", valor=gross_profit),
            RoiWaterfall(etapa="4. Custos Operacionais (15%)", valor=-op_cost),
            RoiWaterfall(etapa="5. Lucro Líquido", valor=net_profit),
        ],
        "roi_liquido_pct": net_roi,
    }


# ─────  COMPLETE CAMPAIGN PERFORMANCE ─────

@app.get("/v2/dw/campaigns/{campaign_id}/performance", tags=["Campaigns"])
def campaign_performance(campaign_id: int):
    """Visão completa de performance de uma campanha."""
    camp = get_campaign(campaign_id)
    ch = get_channel(camp["canal_id"])

    spend_items = [s for s in DAILY_SPEND if s["campaign_id"] == campaign_id]
    convs = [c for c in CONVERSIONS if c["campaign_id"] == campaign_id]
    leads_camp = [l for l in LEADS if l["campaign_id"] == campaign_id]

    total_spend = round(sum(s["spend"] for s in spend_items), 2)
    total_impressions = sum(s["impressions"] for s in spend_items)
    total_clicks = sum(s["clicks"] for s in spend_items)
    total_leads = len(leads_camp)
    total_vendas = len(convs)
    total_receita = round(sum(c["receita"] for c in convs), 2)

    ctr = round(total_clicks / total_impressions * 100, 2) if total_impressions else 0
    cvr = round(total_vendas / total_clicks * 100, 2) if total_clicks else 0
    cpl = round(total_spend / total_leads, 2) if total_leads else 0
    cac = round(total_spend / total_vendas, 2) if total_vendas else 0
    roas = round(total_receita / total_spend, 2) if total_spend else 0
    roi = round(((total_receita - total_spend) / total_spend) * 100, 2) if total_spend else 0

    # Pipeline stages
    pipeline_items = [p for p in PIPELINE if p["campaign_id"] == campaign_id]
    pipeline_stages = {}
    for p in pipeline_items:
        s = p["estagio"]
        if s not in pipeline_stages:
            pipeline_stages[s] = {"qtd": 0, "valor": 0.0}
        pipeline_stages[s]["qtd"] += 1
        pipeline_stages[s]["valor"] += p["valor"]

    mql = pipeline_stages.get("mql", {}).get("qtd", 0)
    sql = pipeline_stages.get("sql", {}).get("qtd", 0)
    opp = pipeline_stages.get("oportunidade", {}).get("qtd", 0)
    won = pipeline_stages.get("won", {}).get("qtd", 0)

    return {
        "campanha": {"id": camp["id"], "nome": camp["nome"], "canal": ch["nome"],
                      "objetivo": camp["objetivo"]},
        "midia": {
            "spend_total": total_spend,
            "impressions": total_impressions,
            "clicks": total_clicks,
            "ctr_pct": ctr,
        },
        "resultados": {
            "leads": total_leads,
            "vendas": total_vendas,
            "receita": total_receita,
            "ticket_medio": round(total_receita / total_vendas, 2) if total_vendas else 0,
        },
        "eficiencia": {
            "cpl": cpl,
            "cac": cac,
            "cvr_pct": cvr,
        },
        "roi": {
            "roas": roas,
            "roi_simples_pct": roi,
        },
        "pipeline": {
            "mql": mql,
            "sql": sql,
            "oportunidade": opp,
            "won": won,
            "conversao_mql_to_won_pct": round(won / mql * 100, 2) if mql else 0,
        },
        "atribuicao_tipica": f"{ch['nome']} usa modelo {ch['modelo_atribuicao']}",
    }


# ─────  RAW QUERY (para o agente consultar)  ─────

class QueryRequest(BaseModel):
    sql: str = Field(..., description="Query SQL simulada (não executada de verdade)")
    params: Optional[dict] = None

@app.post("/v2/dw/query", tags=["Meta"])
def dw_query(req: QueryRequest):
    """Endpoint para o agente LangChain consultar o DW.

    No mock, retorna uma sugestão de como interpretar a query.
    Num DW real, executaria no BigQuery / Snowflake.
    """
    sql_lower = req.sql.lower().strip()
    tables_available = [
        "dim_channel", "dim_campaign", "fact_daily_spend",
        "fact_leads", "fact_conversions", "fact_crm_pipeline",
        "dim_customer", "fact_channel_overlap",
    ]
    mentioned = [t for t in tables_available if t in sql_lower]

    return {
        "status": "query_received",
        "sql_recebida": req.sql,
        "tabelas_identificadas": mentioned,
        "nota": "Ambiente mock. Em produção, executaria no BigQuery.",
        "sugestao": f"Use os endpoints REST /v2/dw/... para obter dados estruturados. "
                    f"Tabelas disponíveis: {', '.join(tables_available)}",
    }
