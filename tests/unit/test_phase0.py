"""
tests/unit/test_phase0.py — Unit tests for Phase 0:
1. State schema cleanliness
2. Qdrant user memory collection namespacing
3. DockerSandbox security fail-hard policy
4. ReAct tool-calling router node execution
"""
import unittest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path

# Ensure root workspace directory is in python path
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graph.state import State
from modules.memory.long_term.vector_store import get_user_collection_name
from modules.evolution.sandbox import DockerSandbox
from langchain_core.messages import HumanMessage


class TestPhase0State(unittest.TestCase):
    def test_state_schema_keys(self):
        """Verify State schema has no duplicated fields and contains required fields."""
        annotations = State.__annotations__
        self.assertIn("user_id", annotations)
        self.assertIn("thread_id", annotations)
        self.assertIn("workflow", annotations)
        self.assertIn("memory_context", annotations)
        self.assertIn("active_skills_context", annotations)
        self.assertIn("evolution_pending", annotations)


class TestUserMemoryIsolation(unittest.TestCase):
    def test_get_user_collection_name_standard(self):
        self.assertEqual(get_user_collection_name("user123"), "marcus_memory_user123")

    def test_get_user_collection_name_whatsapp(self):
        self.assertEqual(get_user_collection_name("wa_+15125550199"), "marcus_memory_wa_15125550199")

    def test_get_user_collection_name_empty(self):
        self.assertEqual(get_user_collection_name(""), "marcus_memory_default")

    def test_get_user_collection_name_sanitization(self):
        self.assertEqual(get_user_collection_name("user@domain.com!#$"), "marcus_memory_userdomaincom")


class TestDockerSandboxSecurity(unittest.TestCase):
    @patch("modules.evolution.sandbox.DockerSandbox.is_docker_available", return_value=False)
    def test_docker_unavailable_fails_hard(self, mock_is_docker):
        """Verify DockerSandbox raises RuntimeError when Docker is unavailable."""
        sandbox = DockerSandbox()
        dummy_path = Path("fake_tool.py")

        with self.assertRaises(RuntimeError) as ctx:
            sandbox.run_tool(dummy_path, "fake_func")

        self.assertIn("CRITICAL SECURITY VIOLATION", str(ctx.exception))
        self.assertIn("Subprocess fallback is disabled", str(ctx.exception))


class TestReActRouterNode(unittest.IsolatedAsyncioTestCase):
    @patch("graph.nodes.router.make_llm")
    async def test_router_node_basic(self, mock_make_llm):
        from graph.nodes.router import router_node
        from unittest.mock import AsyncMock

        mock_llm_instance = MagicMock()
        mock_bound_llm = MagicMock()
        mock_make_llm.return_value = mock_llm_instance
        mock_llm_instance.bind_tools.return_value = mock_bound_llm

        # Mock tool call output from LLM
        mock_response = MagicMock()
        mock_response.tool_calls = [
            {"name": "route", "args": {"workflow": "conversation"}},
        ]
        mock_bound_llm.ainvoke = AsyncMock(return_value=mock_response)

        state = {
            "messages": [HumanMessage(content="Hello Marcus!")],
            "user_id": "test_user",
        }

        res = await router_node(state, config={})
        self.assertEqual(res.get("workflow"), "conversation")


if __name__ == "__main__":
    unittest.main()
