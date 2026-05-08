"""
graph/nodes.py — All LangGraph node functions for Marcus's agent.
Model selection flows through config["configurable"]["model_key"].
FallbackLLM in llm.py handles Groq rate-limit -> Gemini retry transparently.
"""
from __future__ import annotations
import json, logging, os, uuid
from langchain_core.messages import HumanMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from .state import State
from .utils.chains import get_character_response_chain, get_router_chain
from .utils.helper import get_text_to_speech_module, get_text_to_image_module
from .utils.llm import make_llm, get_chat_model_from_config
from modules.memory.long_term.memory_manager import get_memory_manager
from modules.self_evolution.skill_manager import get_skill_manager
from modules.self_evolution.tool_creator import get_tool_creator
from modules.self_evolution.agent_spawner import get_agent_spawner

logger = logging.getLogger(__name__)


def skill_injection_node(state: State) -> dict:
    return {"active_skills_context": get_skill_manager().get_active_skills_context()}


async def self_evolve_check_node(state: State, config: RunnableConfig) -> dict:
    from core.prompts import SELF_EVOLVE_CHECK_PROMPT
    from pydantic import BaseModel, Field

    class EvolveCheck(BaseModel):
        needs_evolution: bool = Field(description="Whether self-evolution is needed")

    from core.config import EVOLVE_CHECK_MODEL_KEY, EVALUATION_TEMPERATURE
    llm = make_llm(EVOLVE_CHECK_MODEL_KEY, temperature=EVALUATION_TEMPERATURE).with_structured_output(EvolveCheck)
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
    from core.prompts import SELF_EVOLVE_DISPATCH_PROMPT

    conv = "\n".join(
        f"{'User' if m.type == 'human' else 'Marcus'}: {m.content}"
        for m in state["messages"][-6:]
    )
    llm = get_chat_model_from_config(config, temperature=0.3)
    try:
        response = await llm.ainvoke(SELF_EVOLVE_DISPATCH_PROMPT.format(conversation=conv))
        raw = response.content.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        plan = json.loads(raw)
    except Exception as e:
        logger.error(f"self_evolve_node dispatch failed: {e}")
        return {"workflow": "conversation", "evolved_context": ""}

    etype = plan.get("evolution_type", "")
    name  = plan.get("name", "Unnamed")
    desc  = plan.get("description", "")
    ctx   = plan.get("coaching_context", "")
    uses  = plan.get("use_cases", [])
    evolved = ""

    try:
        if etype == "create_tool":
            spec = plan.get("tool_spec", {})
            spec.update({"name": name, "description": desc})
            r = await get_tool_creator().create_tool(spec)
            if r.get("status") == "pending":
                evolved = (
                    f"Marcus proposed a new tool: **{r['name']}**\n"
                    f"What it does: {r['description']}\n"
                    f"This tool is pending human approval before it can be used."
                )
            else:
                evolved = (
                    f"Marcus just built a new tool: **{r['name']}**\n"
                    f"What it does: {r['description']}\n"
                    f"It is now permanently in his coaching toolkit."
                )
        elif etype == "acquire_skill":
            sm = get_skill_manager()
            r = sm.acquire_skill(name=name, description=desc,
                                 coaching_context=ctx, use_cases=uses)
            if r.get("status") == "pending":
                evolved = (
                    f"Marcus proposed adding: **{r['name']}**\n"
                    f"{r['description']}\n"
                    f"This framework is pending approval before it becomes part of his practice."
                )
                return {"workflow": "conversation", "evolved_context": evolved}
            else:
                evolved = (
                    f"Marcus just added: **{r['name']}**\n"
                    f"{r['description']}\nHe will draw on this where it fits."
                )
                return {
                    "workflow": "conversation",
                    "evolved_context": evolved,
                    "active_skills_context": sm.get_active_skills_context(),
                }
        elif etype == "spawn_agent":
            r = await get_agent_spawner().spawn_agent(
                name=name, purpose=desc, coaching_context=ctx, use_cases=uses
            )
            if r.get("status") == "pending":
                evolved = (
                    f"Marcus proposed creating agent: **{r['name']}**\n"
                    f"Purpose: {r['purpose']}\n"
                    f"This agent is pending human approval before activation."
                )
            else:
                evolved = (
                    f"Marcus just created agent: **{r['name']}**\n"
                    f"Purpose: {r['purpose']}\nNow available as a dedicated coaching resource."
                )
        else:
            logger.warning(f"Unknown evolution_type: {etype}")
    except Exception as e:
        logger.error(f"self_evolve_node creation failed ({etype}): {e}")

    return {"workflow": "conversation", "evolved_context": evolved}


async def router_node(state: State, config: RunnableConfig):
    chain = get_router_chain(config)
    response = await chain.ainvoke({"messages": state["messages"][-3:]}, config=config)
    return {"workflow": response.response_type}


async def audio_node(state: State, config: RunnableConfig):
    chain = get_character_response_chain(
        summary=state.get("summary", ""),
        active_skills=state.get("active_skills_context", ""),
        config=config,
    )
    tts = get_text_to_speech_module()
    response = await chain.ainvoke(
        {"messages": state["messages"],
         "memory_context": state.get("memory_context", "")},
        config=config,
    )
    return {"messages": response, "audio_buffer": await tts.synthesize(response.content)}


async def image_node(state: State, config: RunnableConfig):
    chain = get_character_response_chain(
        summary=state.get("summary", ""),
        active_skills=state.get("active_skills_context", ""),
        config=config,
    )
    tti = get_text_to_image_module()
    scenario = await tti.create_scenario(state["messages"][-5:])
    enhanced = await tti.enhance_prompt(scenario.image_prompt)
    os.makedirs("public/images", exist_ok=True)
    img_path = f"public/images/image_{uuid.uuid4()}.png"
    await tti.generate_image(enhanced, img_path)
    msgs = state["messages"] + [
        HumanMessage(content=f"<image from prompt: {scenario.image_prompt}>")
    ]
    response = await chain.ainvoke(
        {"messages": msgs, "memory_context": state.get("memory_context", "")},
        config=config,
    )
    return {"messages": response, "image_path": img_path}


async def conversation_node(state: State, config: RunnableConfig):
    chain = get_character_response_chain(
        summary=state.get("summary", ""),
        active_skills=state.get("active_skills_context", ""),
        evolved_context=state.get("evolved_context", ""),
        config=config,
    )
    response = await chain.ainvoke(
        {"messages": state.get("messages", [])}, config=config
    )
    return {"messages": response, "evolved_context": ""}


async def memory_saving_node(state: State):
    if not state["messages"]:
        return {}
    human = [m for m in state["messages"] if m.type == "human"]
    if human:
        await get_memory_manager().extract_and_save_context(human[-1])
    return {}


def memory_retrieval_node(state: State):
    mm = get_memory_manager()
    recent = " ".join(m.content for m in state["messages"][-3:])
    return {"memory_context": mm.format_memories_for_prompt(mm.get_relevant_memories(recent))}


async def summarization_node(state: State, config: RunnableConfig):
    model = get_chat_model_from_config(config, temperature=0.3)
    summary = state.get("summary", "")
    if summary:
        msg = f"Summary so far: {summary}\n\nExtend it with the new messages above."
    else:
        msg = "Create a concise summary of the conversation between Marcus and the User."
    response = await model.ainvoke(state["messages"] + [HumanMessage(content=msg)])
    return {
        "summary": response.content,
        "messages": [RemoveMessage(id=m.id) for m in state["messages"][:-5]],
    }
