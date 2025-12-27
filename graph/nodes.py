from .state import State 
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from .utils.chains import get_character_response_chain, get_router_chain
from modules.memory.long_term.memory_manager import get_memory_manager
from .utils.helper import get_text_to_speech_module, get_text_to_image_module


async def router_node(state: State, config: RunnableConfig):
    chain = get_router_chain()
    response = await chain.ainvoke({
        "messages": state["messages"][-3:],
    }, config=config)

    return {"workflow": response.response_type}

async def audio_node(state: State, config: RunnableConfig):
    memory_context = state.get("memory_context", "")

    chain = get_character_response_chain(state.get('summary', ""))
    text_to_speech_module = get_text_to_speech_module()

    response = await chain.ainvoke({
        "messages": state["messages"],
        "memory_context": memory_context
    }, config=config)

    # Extract text content from AIMessage for TTS
    output_audio = await text_to_speech_module.synthesize(response.content)

    return {"messages": response, "audio_buffer": output_audio}

async def image_node(state: State, config: RunnableConfig):
    """Generate an image based on the user's request."""
    text_to_image_module = get_text_to_image_module()
    
    # Get the user's last message as the image prompt
    human_messages = [msg for msg in state["messages"] if msg.type == "human"]
    if not human_messages:
        return {"messages": AIMessage(content="I couldn't find your image request.")}
    
    prompt = human_messages[-1].content
    
    # Generate the image
    image_bytes = await text_to_image_module.generate(prompt)
    
    response = AIMessage(content=f"Here's the image I created based on your request: '{prompt}'")
    
    return {"messages": response, "image_buffer": image_bytes}

async def conversation_node(state: State, config: RunnableConfig):
    chain = get_character_response_chain(state.get("summary", ""))
    response = await chain.ainvoke({
        "messages": state.get("messages", []), 
    }, config=config)

    return {"messages": response} 


async def memory_saving_node(state: State): 
    """Extracts relevant context from the conversation history."""
    if not state["messages"]:
        return {}
    
    # Find the last human message (not AI response)
    human_messages = [msg for msg in state["messages"] if msg.type == "human"]
    if human_messages:
        memory_manager = get_memory_manager() 
        await memory_manager.extract_and_save_context(human_messages[-1])
    return {}

def memory_retrieval_node(state: State):
    """Retrieve and inject relevant memories into the system prompt"""
    memory_manager = get_memory_manager()
    
    recent_context = " ".join([msg.content for msg in state["messages"][-3:]])
    memories = memory_manager.get_relevant_memories(recent_context)

    memory_context = memory_manager.format_memories_for_prompt(memories)
    return {"memory_context": memory_context}
