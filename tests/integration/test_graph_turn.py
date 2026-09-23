"""
tests/integration/test_graph_turn.py — End-to-end integration tests for:
1. Versioned YAML Prompt Registry (prompts/registry.py)
2. WhatsApp Webhook Adapter (interfaces/whatsapp/app.py)
3. End-to-End Multi-Turn LangGraph Orchestration (graph/graph.py)
"""
import os
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi.testclient import TestClient
from fastapi import FastAPI
from langchain_core.messages import HumanMessage, AIMessage

from prompts.registry import get_prompt_registry, PromptRegistry
from interfaces._base import AgentRequest, AgentResponse
from interfaces.whatsapp.app import (
    router as whatsapp_router,
    parse_whatsapp_payload,
    dispatch_graph_request,
    send_whatsapp_response,
)
from graph.graph import get_compiled_app


class TestPromptRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = get_prompt_registry()

    def test_load_and_render_prompts(self):
        # Verify v1 system prompt
        system_prompt = self.registry.render_prompt(
            "system",
            version="v1",
            memory_context="User values balance.",
            summary="User discussed career change."
        )
        self.assertIn("Marcus Reyes", system_prompt)
        self.assertIn("User values balance.", system_prompt)

    def test_router_prompt(self):
        router_prompt = self.registry.render_prompt("router", version="v1")
        self.assertIn("retrieve_memories", router_prompt)
        self.assertIn("route", router_prompt)

    def test_memory_analysis_prompt(self):
        mem_prompt = self.registry.render_prompt("memory_analysis", version="v1", message="I live in Austin.")
        self.assertIn("I live in Austin.", mem_prompt)

    def test_hot_reload(self):
        self.registry.reload_prompts()
        data = self.registry.get_prompt("system", version="v1")
        self.assertEqual(data.get("name"), "system")


class TestWhatsAppWebhookAdapter(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(whatsapp_router)
        self.client = TestClient(app)

    def test_verify_webhook_success(self):
        response = self.client.get(
            "/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "MY_VERIFY_TOKEN",
                "hub.challenge": "123456789"
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "123456789")

    def test_verify_webhook_invalid_token(self):
        response = self.client.get(
            "/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "WRONG_TOKEN",
                "hub.challenge": "123456789"
            }
        )
        self.assertEqual(response.status_code, 403)

    def test_parse_meta_payload(self):
        meta_payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "123",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "messages": [{
                            "from": "15125551234",
                            "id": "wamid.HBgL",
                            "timestamp": "1670000000",
                            "text": {"body": "Hello Marcus, I need coaching on burnout."},
                            "type": "text"
                        }]
                    }
                }]
            }]
        }
        agent_req = parse_whatsapp_payload(meta_payload)
        self.assertEqual(agent_req.user_id, "wa_15125551234")
        self.assertEqual(agent_req.content, "Hello Marcus, I need coaching on burnout.")
        self.assertEqual(agent_req.channel, "whatsapp")

    def test_parse_twilio_payload(self):
        twilio_payload = {
            "From": "whatsapp:+15125559999",
            "Body": "Can we talk about my goals?",
            "NumMedia": "0"
        }
        agent_req = parse_whatsapp_payload(twilio_payload)
        self.assertEqual(agent_req.user_id, "wa_15125559999")
        self.assertEqual(agent_req.content, "Can we talk about my goals?")

    @patch("interfaces.whatsapp.app.send_whatsapp_response")
    @patch("interfaces.whatsapp.app.dispatch_graph_request")
    def test_handle_whatsapp_post_webhook(self, mock_dispatch, mock_send):
        mock_dispatch.return_value = AgentResponse(
            user_id="wa_15125551234",
            thread_id="thread_15125551234",
            content="Hello! I hear you regarding burnout. Where are you feeling this?",
            workflow="conversation"
        )
        mock_send.return_value = {"status": "sent", "provider": "meta"}
        payload = {
            "from": "+15125551234",
            "text": {"body": "I feel burned out."}
        }
        response = self.client.post("/whatsapp/webhook", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "processed")
        self.assertIn("burned out", data["request"]["content"])
        self.assertIn("Hello! I hear you", data["response"]["content"])


class TestWhatsAppOutboundDelivery(unittest.IsolatedAsyncioTestCase):
    @patch("services.graph_service.graph_service.invoke_graph")
    async def test_dispatch_uses_shared_graph_service(self, mock_invoke):
        mock_invoke.return_value = {
            "messages": [AIMessage(content="Shared service response")],
            "workflow": "conversation",
            "evolution_pending": False,
        }
        request = AgentRequest(
            user_id="wa_15125551234",
            thread_id="thread_15125551234",
            content="Hello",
            channel="whatsapp",
            model_key="groq-llama3.1",
        )

        response = await dispatch_graph_request(request)

        mock_invoke.assert_awaited_once_with(
            content="Hello",
            thread_id="thread_15125551234",
            model_key="groq-llama3.1",
            user_id="wa_15125551234",
            channel="whatsapp",
        )
        self.assertEqual(response.content, "Shared service response")

    @patch("interfaces.whatsapp.app.WHATSAPP_ACCESS_TOKEN", "meta-token")
    @patch("interfaces.whatsapp.app.WHATSAPP_PHONE_NUMBER_ID", "123456")
    @patch("interfaces.whatsapp.app.WHATSAPP_PROVIDER", "meta")
    @patch("interfaces.whatsapp.app.httpx.AsyncClient")
    async def test_send_meta_response(self, mock_client):
        provider_response = MagicMock()
        provider_response.json.return_value = {"messages": [{"id": "wamid.test"}]}
        provider_response.raise_for_status.return_value = None
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=provider_response
        )

        delivered = await send_whatsapp_response(
            "15125551234",
            AgentResponse(
                user_id="wa_15125551234",
                thread_id="thread_15125551234",
                content="Hello from Meta",
            ),
        )

        self.assertEqual(delivered["provider"], "meta")
        request = mock_client.return_value.__aenter__.return_value.post.call_args
        self.assertIn("123456/messages", request.args[0])
        self.assertEqual(request.kwargs["json"]["text"]["body"], "Hello from Meta")

    @patch("interfaces.whatsapp.app.TWILIO_ACCOUNT_SID", "AC123")
    @patch("interfaces.whatsapp.app.TWILIO_AUTH_TOKEN", "twilio-token")
    @patch("interfaces.whatsapp.app.TWILIO_WHATSAPP_FROM", "whatsapp:+14155550100")
    @patch("interfaces.whatsapp.app.WHATSAPP_PROVIDER", "twilio")
    @patch("interfaces.whatsapp.app.httpx.AsyncClient")
    async def test_send_twilio_response(self, mock_client):
        provider_response = MagicMock()
        provider_response.json.return_value = {"sid": "SM123"}
        provider_response.raise_for_status.return_value = None
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=provider_response
        )

        delivered = await send_whatsapp_response(
            "15125551234",
            AgentResponse(
                user_id="wa_15125551234",
                thread_id="thread_15125551234",
                content="Hello from Twilio",
            ),
        )

        self.assertEqual(delivered["provider"], "twilio")
        request = mock_client.return_value.__aenter__.return_value.post.call_args
        self.assertEqual(request.kwargs["data"]["To"], "whatsapp:+15125551234")
        self.assertEqual(request.kwargs["data"]["Body"], "Hello from Twilio")


class TestEndToEndGraphExecution(unittest.IsolatedAsyncioTestCase):
    @patch("graph.nodes.router.make_llm")
    @patch("graph.utils.chains.get_chat_model_from_config")
    @patch("graph.nodes.memory.get_memory_manager")
    async def test_multi_turn_conversation_turn(self, mock_get_mem_mgr, mock_get_chat_model, mock_make_router_llm):
        # Mock Router LLM tool calling (route tool call)
        mock_router_llm = MagicMock()
        mock_router_resp = MagicMock()
        tool_call = {
            "name": "route",
            "args": {"workflow": "conversation"},
            "id": "call_123"
        }
        mock_router_resp.tool_calls = [tool_call]
        mock_router_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_router_resp)
        mock_make_router_llm.return_value = mock_router_llm

        # Mock Conversation LLM using RunnableLambda
        from langchain_core.runnables import RunnableLambda
        mock_chat_model = RunnableLambda(
            lambda x: AIMessage(content="What specifically is feeling heavy right now?")
        )
        mock_get_chat_model.return_value = mock_chat_model


        # Mock Memory Manager
        mock_mem_mgr = MagicMock()
        mock_mem_mgr.extract_and_save_context = AsyncMock(return_value={"is_important": True, "formatted_memory": "User feels overwhelmed."})
        mock_mem_mgr.save_memory = AsyncMock(return_value={"is_important": True, "formatted_memory": "User feels overwhelmed."})
        mock_get_mem_mgr.return_value = mock_mem_mgr


        # Build app without checkpointer for lightweight test
        app = get_compiled_app(checkpointer=None)

        # Turn 1
        state_turn1 = {
            "messages": [HumanMessage(content="I'm feeling really stressed with work.")],
            "user_id": "wa_testuser",
            "thread_id": "thread_test",
            "channel": "whatsapp",
        }
        config = {"configurable": {"thread_id": "thread_test"}}
        res_turn1 = await app.ainvoke(state_turn1, config=config)

        self.assertEqual(res_turn1["workflow"], "conversation")
        messages = res_turn1["messages"]
        self.assertTrue(len(messages) >= 2)
        self.assertIn("feeling heavy", messages[-1].content)


if __name__ == "__main__":
    unittest.main()
