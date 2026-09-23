"""
graph/nodes/evolution.py — Self-evolution nodes and skill injection.
"""
from __future__ import annotations
import json
import logging
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from graph.state import State
from graph.utils.llm import make_llm, get_chat_model_from_config, with_resilience
from modules.self_evolution.skill_manager import get_skill_manager
from modules.self_evolution.tool_creator import get_tool_creator
from modules.self_evolution.agent_spawner import get_agent_spawner

logger = logging.getLogger(__name__)


def skill_injection_node(state: State) -> dict:
    return {"active_skills_context": get_skill_manager().get_active_skills_context()}


async def self_evolve_check_node(state: State, config: RunnableConfig) -> dict:
    from core.prompts import SELF_EVOLVE_CHECK_PROMPT

    class EvolveCheck(BaseModel):
        needs_evolution: bool = Field(description="Whether self-evolution is needed")

    from core.config import EVOLVE_CHECK_MODEL_KEY, EVALUATION_TEMPERATURE
    llm = make_llm(EVOLVE_CHECK_MODEL_KEY, temperature=EVALUATION_TEMPERATURE)
    llm = with_resilience(
        llm.with_structured_output(EvolveCheck),
        EVOLVE_CHECK_MODEL_KEY,
        temperature=EVALUATION_TEMPERATURE,
    )
    try:
        result = await llm.ainvoke(
            [HumanMessage(content=SELF_EVOLVE_CHECK_PROMPT)] + state["messages"][-3:]
        )
        if result.needs_evolution:
            return {"workflow": "self_evolve"}
    except Exception as e:
        logger.warning(f"self_evolve_check_node failed, skipping: {e}")
    return {}


async def self_evolve_node(state: State, config: RunnableConfig) -> dict:
    """
    Analyze the recent conversation and optionally create a tool,
    acquire a new skill, or spawn a specialized agent.
    """
    from prompts.registry import get_prompt_registry

    messages = state.get("messages", [])
    configurable = (config.get("configurable") if config else {}) or {}
    prompt_version = configurable.get("prompt_version", "v1")

    conversation = "\n".join(
        f"{'User' if m.type == 'human' else 'Marcus'}: {m.content}"
        for m in messages[-6:]
    )

    llm = get_chat_model_from_config(config, temperature=0.3)

    try:
        prompt_text = get_prompt_registry().render_prompt("evolution", version=prompt_version, conversation=conversation)
    except Exception:
        from core.prompts import SELF_EVOLVE_DISPATCH_PROMPT
        prompt_text = SELF_EVOLVE_DISPATCH_PROMPT.format(conversation=conversation)

    try:
        response = await llm.ainvoke(
            prompt_text,
            config=config,
        )

        raw = response.content

        if isinstance(raw, list):
            raw = "".join(
                block.get("text", "")
                if isinstance(block, dict)
                else str(block)
                for block in raw
            )

        raw = str(raw).strip()

        if "```json" in raw:
            raw = raw.split("```json")[1].split("```", 1)[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```", 1)[0].strip()

        plan = json.loads(raw)

    except json.JSONDecodeError as exc:
        logger.error("self_evolve_node returned invalid JSON: %s", exc)
        return {
            "workflow": "conversation",
            "evolved_context": "",
            "pending_action": None,
        }
    except Exception as exc:
        logger.exception("self_evolve_node dispatch failed: %s", exc)
        return {
            "workflow": "conversation",
            "evolved_context": "",
            "pending_action": None,
        }

    evolution_type = plan.get("evolution_type", "")
    name = plan.get("name", "Unnamed")
    description = plan.get("description", "")
    coaching_context = plan.get("coaching_context", "")
    use_cases = plan.get("use_cases", [])

    evolved_context = ""
    pending_action = None

    try:
        if evolution_type == "create_tool":
            tool_spec = plan.get("tool_spec", {})
            if not isinstance(tool_spec, dict):
                tool_spec = {}

            tool_spec.update({"name": name, "description": description})
            result = await get_tool_creator().create_tool(tool_spec)

            if result.get("status") == "pending":
                evolved_context = (
                    f"Marcus proposed a new tool: **{result.get('name', name)}**\n"
                    f"What it does: {result.get('description', description)}\n"
                    "This tool is pending human approval before it can be used."
                )
                pending_action = {
                    "type": "approve_tool",
                    "label": "Approve Tool",
                    "payload": {"tool_id": result.get("id")},
                }
            else:
                evolved_context = (
                    f"Marcus just built a new tool: **{result.get('name', name)}**\n"
                    f"What it does: {result.get('description', description)}\n"
                    "It is now permanently in his toolkit."
                )

        elif evolution_type == "acquire_skill":
            skill_manager = get_skill_manager()
            result = skill_manager.acquire_skill(
                name=name,
                description=description,
                coaching_context=coaching_context,
                use_cases=use_cases,
            )

            if result.get("status") == "pending":
                evolved_context = (
                    f"Marcus proposed adding: **{result.get('name')}**\n"
                    f"{result.get('description')}\n"
                    f"This framework is pending approval before it becomes part of his practice."
                )
                pending_action = {
                    "type": "approve_skill",
                    "label": "Approve Skill",
                    "payload": {"skill_id": result.get("id")},
                }
            else:
                evolved_context = (
                    f"Marcus just added: **{result.get('name', name)}**\n"
                    f"{result.get('description', description)}\n"
                    f"He will draw on this where it fits."
                )
                return {
                    "workflow": "conversation",
                    "evolved_context": evolved_context,
                    "active_skills_context": skill_manager.get_active_skills_context(),
                    "pending_action": None,
                }

        elif evolution_type == "spawn_agent":
            result = await get_agent_spawner().spawn_agent(
                name=name,
                purpose=description,
                coaching_context=coaching_context,
                use_cases=use_cases,
            )

            if result.get("status") == "pending":
                evolved_context = (
                    f"Marcus proposed creating agent: **{result.get('name', name)}**\n"
                    f"Purpose: {result.get('purpose', description)}\n"
                    f"This agent requires your approval before activation."
                )
                pending_action = {
                    "type": "approve_agent",
                    "label": "Approve agent",
                    "payload": {"agent_id": result.get("id")},
                }
            else:
                evolved_context = (
                    f"Marcus just created a sub-agent: **{result.get('name', name)}**\n"
                    f"Purpose: {result.get('purpose', description)}\n"
                    f"It is now available as a specialized resource."
                )
        else:
            logger.warning("Unknown evolution_type: %r", evolution_type)

    except Exception as exc:
        logger.exception("Self-evolution creation failed for %s: %s", evolution_type, exc)
        return {
            "workflow": "conversation",
            "evolved_context": "",
            "pending_action": None,
        }

    return {
        "workflow": "conversation",
        "evolved_context": evolved_context,
        "pending_action": pending_action,
    }
