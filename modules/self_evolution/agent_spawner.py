"""
Agent Spawner — lets Marcus create persistent specialist sub-agents.
Each agent is a focused LLM chain with its own system prompt and identity,
stored in PostgreSQL (agents_registry) with row-level locking.
"""
import threading
import logging
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage

from core.db import init_db, get_db_session, AgentModel

logger = logging.getLogger(__name__)


class AgentSpawner:
    """
    Creates and manages specialist sub-agents that Marcus can delegate to.
    Agents persist in PostgreSQL (agents_registry) with row-level locking.
    Thread-safe singleton.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        init_db()
        self._initialized = True

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
        Use an LLM to write the agent's system prompt, then persist the pending agent to PostgreSQL.
        Returns the stored agent dict.
        """
        from core.prompts import AGENT_SPAWN_PROMPT
        from graph.utils.llm import make_llm
        from core.config import DEFAULT_MODEL_KEY, DEFAULT_TEMPERATURE

        llm = make_llm(DEFAULT_MODEL_KEY, temperature=DEFAULT_TEMPERATURE)

        spawn_prompt = AGENT_SPAWN_PROMPT.format(
            name=name,
            purpose=purpose,
            coaching_context=coaching_context,
            use_cases=", ".join(use_cases),
        )

        response = await llm.ainvoke(spawn_prompt)
        system_prompt = response.content.strip()

        agent_id = name.lower().replace(" ", "_").replace("-", "_")
        now_str = datetime.now().isoformat()

        with get_db_session() as session:
            existing = session.query(AgentModel).filter(AgentModel.id == agent_id).with_for_update().first()
            if existing:
                existing.name = name
                existing.purpose = purpose
                existing.coaching_context = coaching_context
                existing.use_cases = use_cases
                existing.system_prompt = system_prompt
                existing.status = "pending"
                agent_obj = existing
            else:
                agent_obj = AgentModel(
                    id=agent_id,
                    name=name,
                    purpose=purpose,
                    coaching_context=coaching_context,
                    use_cases=use_cases,
                    system_prompt=system_prompt,
                    created_at=now_str,
                    invocation_count=0,
                    status="pending",
                )
                session.add(agent_obj)
            session.flush()
            result = agent_obj.to_dict()

        logger.info(f"AgentSpawner: spawned pending agent '{name}' (id={agent_id})")
        return result

    # ------------------------------------------------------------------
    # Pending & Approval
    # ------------------------------------------------------------------

    def list_pending_agents(self) -> list:
        with get_db_session() as session:
            records = session.query(AgentModel).filter(AgentModel.status == "pending").all()
            return [r.to_dict() for r in records]

    def approve_agent(self, agent_id: str) -> dict:
        with get_db_session() as session:
            agent_obj = (
                session.query(AgentModel)
                .filter(AgentModel.id == agent_id, AgentModel.status == "pending")
                .with_for_update()
                .first()
            )
            if not agent_obj:
                raise KeyError(f"Pending agent '{agent_id}' not found")

            agent_obj.status = "active"
            session.flush()
            result = agent_obj.to_dict()

        logger.info(f"AgentSpawner: approved agent '{agent_id}'")
        return result

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
        with get_db_session() as session:
            agent_obj = (
                session.query(AgentModel)
                .filter(AgentModel.id == agent_id, AgentModel.status == "active")
                .first()
            )
            if not agent_obj:
                return f"Agent '{agent_id}' not found."
            agent = agent_obj.to_dict()

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

        with get_db_session() as session:
            agent_obj = session.query(AgentModel).filter(AgentModel.id == agent_id).with_for_update().first()
            if agent_obj:
                agent_obj.invocation_count = (agent_obj.invocation_count or 0) + 1

        return response.content

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_agents(self) -> list:
        with get_db_session() as session:
            records = session.query(AgentModel).filter(AgentModel.status == "active").all()
            return [r.to_dict() for r in records]

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
