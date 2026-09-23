import json
import chainlit as cl
from services.graph_service import graph_service
from services.media_service import media_service
from services.mcp_service import mcp_service
from interfaces.chainlit.utils.actions import build_pending_action
from interfaces.chainlit.utils.errors import format_api_error
from core.exceptions import ImageToTextError

@cl.step(type="tool")
async def execute_chainlit_mcp_tool(name: str, args: dict):
    current_step = cl.context.current_step
    current_step.name = name
    current_step.input = json.dumps(args, indent=2) if args else "{}"
    
    mcp_tools = cl.user_session.get("mcp_tools", {})
    mcp_name = next(
        (conn for conn, tools in mcp_tools.items() if any(t.get("name") == name for t in tools)),
        None
    )
    
    if not mcp_name or not cl.context.session.mcp_sessions.get(mcp_name):
        err = f"Tool or Session {name} not found"
        current_step.output = err
        return err

    mcp_session, _ = cl.context.session.mcp_sessions.get(mcp_name)
    try:
        res = await mcp_session.call_tool(name, args)
        out = "\n".join([c.text for c in res.content if hasattr(c, "text")]) if getattr(res, "content", None) else str(res)
        current_step.output = out
        return out
    except Exception as e:
        err = f"Error: {e}"
        current_step.output = err
        return err

@cl.on_message 
async def on_message(message: cl.Message):
    content = message.content 

    if message.elements:
        for el in message.elements:
            if isinstance(el, cl.Image):
                try:
                    with open(el.path, "rb") as img_file:
                        description = await media_service.analyze_image(img_file.read(), mime_type=el.mime or "image/jpeg")
                        content += f"\n[Image Analysis: {description}]"
                except ImageToTextError as e:
                    await cl.Message(
                        author="Marcus",
                        content="Sorry, I couldn't analyze the attached image. Please try uploading it again."
                    ).send()
                    return

    mcp_tools = [item for group in cl.user_session.get("mcp_tools", {}).values() for item in group]
    if mcp_tools:
        msg = cl.Message(content="", author="Marcus")
        async def stream_cb(token: str):
            await msg.stream_token(token)
            
        await mcp_service.run_mcp_loop(
            user_message=content,
            mcp_tools=mcp_tools,
            tool_executor=execute_chainlit_mcp_tool,
            stream_callback=stream_cb,
            model_key=cl.user_session.get("model_key")
        )
        await msg.send()
        return

    thread_id = cl.user_session.get("thread_id")
    model_key = cl.user_session.get("model_key")
    msg = cl.Message(content="", author="Marcus")

    try:
        async with cl.Step(type="run"):
            async for token in graph_service.stream_conversation(content, thread_id, model_key):
                await msg.stream_token(token)
            
            output_state = await graph_service.get_state(thread_id, model_key)
    except Exception as e:
        _, friendly = format_api_error(e, model_key)
        await cl.Message(content=friendly, author="Marcus").send()
        return

    workflow = output_state.values.get("workflow")
    chainlit_actions = build_pending_action(output_state.values.get("pending_action"))

    if workflow == "audio":
        audio_path = output_state.values.get("audio_path")
        resp = output_state.values.get("messages", [])[-1].content
        elements = [cl.Audio(name="Marcus's Voice", path=audio_path, mime="audio/mpeg", auto_play=True)] if audio_path else []
        await cl.Message(content=resp, author="Marcus", elements=elements, actions=chainlit_actions).send()

    elif workflow == "image":
        image_path = output_state.values.get("image_path")
        elements = [cl.Image(path=image_path, display="inline")] if image_path else []
        await cl.Message(content="Here is the generated image.", author="Marcus", elements=elements, actions=chainlit_actions).send()

    else:
        msg.actions = chainlit_actions
        await msg.send()