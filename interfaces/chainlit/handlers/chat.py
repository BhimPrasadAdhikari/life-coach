import uuid
import chainlit as cl
from mcp import ClientSession
from core.config import DEFAULT_MODEL_KEY
from interfaces.chainlit.handlers.profiles import PROFILE_MAP
from services.graph_service import graph_service

@cl.on_chat_start 
async def on_chat_start():
    await graph_service.initialize()
    cl.user_session.set("thread_id", str(uuid.uuid4()))
    profile = cl.user_session.get("chat_profile") or "GPT-OSS 120B (Groq — best)"

    cl.user_session.set("model_key", PROFILE_MAP.get(profile, DEFAULT_MODEL_KEY))
    cl.user_session.set("mcp_tools", {})
    
    actions = [cl.Action(name="new_conversation", label="🆕 New Conversation", payload={})]
    await cl.Message(content="Hey — Marcus here. What's on your mind today?", actions=actions, author="Marcus").send()

@cl.on_chat_resume
async def on_chat_resume(thread):
    await graph_service.initialize()
    cl.user_session.set("thread_id", thread["id"])
    if not cl.user_session.get("model_key"):
        cl.user_session.set("model_key", DEFAULT_MODEL_KEY)

@cl.on_mcp_connect
async def on_mcp_connect(connection, session: ClientSession):
    result = await session.list_tools()
    tools = [{"name": t.name, "description": t.description, "input_schema": t.inputSchema} for t in result.tools]
    mcp_tools = cl.user_session.get("mcp_tools", {})
    mcp_tools[connection.name] = tools
    cl.user_session.set("mcp_tools", mcp_tools)