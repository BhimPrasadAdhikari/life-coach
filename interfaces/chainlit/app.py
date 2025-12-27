import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import chainlit as cl 
from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver 

@cl.on_chat_start 
async def on_chat_start():
    cl.user_session.set("thread_id", 1)

@cl.on_message 
async def on_message(message: cl.Message):
    # Lazy import to allow server to start before loading heavy ML models
    from graph.graph import create_graph
    
    msg = cl.Message(content="")
    content = message.content 
    thread_id = cl.user_session.get("thread_id")

    async with cl.Step(type='run'):
        async with AsyncSqliteSaver.from_conn_string("checkpoint.db") as saver:
            graph = create_graph().compile(checkpointer=saver)
            async for chunk in graph.astream(
                {"messages": [HumanMessage(content=content,)]},
                {'configurable': {"thread_id": thread_id}},
                stream_mode="messages",
            ):
                if chunk[1]["langgraph_node"] == "conversation_node" and isinstance(chunk[0], AIMessageChunk):
                    await msg.stream_token(chunk[0].content) 

        await msg.send()
