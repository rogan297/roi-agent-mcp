"""
ROI Agent – LangGraph + MCP
============================
Agente de IA que consulta o Marketing Data Warehouse via MCP Server
e responde perguntas em português sobre ROI, CAC, LTV, pipeline e atribuição.

Arquitetura LangGraph (inspirada em opencode_agent_langgraph.py):
  - StateGraph com MessagesState
  - Nó "agent" (LLM) e nó "tools" (ToolNode)
  - Loop: agent → tools → agent → ... → resposta final
  - Tools obtidas dinamicamente via MCP Client

Uso:
  export OPENAI_API_KEY="sua-chave"
  uv run agent.py                        # modo interativo
  uv run agent.py --demo                 # perguntas pré-definidas

Requer o MCP server rodando:
  uv run mcp_server.py                    # http://localhost:9000/mcp
  uvicorn mock_dw_marketing:app --port 8000  # http://localhost:8000 (DW)
"""

import argparse
import asyncio
import os
import sys
from typing import Literal, Optional

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, MessagesState, END, START
from langgraph.prebuilt import ToolNode

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:9000/mcp")

SYSTEM_PROMPT = """Você é um analista de marketing digital especializado em ROI, CAC, LTV e atribuição.

Você tem acesso a um Data Warehouse de Marketing via MCP com dados reais de campanhas.
Sempre responda em português claro e direto, como se estivesse explicando para um gestor.

REGRAS:
1. Use as ferramentas disponíveis para obter dados reais — nunca invente números.
2. Quando perguntarem sobre "qual canal é melhor", analise múltiplas métricas:
   ROI, CAC, LTV:CAC ratio, pipeline e overlap.
3. Faça conexões entre os dados: um canal pode ter ROI alto mas CAC alto também.
4. Se o usuário não especificar uma campanha, pergunte ou sugira as disponíveis.
5. Para análises comparativas, chame a ferramenta de performance para cada campanha relevante.
6. Apresente os números de forma clara e conclusões acionáveis."""

PERGUNTAS_DEMO = [
    "Quais campanhas estão ativas? Me dê um resumo.",
    "Qual a performance da campanha 1?",
    "Qual canal tem o menor CAC?",
    "Qual a saúde do LTV:CAC por canal?",
    "Simule a atribuição time_decay para a campanha 1. Quais canais levam mais crédito?",
    "Compare a campanha 1 (Google Ads) com a campanha 2 (Meta Ads). Qual é melhor?",
    "Qual é o ROI líquido consolidado de todos os canais?",
    "Quais canais mais se sobrepõem?",
]

# ── LÓGICA DO GRAFO (mesmo padrão do opencode_agent_langgraph.py) ──

def should_continue(state: MessagesState) -> Literal["tools", "__end__"]:
    """Decide se chama mais tools ou devolve a resposta final."""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "__end__"


def create_agent_roi(llm, tools: list[BaseTool]):
    """Cria um grafo LangGraph para o agente ROI com tools do MCP."""
    tool_node = ToolNode(tools)
    model_with_tools = llm.bind_tools(tools)

    def call_model(state: MessagesState):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        return {"messages": [model_with_tools.invoke(messages)]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "__end__": END})
    graph.add_edge("tools", "agent")

    return graph.compile()


# ── LLM FACTORY ──

def criar_mock_llm():
    """Mock LLM para testes sem API key."""
    def mock_invoke(messages):
        content = ""
        for m in messages:
            if isinstance(m, HumanMessage):
                content = m.content
                break
        cl = content.lower() if isinstance(content, str) else ""

        if any(w in cl for w in ["atribuição", "atribuicao", "credito", "distribuic"]):
            tool = ("simular_atribuicao", {"campaign_id": 1, "modelo": "time_decay"})
        elif any(w in cl for w in ["waterfall", "lucro líquido", "liquido", "roi líquido"]):
            tool = ("roi_waterfall", {})
        elif any(w in cl for w in ["sobreposição", "overlap", "sobrepoem"]):
            tool = ("channel_overlap", {})
        elif any(w in cl for w in ["ltv", "saúde", "ratio", "saudavel"]):
            tool = ("ltv_cac_ratio", {})
        elif any(w in cl for w in ["pipeline", "funil", "mql", "sql"]):
            tool = ("pipeline_overview", {})
        elif any(w in cl for w in ["performance", "desempenho", "métrica"]):
            tool = ("campaign_performance", {"campaign_id": 1})
        elif any(w in cl for w in ["cac", "custo de aquisição", "custo aquisicao"]):
            tool = ("cac_analysis", {})
        elif any(w in cl for w in ["compar", "google", "meta", "melhor", "vs"]):
            tool = ("campaign_performance", {"campaign_id": 1})
        elif any(w in cl for w in ["listar", "campanha", "quais", "ativas", "resumo"]):
            tool = ("list_campaigns", {})
        else:
            tool = ("list_campaigns", {})

        name, args = tool
        return AIMessage(
            content=f"Consultando {name}...",
            tool_calls=[{"name": name, "args": args, "id": "call_mock", "type": "tool_call"}],
        )

    from langchain_core.runnables import RunnableLambda
    return RunnableLambda(mock_invoke)


def criar_llm_real():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return ChatOpenAI(model="gpt-4", temperature=0.1)


# ── EXECUÇÃO ──

def _extract_text(content) -> str:
    """Extrai texto limpo do content de uma mensagem."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content)


async def run_agent(llm, tools, user_input: str):
    """Processa uma pergunta e retorna a resposta final."""
    agent = create_agent_roi(llm, tools)
    output = []
    async for chunk in agent.astream({"messages": [HumanMessage(content=user_input)]}):
        for node, msg in chunk.items():
            if isinstance(msg, dict) and "messages" in msg:
                m = msg["messages"][-1]
                if hasattr(m, "tool_calls") and m.tool_calls:
                    for tc in m.tool_calls:
                        line = f"  🛠  {tc['name']}({tc['args']})"
                        print(line)
                        output.append(line)
                elif isinstance(m, AIMessage) and m.content:
                    text = _extract_text(m.content)
                    if text.strip():
                        print(f"  {text}")
                        output.append(text)
    return "\n".join(output)


async def modo_interativo(llm, tools):
    print("=" * 60)
    print("  ROI Agent — LangGraph + MCP")
    print("  Digite 'sair' para encerrar")
    print("  Digite 'demo' para perguntas automáticas")
    print("=" * 60)
    while True:
        pergunta = input("\n💬 ").strip()
        if pergunta.lower() in ("sair", "exit", "quit"):
            break
        if pergunta.lower() == "demo":
            await modo_demo(llm, tools)
            continue
        if not pergunta:
            continue
        try:
            await run_agent(llm, tools, pergunta)
        except Exception as e:
            print(f"\n  ⚠️  Erro: {e}")


async def modo_demo(llm, tools):
    print("=" * 70)
    print("  ROI AGENT - DEMO AUTOMÁTICA")
    print("=" * 70)
    for pergunta in PERGUNTAS_DEMO:
        print(f"\n▶ {pergunta}")
        print()
        try:
            await run_agent(llm, tools, pergunta)
        except Exception as e:
            print(f"  ⚠️  Erro: {e}")
        print("\n" + "-" * 70)


async def main():
    parser = argparse.ArgumentParser(description="ROI Agent - LangGraph + MCP")
    parser.add_argument("--demo", action="store_true", help="Demo automática")
    parser.add_argument("--mock", action="store_true", help="Usar mock LLM")
    args = parser.parse_args()

    if args.mock:
        print("🧪 Modo mock (sem API key)\n")
        llm = criar_mock_llm()
    else:
        llm = criar_llm_real()
        if llm is None:
            print("⚠️  OPENAI_API_KEY não encontrada.")
            print("   Exporte a chave ou use --mock para modo de demonstração.\n")
            print("   export OPENAI_API_KEY='sua-chave-aqui'")
            print("   uv run agent.py\n")
            sys.exit(1)

    client = MultiServerMCPClient(
        {"marketing-dw": {"transport": "http", "url": MCP_SERVER_URL}}
    )
    tools = await client.get_tools()

    if args.demo:
        await modo_demo(llm, tools)
    else:
        await modo_interativo(llm, tools)


if __name__ == "__main__":
    asyncio.run(main())
