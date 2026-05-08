"""
Agent Spawner — lets Marcus create persistent specialist sub-agents.
Each agent is a focused LLM chain with its own system prompt and identity,
stored in data/agents.json and invokable by name.
"""
import os
import json
import logging
from pathlib import Path
from datetime import datetime
from utils.file_lock import read_json_atomic, write_json_atomic

from langchain_core.messages import HumanMessage, SystemMessage

_BASE = Path(__file__).resolve().parent.parent.parent
AGENTS_FILE = _BASE / "data" / "agents.json"
AGENTS_PENDING_FILE = _BASE / "data" / "agents_pending.json"

logger = logging.getLogger(__name__)


class AgentSpawner:
    """
    Creates and manages specialist sub-agents that Marcus can delegate to.
    Agents persist and can be invoked across sessions.
    """

    def __init__(self):
        AGENTS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        data = read_json_atomic(str(AGENTS_FILE))
        return data or {}

    def _save(self, agents: dict) -> None:
        write_json_atomic(str(AGENTS_FILE), agents)

    # ------------------------------------------------------------------
    # Spawn
    # ------------------------------------------------------------------

    async def spawn_agent(
        self,
        name: str,
        purpose: str,
        coaching_context: str,
        use_cases: list,
    ) -> dict:
        """
        Use an LLM to write the agent's system prompt, then persist the agent.
        Returns the stored agent dict.
        """
        from core.prompts import AGENT_SPAWN_PROMPT
        from graph.utils.llm import make_llm
        from core.config import DEFAULT_MODEL_KEY

        from core.config import DEFAULT_TEMPERATURE
        llm = make_llm(DEFAULT_MODEL_KEY, temperature=DEFAULT_TEMPERATURE)

        spawn_prompt = AGENT_SPAWN_PROMPT.format(
            name=name,
            purpose=purpose,
            coaching_context=coaching_context,
            use_cases=", ".join(use_cases),
        )

        response = await llm.ainvoke(spawn_prompt)
        system_prompt = response.content.strip()

        # Persist as a pending agent for human approval
        pending = self._load_pending()
        agent_id = name.lower().replace(" ", "_").replace("-", "_")

        agent = {
            "id": agent_id,
            "name": name,
            "purpose": purpose,
            "coaching_context": coaching_context,
            "use_cases": use_cases,
            "system_prompt": system_prompt,
            "created_at": datetime.now().isoformat(),
            "invocation_count": 0,
            "status": "pending",
        }
        pending[agent_id] = agent
        self._save_pending(pending)

        logger.info(f"AgentSpawner: spawned pending agent '{name}' (id={agent_id})")
        return agent

    # ------------------------------------------------------------------
    # Pending helpers
    # ------------------------------------------------------------------
    def _load_pending(self) -> dict:
        data = read_json_atomic(str(AGENTS_PENDING_FILE))
        return data or {}

    def _save_pending(self, pending: dict) -> None:
        write_json_atomic(str(AGENTS_PENDING_FILE), pending)

    def list_pending_agents(self) -> list:
        return list(self._load_pending().values())

    def approve_agent(self, agent_id: str) -> dict:
        pending = self._load_pending()
        if agent_id not in pending:
            raise KeyError(f"Pending agent '{agent_id}' not found")

        agent = pending.pop(agent_id)
        # Move to main agents file
        agents = self._load()
        agent.pop("status", None)
        agents[agent_id] = agent
        self._save(agents)
        self._save_pending(pending)
        logger.info(f"AgentSpawner: approved agent '{agent_id}'")
        return agent

    # ------------------------------------------------------------------
    # Invoke
    # ------------------------------------------------------------------

    async def invoke_agent(
        self,
        agent_id: str,
        user_input: str,
        context: str = "",
    ) -> str:
        """Run a specialist agent on a given input, with optional session context."""
        agents = self._load()
        if agent_id not in agents:
            return f"Agent '{agent_id}' not found."

        agent = agents[agent_id]

        from graph.utils.llm import make_llm
        from core.config import DEFAULT_MODEL_KEY, DEFAULT_TEMPERATURE
        llm = make_llm(DEFAULT_MODEL_KEY, temperature=DEFAULT_TEMPERATURE)

        system = agent["system_prompt"]
        if context:
            system += (
                "\n\n## Context from Marcus's current session\n"
                f"{context}\n"
                "Use this context to make your response more relevant and personalized."
            )

        messages = [
            SystemMessage(content=system),
            HumanMessage(content=user_input),
        ]

        response = await llm.ainvoke(messages)

        # Track invocation count
        agents[agent_id]["invocation_count"] += 1
        self._save(agents)

        return response.content

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_agents(self) -> list:
        return list(self._load().values())

    def get_agent_summary(self) -> str:
        agents = self.list_agents()
        if not agents:
            return "No specialist agents created yet."
        lines = ["Specialist agents Marcus has built:"]
        for a in agents:
            lines.append(f"  • {a['name']} — {a['purpose']}")
        return "\n".join(lines)


def get_agent_spawner() -> AgentSpawner:
    return AgentSpawner()
