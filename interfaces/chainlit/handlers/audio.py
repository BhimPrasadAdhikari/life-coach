from pathlib import Path
from io import BytesIO
import chainlit as cl

from services.graph_service import graph_service
from services.media_service import media_service
from interfaces.chainlit.utils.actions import build_pending_action
from interfaces.chainlit.utils.errors import format_api_error


@cl.on_audio_start
async def on_audio_start():
    # Initialize fresh audio buffer and default mime type for this voice session
    cl.user_session.set("audio_buffer", BytesIO())
    cl.user_session.set("audio_mime_type", "audio/wav")
    return True


@cl.on_audio_chunk
async def on_audio_chunk(chunk: cl.InputAudioChunk):
    audio_buffer = cl.user_session.get("audio_buffer")
    if audio_buffer is None:
        audio_buffer = BytesIO()
        cl.user_session.set("audio_buffer", audio_buffer)
        
    if chunk.mimeType:
        cl.user_session.set("audio_mime_type", chunk.mimeType)
        
    audio_buffer.write(chunk.data)


@cl.on_audio_end
async def on_audio_end():
    audio_buffer: BytesIO = cl.user_session.get("audio_buffer")
    if not audio_buffer:
        return
        
    audio_data = audio_buffer.getvalue()
    mime_type = cl.user_session.get("audio_mime_type", "audio/wav")

    if not audio_data:
        return

    # 1. Transcribe incoming voice message
    try:
        transcription = await media_service.transcribe_audio(audio_data, mime_type=mime_type)
    except Exception as e:
        await cl.Message(content=f"Could not transcribe audio: {e}", author="Marcus").send()
        return

    if not transcription or not transcription.strip():
        await cl.Message(content="No voice detected.", author="Marcus").send()
        return

    # Render user transcription in chat
    await cl.Message(content=transcription, author="You", type="user_message").send()

    thread_id = cl.user_session.get("thread_id")
    model_key = cl.user_session.get("model_key")

    # 2. Invoke Graph Agent
    try:
        output_state = await graph_service.invoke_graph(transcription, thread_id, model_key)
    except Exception as e:
        _, friendly = format_api_error(e, model_key)
        await cl.Message(content=friendly, author="Marcus").send()
        return

    response_text = output_state["messages"][-1].content
    chainlit_actions = build_pending_action(output_state.get("pending_action"))

    # 3. Synthesize speech and play back file path directly via cl.Audio
    try:
        audio_path = await media_service.synthesize_speech(response_text)
        
        output_audio_el = cl.Audio(
            name="Response", 
            auto_play=True, 
            path=str(audio_path)
        )
        await cl.Message(
            author="Marcus", 
            content=response_text, 
            elements=[output_audio_el], 
            actions=chainlit_actions
        ).send()
    except Exception:
        # Fallback to text message if TTS generation fails
        await cl.Message(
            author="Marcus", 
            content=response_text, 
            actions=chainlit_actions
        ).send()