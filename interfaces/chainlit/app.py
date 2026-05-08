from io import BytesIO
import sys
import logging
import uuid
import os
from pathlib import Path
from mcp import ClientSession

# Add project root to path for imports
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import chainlit as cl 
from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver 
from graph.graph import create_graph

from modules.image.image_to_text import ImageToText

image_to_text = ImageToText()


logger = logging.getLogger(__name__)

from modules.speech.speech_to_text import SpeechToText 
from modules.speech.text_to_speech import TextToSpeech 

# Global module instance 
speech_to_text = SpeechToText()
text_to_speech = TextToSpeech()

# Password authentication callback (enables login and history sidebar)
@cl.password_auth_callback
def auth_callback(username: str, password: str):
    """
    Authenticate users with username/password.
    Set AUTH_USERNAME and AUTH_PASSWORD in .env to customize credentials.
    Default: user/password (for development only!)
    """
    # Development mode: disable authentication
    return cl.User(
        identifier=username,
        metadata={"role": "user", "provider": "dev-mode"}
    )

import json

def flatten(xss):
    """Flatten a list of lists into a single list."""
    return [x for xs in xss for x in xs]


import re as _re

def _format_api_error(e: Exception) -> tuple:
    """
    Parse an API exception and return (is_user_facing: bool, friendly_message: str).
    Surfaces rate-limit / quota / token-size errors clearly; marks unexpected errors
    as generic so callers can decide whether to re-raise.
    """
    err_str = str(e)
    if "rate_limit_exceeded" in err_str or "429" in err_str or "413" in err_str:
        msg_match = _re.search(r"'message':\s*'([^']+)'", err_str)
        friendly = msg_match.group(1) if msg_match else err_str
        retry_match = _re.search(r"(Please try again in [^\.']+)", friendly)
        retry_hint = f"\n\n**{retry_match.group(1)}.**" if retry_match else ""
        return True, f"⚠️ **API rate limit reached.**\n\n{friendly}{retry_hint}"
    return False, f"⚠️ **An unexpected error occurred.** Please try again.\n\n`{err_str[:300]}`"


@cl.on_mcp_connect
async def on_mcp_connect(connection, session: ClientSession):
    """Handle MCP server connection and store available tools."""
    try:
        result = await session.list_tools()
        tools = [{
            "name": t.name,
            "description": t.description,
            "input_schema": t.inputSchema,
        } for t in result.tools]
        
        # Store tools keyed by connection name
        mcp_tools = cl.user_session.get("mcp_tools", {})
        mcp_tools[connection.name] = tools
        cl.user_session.set("mcp_tools", mcp_tools)
        
        logger.info(f"MCP connected: {connection.name} with {len(tools)} tools")
    except Exception as e:
        logger.error(f"Error connecting to MCP {connection.name}: {e}")
        raise


@cl.step(type="tool")
async def call_mcp_tool(tool_use):
    """Call an MCP tool and return the result."""
    tool_name = tool_use.name
    tool_input = tool_use.input
    
    current_step = cl.context.current_step
    current_step.name = tool_name
    
    # Show clean input in the step UI
    current_step.input = json.dumps(tool_input, indent=2) if tool_input else "{}"
    
    # Find which MCP connection owns this tool
    mcp_tools = cl.user_session.get("mcp_tools", {})
    mcp_name = None
    
    for connection_name, tools in mcp_tools.items():
        if any(tool.get("name") == tool_name for tool in tools):
            mcp_name = connection_name
            break
    
    if not mcp_name:
        error_msg = f"Tool {tool_name} not found"
        current_step.output = error_msg
        return json.dumps({"error": error_msg})
    
    # Get the MCP session for this connection
    mcp_session, _ = cl.context.session.mcp_sessions.get(mcp_name)
    
    if not mcp_session:
        error_msg = f"MCP session {mcp_name} not found"
        current_step.output = error_msg
        return json.dumps({"error": error_msg})
    
    try:
        result = await mcp_session.call_tool(tool_name, tool_input)
        
        # Extract the text content from the MCP result
        if hasattr(result, 'content') and result.content:
            # Get text from TextContent objects
            text_parts = []
            for content in result.content:
                if hasattr(content, 'text'):
                    text_parts.append(content.text)
            output_text = "\n".join(text_parts)
        else:
            output_text = str(result)
        
        # Check if it's an error
        is_error = getattr(result, 'isError', False)
        if is_error:
            current_step.output = f"❌ {output_text}"
        else:
            # Try to format as JSON for cleaner display
            try:
                parsed = json.loads(output_text)
                current_step.output = json.dumps(parsed, indent=2)
            except:
                current_step.output = output_text
        
        return output_text
        
    except Exception as e:
        error_msg = str(e)
        current_step.output = f"❌ Error: {error_msg}"
        return json.dumps({"error": error_msg})


def get_all_mcp_tools():
    """Get all MCP tools from all connections."""
    mcp_tools = cl.user_session.get("mcp_tools", {})
    return flatten([tools for _, tools in mcp_tools.items()])


async def call_mcp_conversation(user_message: str):
    """
    Handle conversation with MCP tools using Groq LLM.
    This runs a tool-calling loop until the model stops requesting tools.
    """
    from graph.utils.llm import make_llm
    import os
    from core.config import DEFAULT_MODEL_KEY

    # Resolve which model to use
    model_key = cl.user_session.get("model_key", DEFAULT_MODEL_KEY)
    mcp_tools = get_all_mcp_tools()
    
    if not mcp_tools:
        logger.info("No MCP tools available")
        return None
    
    logger.info(f"🔧 MCP tools available: {[t['name'] for t in mcp_tools]}")
    
    # Convert MCP tools to OpenAI function format for Groq
    openai_tools = []
    for tool in mcp_tools:
        # Get the input schema, defaulting to empty object if not present
        input_schema = tool.get("input_schema", {"type": "object", "properties": {}})
        
        # Ensure required fields exist
        if "type" not in input_schema:
            input_schema["type"] = "object"
        if "properties" not in input_schema:
            input_schema["properties"] = {}
        
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", f"Tool: {tool['name']}"),
                "parameters": input_schema
            }
        }
        openai_tools.append(openai_tool)
    
    logger.info(f"🔧 Converted {len(openai_tools)} tools to OpenAI format")
    
    # Initialize Groq client for tool calling
    client = make_llm(model_key, temperature=0.3)
    
    # Bind tools to the model with tool_choice auto
    model_with_tools = client.bind_tools(openai_tools, tool_choice="auto")
    
    # Build messages using LangChain message types
    messages = [
        {"role": "system", "content": """You are Marcus Reyes, a life coach with access to Stripe tools.
CRITICAL RULES FOR TOOL USAGE:
1. Make ONE tool call at a time, then WAIT for the result before making the next call
2. ALWAYS use the ACTUAL IDs returned from previous tool calls (e.g., prod_xxx, price_xxx)
3. NEVER make up or guess IDs - they will fail
4. For creating a payment link, the correct sequence is:
   a) First: create_product → returns product ID (prod_xxx)
   b) Second: create_price with the ACTUAL product ID → returns price ID (price_xxx)  
   c) Third: create_payment_link with the ACTUAL price ID

When a user asks to create something, execute the tools step by step and use real IDs from responses."""},
        {"role": "user", "content": user_message}
    ]
    
    # Convert tools to LangChain format
    from langchain_core.tools import StructuredTool
    from pydantic import create_model
    
    # Build tool schemas for binding
    tool_schemas = []
    for tool in mcp_tools:
        tool_schemas.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}})
            }
        })
    
    # Bind tools to the model
    model_with_tools = client.bind_tools(mcp_tools)
    
    msg = cl.Message(content="", author="Marcus")
    
    # Tool calling loop
    max_iterations = 10
    for i in range(max_iterations):
        logger.info(f"🔄 Iteration {i+1}: Calling LLM with {len(messages)} messages")
        
        # Call the model
        try:
            response = await model_with_tools.ainvoke(messages)
        except Exception as e:
            is_user_facing, friendly = _format_api_error(e)
            await cl.Message(content=friendly, author="Marcus").send()
            logger.warning(f"LLM error shown to user: {str(e)[:300]}")
            return None
        
        logger.info(f"📝 Response type: {type(response)}")
        logger.info(f"📝 Response content: {response.content[:200] if response.content else 'None'}...")
        
        # Check for tool calls
        tool_calls = getattr(response, 'tool_calls', None)
        
        if not tool_calls:
            # No more tool calls, stream the final response
            logger.info("✅ No more tool calls, returning final response")
            await msg.stream_token(response.content)
            await msg.send()
            return response.content
        
        logger.info(f"🔧 Tool calls requested: {[tc['name'] for tc in tool_calls]}")
        
        # Process each tool call
        for tool_call in tool_calls:
            tool_name = tool_call['name']
            tool_args = tool_call['args']
            tool_id = tool_call.get('id', tool_name)
            
            # Remove null/empty optional args to avoid schema validation failures
            # (LLMs sometimes emit "null" strings for optional params they don't have values for)
            sanitized_args = {
                k: v for k, v in tool_args.items()
                if v is not None and str(v).lower() not in ("null", "none", "")
            }
            logger.info(f"🔨 Executing tool: {tool_name} with args: {sanitized_args}")
            
            # Create a mock tool_use object for call_mcp_tool
            class ToolUse:
                def __init__(self, name, input_data):
                    self.name = name
                    self.input = input_data
            
            tool_use = ToolUse(tool_name, sanitized_args)
            
            try:
                result = await call_mcp_tool(tool_use)
                logger.info(f"✅ Tool result: {str(result)[:500]}...")
            except Exception as e:
                # Rate-limit / quota errors: show message and stop immediately
                is_rate_limit = (
                    "rate_limit_exceeded" in str(e)
                    or "429" in str(e)
                    or "413" in str(e)
                )
                if is_rate_limit:
                    _, friendly = _format_api_error(e)
                    await cl.Message(content=friendly, author="Marcus").send()
                    logger.warning(f"Rate limit during tool call, stopping: {str(e)[:300]}")
                    return None
                logger.error(f"❌ Tool error: {e}")
                result = json.dumps({"error": str(e)})
            
            # Truncate tool results to avoid exceeding LLM token limits.
            # Target: keep each result under ~3000 chars (~750 tokens) so the
            # full conversation comfortably fits within the 12 000 TPM limit.
            MAX_TOOL_RESULT_CHARS = 3000
            result_str = str(result)
            if len(result_str) > MAX_TOOL_RESULT_CHARS:
                result_str = result_str[:MAX_TOOL_RESULT_CHARS] + f"\n\n[...truncated {len(result_str) - MAX_TOOL_RESULT_CHARS} chars to stay within token limits]"
                logger.info(f"✂️ Tool result truncated to {MAX_TOOL_RESULT_CHARS} chars")

            # Add tool call and result to messages
            messages.append({"role": "assistant", "content": "", "tool_calls": [tool_call]})
            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": result_str
            })
    
    logger.warning("⚠️ Max iterations reached")
    return None

# Model key mapping from Chainlit profile name
_PROFILE_TO_MODEL = {
    "Llama 3.1 8B (Groq — fast)": "groq-llama3.1",
    "Llama 3.3 70B (Groq — best)": "groq-llama3.3",
    "Gemini 2.0 Flash (Google)": "gemini-flash",
    "Gemini 1.5 Pro (Google)": "gemini-pro",
}


@cl.set_chat_profiles
async def set_chat_profiles(current_user: cl.User):
    return [
        cl.ChatProfile(name="Llama 3.3 70B (Groq — best)",  markdown_description="**Groq — Llama 3.3 70B** (Default) Fast, high-quality responses via Groq. Auto-falls back to Gemini if rate-limited."),
        cl.ChatProfile(name="Llama 3.1 8B (Groq — fast)",  markdown_description="**Groq — Llama 3.1 8B** Fastest responses, lighter model. Good for simple conversations."),
        cl.ChatProfile(name="Gemini 2.0 Flash (Google)",     markdown_description="**Google Gemini 2.0 Flash** Runs on Google's infrastructure — use when Groq is rate-limited."),
        cl.ChatProfile(name="Gemini 1.5 Pro (Google)",       markdown_description="**Google Gemini 1.5 Pro** Google's most capable model for complex coaching sessions."),
    ]


@cl.on_chat_start 
async def on_chat_start():
    # Generate unique thread ID for each new conversation
    thread_id = str(uuid.uuid4())
    cl.user_session.set("thread_id", thread_id)

    # Store selected model key from chat profile
    try:
        profile = cl.chat_profile or "Llama 3.3 70B (Groq — best)"
    except (KeyError, AttributeError):
        profile = "Llama 3.3 70B (Groq — best)"
    from core.config import DEFAULT_MODEL_KEY
    model_key = _PROFILE_TO_MODEL.get(profile, DEFAULT_MODEL_KEY)
    cl.user_session.set("model_key", model_key)

    # Initialize MCP tools storage
    cl.user_session.set("mcp_tools", {})
    
    # Add "New Conversation" action button
    actions = [
        cl.Action(name="new_conversation", label="🆕 New Conversation", description="Start a fresh conversation", payload={})
    ]
    await cl.Message(content="Hey — Marcus here. Good to connect. What's going on for you today?", actions=actions, author="Marcus").send()

@cl.on_chat_resume
async def on_chat_resume(thread):
    """Resume a previous conversation from the history sidebar."""
    # Restore the thread ID from the resumed conversation
    cl.user_session.set("thread_id", thread["id"])

    # Default model key if not stored (backward compat)
    if not cl.user_session.get("model_key"):
        from core.config import DEFAULT_MODEL_KEY
        cl.user_session.set("model_key", DEFAULT_MODEL_KEY)

    # Add action button for new conversation 
    actions = [
        cl.Action(name="new_conversation", label="🆕 New Conversation", description="Start a fresh conversation", payload={})
    ]
    await cl.Message(content="Good to see you again. Pick up where we left off?", actions=actions, author="Marcus").send()

@cl.action_callback("new_conversation")
async def new_conversation_callback(action):
    """Start a fresh conversation when user clicks 'New Conversation' button."""
    thread_id = str(uuid.uuid4())
    cl.user_session.set("thread_id", thread_id)
    # Preserve the selected model across resets
    if not cl.user_session.get("model_key"):
        from core.config import DEFAULT_MODEL_KEY
        cl.user_session.set("model_key", DEFAULT_MODEL_KEY)

    actions = [
        cl.Action(name="new_conversation", label="🆕 New Conversation", description="Start a fresh conversation", payload={})
    ]
    await cl.Message(content="Fresh start. What do you want to work on?", actions=actions, author="Marcus").send()

@cl.on_message 
async def on_message(message: cl.Message):
    # Ensure path is set (needed for Chainlit workers)
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    
    content = message.content 

    if message.elements:
        for el in message.elements:
            if isinstance(el, cl.Image):
                # Read image file content
                with open(el.path, "rb") as image_path:
                    image_bytes = image_path.read()
                
                # Analyze image and add to message content
                try:
                    # Use global ImageToText instance 
                    description = await image_to_text.analyze_image(
                        image_bytes,
                        "Describe this image in detail. Identify main objects, text, and actions visible.",
                        mime_type=el.mime or "image/jpeg"
                    )
                    content += f"\n[Image Analysis: {description}]"
                except Exception as e:
                    cl.logger.warning(f"Failed to analyze image: {e}")
    
    # Check if MCP tools are available - use MCP flow if so
    mcp_tools = get_all_mcp_tools()
    if mcp_tools:
        logger.info(f"🔧 Using MCP conversation flow with {len(mcp_tools)} tools")
        try:
            await call_mcp_conversation(content)
        except Exception as e:
            _, friendly = _format_api_error(e)
            logger.error(f"Unhandled error in call_mcp_conversation: {e}")
            await cl.Message(content=friendly, author="Marcus").send()
        return  # MCP path always owns the response (errors are already shown to the user)
    
    # Fallback to LangGraph flow
    # Lazy import to allow server to start before loading heavy ML models
    from graph.graph import create_graph
    
    msg = cl.Message(content="", author="Marcus")
    thread_id = cl.user_session.get("thread_id")

    try:
        async with cl.Step(type='run'):
            async with AsyncSqliteSaver.from_conn_string("checkpoint.db") as saver:
                graph = create_graph().compile(checkpointer=saver)
                async for chunk in graph.astream(
                    {"messages": [HumanMessage(content=content,)]},
                    {'configurable': {"thread_id": thread_id, "model_key": cl.user_session.get("model_key")}},
                    stream_mode="messages",
                ):
                    if chunk[1]["langgraph_node"] == "conversation_node" and isinstance(chunk[0], AIMessageChunk):
                        await msg.stream_token(chunk[0].content)
                output_state = await graph.aget_state(config={"configurable": {"thread_id": thread_id, "model_key": cl.user_session.get("model_key")}})
    except Exception as e:
        _, friendly = _format_api_error(e)
        logger.error(f"LangGraph error in on_message: {e}")
        await cl.Message(content=friendly, author="Marcus").send()
        return

    
    workflow = output_state.values.get("workflow")
    
    if workflow == "audio":
        response = output_state.values["messages"][-1].content 
        audio_buffer = output_state.values["audio_buffer"]
        output_audio_el = cl.Audio(
            name="Marcus's Voice",
            auto_play=True,
            mime="audio/mpeg",
            content=audio_buffer,
        )
        await cl.Message(content=response, author="Marcus", elements=[output_audio_el]).send()
    
    elif workflow == "image":
        response = output_state.values["messages"][-1].content
        image_path = output_state.values.get("image_path")
        if image_path:
            output_image_el = cl.Image(
                path=image_path,
                display="inline",
            )
            await cl.Message(content=response, author="Marcus", elements=[output_image_el]).send()
        else:
            await cl.Message(content="Something went wrong generating the image. Let me try a different approach.", author="Marcus").send()
    
    else:
        await msg.send()


@cl.on_audio_start
async def on_audio_start():
    return True

@cl.on_audio_chunk
async def on_audio_chunk(chunk: cl.InputAudioChunk):
    """Handle incoming audio chunks"""
    audio_buffer = cl.user_session.get("audio_buffer")
    
    if chunk.isStart or audio_buffer is None:
        if audio_buffer is None:
            audio_buffer = BytesIO()
        
        # Reset position if it's a new start or new buffer
        if chunk.isStart:
             audio_buffer = BytesIO() # Create fresh buffer on start
             
        # Try to determine extension
        mime_type = chunk.mimeType if chunk.mimeType else "audio/mp3"
        ext = mime_type.split("/")[1] if "/" in mime_type else "mp3"
        audio_buffer.name = f"input_audio.{ext}"
        
        logger.info(f"Audio chunk started: mime_type={mime_type}, isStart={chunk.isStart}")
        
        cl.user_session.set("audio_buffer", audio_buffer)
        cl.user_session.set("audio_mime_type", mime_type)
    
    audio_buffer.write(chunk.data)

@cl.on_audio_end
async def on_audio_end(elements=[]):
    """Process completed audio input"""
    import wave
    import io
    
    audio_buffer = cl.user_session.get("audio_buffer")
    if audio_buffer is None:
        raise ValueError("Audio buffer is missing")
    audio_buffer.seek(0)
    audio_data = audio_buffer.read()
    
    mime_type = cl.user_session.get("audio_mime_type")
    
    # Convert PCM16 to WAV for display in browser
    if mime_type and ("pcm" in mime_type.lower() or mime_type == "pcm16"):
        # Create WAV in memory for display
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(24000)
            wav_file.writeframes(audio_data)
        wav_buffer.seek(0)
        display_audio_data = wav_buffer.read()
        display_mime = "audio/wav"
    else:
        display_audio_data = audio_data
        display_mime = mime_type or "audio/mpeg"

    # Show user's audio message 
    input_audio_el = cl.Audio(
        name="Your Voice",
        mime=display_mime,
        content=display_audio_data,
        display="inline",
    )

    # Use global SpeechToText instance to transcribe audio 
    mime_type = cl.user_session.get("audio_mime_type")
    logger.info(f"on_audio_end: audio_data size={len(audio_data)}, mime_type={mime_type}")
    # --- Speech-to-text ---
    try:
        transcription = await speech_to_text.transcribe(audio_data, mime_type=mime_type)
    except Exception as e:
        logger.error(f"STT error: {e}")
        await cl.Message(
            content="⚠️ **Could not transcribe audio.** Please try again.",
            author="Marcus",
        ).send()
        return

    # Show what the user said (transcription) aligned to the right
    await cl.Message(
        content=f"{transcription}",
        author="You",
        type="user_message",
        elements=[input_audio_el, *elements]
    ).send()

    thread_id = cl.user_session.get("thread_id", 1)

    # --- LangGraph invocation ---
    try:
        async with AsyncSqliteSaver.from_conn_string("checkpoint.db") as short_term_memory:
            graph = create_graph().compile(checkpointer=short_term_memory)
            from core.config import DEFAULT_MODEL_KEY
            output_state = await graph.ainvoke(
                {"messages": [HumanMessage(content=transcription)]},
                {"configurable": {"thread_id": thread_id, "model_key": cl.user_session.get("model_key", DEFAULT_MODEL_KEY)}},
            )
    except Exception as e:
        _, friendly = _format_api_error(e)
        logger.error(f"LangGraph error in on_audio_end: {e}")
        await cl.Message(content=friendly, author="Marcus").send()
        return

    response_text = output_state["messages"][-1].content

    # --- Text-to-speech ---
    try:
        audio_buffer = await text_to_speech.synthesize(response_text)
        output_audio_el = cl.Audio(
            auto_play=True,
            mime="audio/mpeg",
            content=audio_buffer,
        )
        await cl.Message(author="Marcus", content=response_text, elements=[output_audio_el]).send()
    except Exception as e:
        logger.error(f"TTS error: {e}")
        # Fall back to text-only response if TTS fails
        await cl.Message(author="Marcus", content=response_text).send()

