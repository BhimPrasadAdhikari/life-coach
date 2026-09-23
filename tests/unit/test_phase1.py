"""
tests/unit/test_phase1.py — Unit tests for Phase 1 refactors:
- Redis cache & in-memory fallback
- SkillManager & AgentSpawner thread-safe singletons
- Summarization cooldown threshold (N>=10) and flag logic
- Workflow stream token generator
"""
import unittest
import threading
from unittest.mock import MagicMock, AsyncMock, patch
from langchain_core.messages import HumanMessage, AIMessage, AIMessageChunk

from core.cache import RedisCache, get_redis_cache
from modules.self_evolution.skill_manager import SkillManager, get_skill_manager
from modules.self_evolution.agent_spawner import AgentSpawner, get_agent_spawner
from graph.utils.edges import should_summarize_conversation
from gateway.stream_manager import StreamManager


class TestRedisCache(unittest.TestCase):
    def setUp(self):
        # Reset RedisCache singleton for testing
        RedisCache._instance = None
        self.cache = RedisCache()

    def test_in_memory_fallback_and_ttl(self):
        user_id = "user_123"
        self.assertIsNone(self.cache.get_skills_context(user_id))

        context = "### ACT Framework\nAcceptance and Commitment Therapy"
        self.cache.set_skills_context(user_id, context, ttl=300)

        self.assertEqual(self.cache.get_skills_context(user_id), context)

        self.cache.invalidate_skills_cache(user_id)
        self.assertIsNone(self.cache.get_skills_context(user_id))


class TestThreadSafeSingletons(unittest.TestCase):
    def setUp(self):
        SkillManager._instance = None
        AgentSpawner._instance = None

    def test_skill_manager_singleton(self):
        sm1 = SkillManager()
        sm2 = SkillManager()
        sm3 = get_skill_manager()

        self.assertIs(sm1, sm2)
        self.assertIs(sm2, sm3)

    def test_agent_spawner_singleton(self):
        asp1 = AgentSpawner()
        asp2 = AgentSpawner()
        asp3 = get_agent_spawner()

        self.assertIs(asp1, asp2)
        self.assertIs(asp2, asp3)

    def test_concurrent_singleton_instantiation(self):
        results_sm = []
        results_asp = []

        def worker():
            results_sm.append(SkillManager())
            results_asp.append(AgentSpawner())

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for instance in results_sm:
            self.assertIs(instance, results_sm[0])
        for instance in results_asp:
            self.assertIs(instance, results_asp[0])


class TestSummarizationCooldown(unittest.IsolatedAsyncioTestCase):
    def test_should_summarize_threshold_and_cooldown(self):
        # Case 1: < 10 messages -> END
        state_small = {"messages": [HumanMessage(content=f"msg {i}") for i in range(5)]}
        self.assertEqual(should_summarize_conversation(state_small), "__end__")

        # Case 2: >= 10 messages, no cooldown -> summarization_node
        state_large = {"messages": [HumanMessage(content=f"msg {i}") for i in range(12)]}
        self.assertEqual(should_summarize_conversation(state_large), "summarization_node")

        # Case 3: >= 10 messages, summary_cooldown=True -> END
        state_cooldown = {
            "messages": [HumanMessage(content=f"msg {i}") for i in range(12)],
            "summary_cooldown": True,
        }
        self.assertEqual(should_summarize_conversation(state_cooldown), "__end__")

    @patch("graph.nodes.summarization.get_chat_model_from_config")
    async def test_summarization_node_sets_cooldown(self, mock_get_model):
        from graph.nodes.summarization import summarization_node

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "New conversation summary."
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_model.return_value = mock_llm

        state = {
            "messages": [HumanMessage(content=f"msg {i}", id=str(i)) for i in range(12)],
            "summary": "Old summary",
        }
        config = {"configurable": {"model_key": "groq-llama3.3"}}

        result = await summarization_node(state, config)

        self.assertEqual(result["summary"], "New conversation summary.")
        self.assertTrue(result["summary_cooldown"])
        self.assertTrue(len(result["messages"]) > 0)


class TestStreamManager(unittest.IsolatedAsyncioTestCase):
    async def test_astream_tokens_multi_workflow(self):
        sm = StreamManager()

        mock_app = MagicMock()

        # Generator returning chunks for conversation_node and audio_node
        async def mock_astream(input_data, config, stream_mode):
            yield (
                AIMessageChunk(content="Hello "),
                {"langgraph_node": "conversation_node"},
            )
            yield (
                AIMessageChunk(content="World!"),
                {"langgraph_node": "audio_node"},
            )
            yield (
                AIMessageChunk(content="Internal node msg"),
                {"langgraph_node": "router_node"},
            )

        mock_app.astream = mock_astream

        tokens = []
        async for token in sm.astream_tokens(mock_app, "hi", "t123", "groq-llama3.3"):
            tokens.append(token)

        self.assertEqual(tokens, ["Hello ", "World!"])


if __name__ == "__main__":
    unittest.main()
