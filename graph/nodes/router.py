"""
graph/nodes/router.py — ReAct tool-calling router node for Marcus agent.
"""
from __future__ import annotations
import logging
from typing import Literal

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage

from graph.state import State
from graph.utils.llm import make_llm
from modules.memory.long_term.memory_manager import get_memory_manager
from modules.self_evolution.skill_manager import get_skill_manager
from prompts.registry import get_prompt_registry

logger = logging.getLogger(__name__)

try:
    ROUTER_SYSTEM_PROMPT = get_prompt_registry().render_prompt("router", version="v1")
except Exception:
    ROUTER_SYSTEM_PROMPT = """You are Marcus's ReAct tool-calling router.
Analyze the user's latest messages and conversation state.
You have tools available:
1. `retrieve_memories`: Search user's long-term memory for relevant past context. Call ONLY when relevant to user request.
2. `get_relevant_skills`: Retrieve active coaching skills/frameworks. Call ONLY when user needs specific coaching methodologies.
3. `trigger_evolution`: Trigger self-evolution sandbox (create tool/skill/agent). Call ONLY when user explicitly asks for creation.
4. `route`: Set response workflow ("conversation", "audio", "image"). MUST be called to decide destination workflow.

You MUST call the `route` tool to finalize destination workflow.
"""



async def router_node(state: State, config: RunnableConfig) -> dict:
    """
    ReAct router node that invokes LLM with tools bound.
    Executes tool calls conditionally and updates state with workflow and context.
    """
    user_id = state.get("user_id", "default")
    messages = state.get("messages", [])

    # Read configurable prompt version and model key
    configurable = (config.get("configurable") if config else {}) or {}
    prompt_version = configurable.get("prompt_version", "v1")
    model_key = configurable.get("model_key", None)

    try:
        router_system_prompt = get_prompt_registry().render_prompt("router", version=prompt_version)
    except Exception:
        router_system_prompt = (
            "You are Marcus's ReAct tool-calling router.\n"
            "Analyze the user's latest messages and conversation state.\n"
            "You have tools available:\n"
            "1. `retrieve_memories`: Search user's long-term memory for relevant past context.\n"
            "2. `get_relevant_skills`: Retrieve active coaching skills/frameworks.\n"
            "3. `trigger_evolution`: Trigger self-evolution sandbox (create tool/skill/agent).\n"
            "4. `route`: Set response workflow ('conversation', 'audio', 'image'). MUST be called.\n"
        )

    @tool
    async def retrieve_memories(query: str) -> str:
        """Search user's long-term vector memory for relevant context.
        Call this when the user references past events, patterns, facts, or goals.
        """
        memory_mgr = get_memory_manager()
        memories = await memory_mgr.get_relevant_memories(query, user_id=user_id, k=5)
        return memory_mgr.format_memories_for_prompt(memories)

    @tool
    def get_relevant_skills(topic: str) -> str:
        """Get coaching frameworks relevant to the current topic.
        Call this when a specific framework applies.
        """
        skill_mgr = get_skill_manager()
        return skill_mgr.get_active_skills_context()

    @tool
    def trigger_evolution(plan: str) -> str:
        """Trigger self-evolution sandbox.
        Call this ONLY when user explicitly requests creating a tool, skill, or agent.
        """
        return f"Evolution triggered with plan: {plan}"

    @tool
    def route(workflow: str) -> str:
        """Set the destination workflow.
        MUST be called. Allowed values: 'conversation', 'audio', 'image'.
        """
        clean_wf = str(workflow).lower().replace("_node", "").strip()
        if clean_wf not in ("conversation", "audio", "image", "self_evolve"):
            return "conversation"
        return clean_wf

    tools = [retrieve_memories, get_relevant_skills, trigger_evolution, route]

    from core.config import ROUTER_MODEL_KEY
    target_model_key = model_key or ROUTER_MODEL_KEY
    llm = make_llm(target_model_key, temperature=0.0)

    model_with_tools = llm.bind_tools(tools).with_retry(
        stop_after_attempt=3,
        wait_exponential_jitter=True,
    )
    input_messages = [SystemMessage(content=router_system_prompt)] + messages[-6:]

    try:
        response = await model_with_tools.ainvoke(input_messages, config=config)
    except Exception as exc:
        logger.warning(f"Router LLM tool-binding failed, falling back to default route: {exc}")
        return {"workflow": "conversation"}

    memory_context = state.get("memory_context", "")
    active_skills_context = state.get("active_skills_context", "")
    workflow = "conversation"
    evolution_pending = False
    route_called = False

    tool_calls = getattr(response, "tool_calls", None) or []

    for tool_call in tool_calls:
        if isinstance(tool_call, dict):
            tool_name = tool_call.get("name")
            args = tool_call.get("args", {})
        else:
            tool_name = getattr(tool_call, "name", None)
            args = getattr(tool_call, "args", {})

        if isinstance(args, str):
            import json
            try:
                args = json.loads(args)
            except Exception:
                args = {}

        if tool_name == "retrieve_memories":
            query = args.get("query") or args.get("search_query") or args.get("text") or ""
            if not query and messages:
                query = str(messages[-1].content)
            if query:
                mem_mgr = get_memory_manager()
                mems = await mem_mgr.get_relevant_memories(query, user_id=user_id, k=5)
                memory_context = mem_mgr.format_memories_for_prompt(mems)

        elif tool_name == "get_relevant_skills":
            skill_mgr = get_skill_manager()
            active_skills_context = skill_mgr.get_active_skills_context()

        elif tool_name == "trigger_evolution":
            evolution_pending = True
            workflow = "self_evolve"

        elif tool_name == "route":
            route_called = True
            raw_wf = args.get("workflow") or args.get("destination") or "conversation"
            clean_wf = str(raw_wf).lower().replace("_node", "").strip()
            if clean_wf in ("conversation", "audio", "image", "self_evolve"):
                workflow = clean_wf

    # Fallback workflow inferencing if route tool was not called explicitly
    if not route_called and not evolution_pending and messages:
        last_msg = str(messages[-1].content).lower()
        if any(w in last_msg for w in ["voice note", "audio message", "speak to me", "say this out loud"]):
            workflow = "audio"
        elif any(w in last_msg for w in ["generate an image", "picture of", "draw a", "visualize"]):
            workflow = "image"
        elif any(w in last_msg for w in ["create tool", "build tool", "acquire skill", "spawn agent"]):
            workflow = "self_evolve"
            evolution_pending = True

    return {
        "workflow": workflow,
        "memory_context": memory_context,
        "active_skills_context": active_skills_context,
        "evolution_pending": evolution_pending,
    }

