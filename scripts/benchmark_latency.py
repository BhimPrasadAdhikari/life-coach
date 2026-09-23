"""
scripts/benchmark_latency.py — Benchmark execution latency, throughput, and system overhead.
"""
import time
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from prompts.registry import get_prompt_registry
from interfaces.whatsapp.app import parse_whatsapp_payload
from interfaces._base import AgentRequest
from modules.self_evolution.skill_manager import get_skill_manager
from graph.graph import get_compiled_app
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableLambda


def benchmark_prompt_registry(iterations=1000):
    registry = get_prompt_registry()
    
    t0 = time.perf_counter()
    for _ in range(iterations):
        registry.render_prompt("system", version="v1", memory_context="User values balance.", summary="Summary test.")
    t1 = time.perf_counter()

    avg_ms = ((t1 - t0) / iterations) * 1000
    ops_per_sec = iterations / (t1 - t0)
    print(f"[PromptRegistry] {iterations} renders completed in {t1-t0:.4f}s | Avg latency: {avg_ms:.4f} ms | Throughput: {ops_per_sec:.2f} op/s")
    return avg_ms


def benchmark_whatsapp_parser(iterations=10000):
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "123",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "messages": [{
                        "from": "15125551234",
                        "id": "wamid.12345",
                        "timestamp": "1670000000",
                        "text": {"body": "Hello Marcus, benchmark message testing latency."},
                        "type": "text"
                    }]
                }
            }]
        }]
    }

    t0 = time.perf_counter()
    for _ in range(iterations):
        parse_whatsapp_payload(payload)
    t1 = time.perf_counter()

    avg_ms = ((t1 - t0) / iterations) * 1000
    ops_per_sec = iterations / (t1 - t0)
    print(f"[WhatsApp Payload Parser] {iterations} parses completed in {t1-t0:.4f}s | Avg latency: {avg_ms:.4f} ms | Throughput: {ops_per_sec:.2f} op/s")
    return avg_ms


def benchmark_skill_manager(iterations=500):
    sm = get_skill_manager()
    
    t0 = time.perf_counter()
    for _ in range(iterations):
        sm.get_active_skills_context()
    t1 = time.perf_counter()

    avg_ms = ((t1 - t0) / iterations) * 1000
    ops_per_sec = iterations / (t1 - t0)
    print(f"[SkillManager Context Cache] {iterations} lookups completed in {t1-t0:.4f}s | Avg latency: {avg_ms:.4f} ms | Throughput: {ops_per_sec:.2f} op/s")
    return avg_ms


async def benchmark_graph_turn(iterations=100):
    with patch("graph.nodes.router.make_llm") as mock_make_router_llm, \
         patch("graph.utils.chains.get_chat_model_from_config") as mock_get_chat_model, \
         patch("graph.nodes.memory.get_memory_manager") as mock_get_mem_mgr:

        mock_router_llm = MagicMock()
        mock_router_resp = MagicMock()
        mock_router_resp.tool_calls = [{"name": "route", "args": {"workflow": "conversation"}, "id": "call_123"}]
        mock_router_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_router_resp)
        mock_make_router_llm.return_value = mock_router_llm

        mock_chat_model = RunnableLambda(lambda x: AIMessage(content="Benchmark response from Marcus."))
        mock_get_chat_model.return_value = mock_chat_model

        mock_mem_mgr = MagicMock()
        mock_mem_mgr.extract_and_save_context = AsyncMock(return_value={"is_important": False, "formatted_memory": ""})
        mock_get_mem_mgr.return_value = mock_mem_mgr

        app = get_compiled_app(checkpointer=None)
        state = {
            "messages": [HumanMessage(content="Hello Marcus!")],
            "user_id": "wa_benchmark",
            "thread_id": "thread_benchmark",
            "channel": "whatsapp"
        }
        config = {"configurable": {"thread_id": "thread_benchmark"}}

        t0 = time.perf_counter()
        for _ in range(iterations):
            await app.ainvoke(state, config=config)
        t1 = time.perf_counter()

        avg_ms = ((t1 - t0) / iterations) * 1000
        ops_per_sec = iterations / (t1 - t0)
        print(f"[LangGraph Execution Overhead] {iterations} turns completed in {t1-t0:.4f}s | Avg graph overhead latency: {avg_ms:.4f} ms | Throughput: {ops_per_sec:.2f} turns/s")
        return avg_ms


def main():
    print("=" * 70)
    print("      MARCUS AI AGENT — PERFORMANCE & LATENCY BENCHMARK TOOL")
    print("=" * 70)
    
    prompt_ms = benchmark_prompt_registry(1000)
    whatsapp_ms = benchmark_whatsapp_parser(10000)
    skill_ms = benchmark_skill_manager(500)
    graph_ms = asyncio.run(benchmark_graph_turn(100))

    print("=" * 70)
    print("SUMMARY OF BENCHMARK LATENCIES:")
    print(f"  • Prompt Registry Render:   {prompt_ms:.4f} ms per call")
    print(f"  • WhatsApp Webhook Parse:   {whatsapp_ms:.4f} ms per payload")
    print(f"  • Skill Cache Lookup:       {skill_ms:.4f} ms per turn")
    print(f"  • LangGraph Framework Overhead: {graph_ms:.4f} ms per turn")
    print("=" * 70)

if __name__ == "__main__":
    main()
