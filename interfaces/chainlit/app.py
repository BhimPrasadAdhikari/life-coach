from io import BytesIO
import sys
import logging
from pathlib import Path

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
        image_path = output_state.values.get("image_path")
        if image_path:
            output_image_el = cl.Image(
                path=image_path,
                display="inline",
            )
            await cl.Message(content=response, author="Aria", elements=[output_image_el]).send()
        else:
            await cl.Message(content="Sorry, I couldn't generate the image.", author="Aria").send()
    
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
    transcription = await speech_to_text.transcribe(audio_data, mime_type=mime_type)

    # Show what the user said (transcription) aligned to the right
    await cl.Message(
        content=f"{transcription}", 
        author="You", 
        type="user_message",
        elements=[input_audio_el, *elements]
    ).send()

    thread_id = cl.user_session.get("thread_id", 1)

    async with AsyncSqliteSaver.from_conn_string("checkpoint.db") as short_term_memory:
        graph = create_graph().compile(checkpointer=short_term_memory)
        output_state = await graph.ainvoke(
            {"messages": [HumanMessage(content=transcription)]},
            {"configurable": {"thread_id": thread_id}},
        )

    # Use global TextToSpeech instance to generate audio 
    audio_buffer = await text_to_speech.synthesize(output_state["messages"][-1].content) 

    output_audio_el = cl.Audio(
        auto_play=True,
        mime="audio/mpeg",
        content=audio_buffer,
    )

    await cl.Message(author="Aria", content=output_state["messages"][-1].content, elements=[output_audio_el]).send()

