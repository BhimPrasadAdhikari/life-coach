import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import chainlit as cl 
from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver 

@cl.on_chat_start 
async def on_chat_start():
    cl.user_session.set("thread_id", 1)

@cl.on_message 
async def on_message(message: cl.Message):
    # Ensure path is set (needed for Chainlit workers)
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    
    # Lazy import to allow server to start before loading heavy ML models
    from graph.graph import create_graph
    
    msg = cl.Message(content="", author="Aria")
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

            output_state = await graph.aget_state(config={"configurable": {"thread_id": thread_id}})

    
    workflow = output_state.values.get("workflow")
    
    if workflow == "audio":
        response = output_state.values["messages"][-1].content 
        audio_buffer = output_state.values["audio_buffer"]
        output_audio_el = cl.Audio(
            name="Aria's Voice",
            auto_play=True,
            mime="audio/mpeg",
            content=audio_buffer,
        )
        await cl.Message(content=response, author="Aria", elements=[output_audio_el]).send()
    
    elif workflow == "image":
        response = output_state.values["messages"][-1].content
        image_buffer = output_state.values.get("image_buffer")
        if image_buffer:
            output_image_el = cl.Image(
                name="Generated Image",
                content=image_buffer,
                display="inline",
            )
            await cl.Message(content=response, author="Aria", elements=[output_image_el]).send()
        else:
            await cl.Message(content="Sorry, I couldn't generate the image.", author="Aria").send()
    
    else:
        await msg.send()
