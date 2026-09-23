"""
tests/unit/test_phase2.py — Unit tests for Phase 2 implementation:
- Package importability (marcus_agent package)
- Database schema initialization & connection (core/db.py)
- SkillManager PostgreSQL migration & row-level locking behavior
- AgentSpawner PostgreSQL migration & row-level locking behavior
"""
import os
import unittest
import tempfile
from unittest.mock import MagicMock, AsyncMock, patch

from core.db import init_db, get_db_session, SkillModel, AgentModel
from modules.self_evolution.skill_manager import SkillManager
from modules.self_evolution.agent_spawner import AgentSpawner


class TestPackageImportability(unittest.TestCase):
    def test_marcus_agent_package_import(self):
        import marcus_agent
        self.assertTrue(hasattr(marcus_agent, "__version__"))
        self.assertEqual(marcus_agent.__version__, "0.1.0")


class TestDatabaseRegistries(unittest.TestCase):
    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        self.db_url = f"sqlite:///{self.temp_db_path}"
        init_db(self.db_url)

    def tearDown(self):
        from core.db import dispose_engine
        dispose_engine()
        os.close(self.temp_db_fd)
        try:
            if os.path.exists(self.temp_db_path):
                os.remove(self.temp_db_path)
        except Exception:
            pass

    def test_skills_db_lifecycle(self):
        with get_db_session(self.db_url) as session:
            skill = SkillModel(
                id="cbt_restructuring",
                name="Cognitive Restructuring",
                description="Identify and reframe cognitive distortions.",
                coaching_context="When user exhibits catastrophic thinking.",
                use_cases=["anxiety", "negative self-talk"],
                created_at="2026-09-05T12:00:00",
                use_count=0,
                status="pending",
            )
            session.add(skill)

        # Retrieve and verify pending status
        with get_db_session(self.db_url) as session:
            fetched = session.query(SkillModel).filter(SkillModel.id == "cbt_restructuring").first()
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched.status, "pending")
            self.assertEqual(len(fetched.to_dict()["use_cases"]), 2)

            # Update to active (simulating approval)
            fetched.status = "active"

        # Verify active status
        with get_db_session(self.db_url) as session:
            fetched = session.query(SkillModel).filter(SkillModel.id == "cbt_restructuring").first()
            self.assertEqual(fetched.status, "active")

    def test_agents_db_lifecycle(self):
        with get_db_session(self.db_url) as session:
            agent = AgentModel(
                id="planner_agent",
                name="Goal Planner Specialist",
                purpose="Break down complex goals into actionable sub-tasks.",
                coaching_context="User needs structured goal planning.",
                use_cases=["planning", "roadmap"],
                system_prompt="You are a goal planning expert.",
                created_at="2026-09-05T12:00:00",
                invocation_count=0,
                status="pending",
            )
            session.add(agent)

        with get_db_session(self.db_url) as session:
            fetched = session.query(AgentModel).filter(AgentModel.id == "planner_agent").first()
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched.status, "pending")
            self.assertEqual(fetched.system_prompt, "You are a goal planning expert.")

            fetched.status = "active"

        with get_db_session(self.db_url) as session:
            fetched = session.query(AgentModel).filter(AgentModel.id == "planner_agent").first()
            self.assertEqual(fetched.status, "active")


class TestSkillManagerPostgres(unittest.TestCase):
    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        self.db_url = f"sqlite:///{self.temp_db_path}"
        init_db(self.db_url)
        SkillManager._instance = None
        self.sm = SkillManager()

    def tearDown(self):
        from core.db import dispose_engine
        dispose_engine()
        os.close(self.temp_db_fd)
        try:
            if os.path.exists(self.temp_db_path):
                os.remove(self.temp_db_path)
        except Exception:
            pass


    def test_acquire_and_approve_skill(self):
        skill = self.sm.acquire_skill(
            name="ACT Values Clarification",
            description="Clarify core personal values.",
            coaching_context="When user feels directionless.",
            use_cases=["career transition", "identity"],
        )
        self.assertEqual(skill["status"], "pending")

        pending = self.sm.list_pending_skills()
        self.assertTrue(any(s["id"] == skill["id"] for s in pending))

        approved = self.sm.approve_skill(skill["id"])
        self.assertEqual(approved["status"], "active")

        active_skills = self.sm.list_skills()
        self.assertTrue(any(s["id"] == skill["id"] for s in active_skills))

        # Test increment_use
        self.sm.increment_use(skill["id"])
        updated_active = self.sm.list_skills()
        matching = next(s for s in updated_active if s["id"] == skill["id"])
        self.assertEqual(matching["use_count"], 1)


class TestAgentSpawnerPostgres(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        AgentSpawner._instance = None
        self.spawner = AgentSpawner()

    @patch("graph.utils.llm.make_llm")
    async def test_spawn_and_approve_agent(self, mock_make_llm):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "System prompt for accountability specialist."
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_make_llm.return_value = mock_llm

        agent = await self.spawner.spawn_agent(
            name="Accountability Bot",
            purpose="Track habit completion.",
            coaching_context="User sets daily habits.",
            use_cases=["habits", "streaks"],
        )
        self.assertEqual(agent["status"], "pending")

        pending = self.spawner.list_pending_agents()
        self.assertTrue(any(a["id"] == agent["id"] for a in pending))

        approved = self.spawner.approve_agent(agent["id"])
        self.assertEqual(approved["status"], "active")

        active_agents = self.spawner.list_agents()
        self.assertTrue(any(a["id"] == agent["id"] for a in active_agents))

        # Invoke agent
        response = await self.spawner.invoke_agent(agent["id"], "Did I finish my 5k run?")
        self.assertEqual(response, "System prompt for accountability specialist.")


if __name__ == "__main__":
    unittest.main()
