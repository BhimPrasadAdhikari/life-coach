from .state import State 
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from .utils.chains import get_character_response_chain, get_router_chain
from modules.memory.long_term.memory_manager import get_memory_manager
from .utils.helper import get_text_to_speech_module, get_text_to_image_module
from .utils.llm import get_chat_model
import os
import uuid


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

    memory_context = state.get("memory_context", "")
    chain = get_character_response_chain(state.get("summary", ""))

    text_to_image_module = get_text_to_image_module()

    scenario = await text_to_image_module.create_scenario(state["messages"][-5:])
    enhanced_prompt = await text_to_image_module.enhance_prompt(scenario.image_prompt)

    os.makedirs("public/images", exist_ok=True)
    img_path = f"public/images/image_{uuid.uuid4()}.png"

    # Generate the image
    await text_to_image_module.generate_image(enhanced_prompt, img_path)

    # Inject the image prompt information as an AI message 
    scenario_message = HumanMessage(content=f"<image attached by Aria generated from prompt: {scenario.image_prompt}")
    updated_messages = state["messages"] + [scenario_message]

    response = await chain.ainvoke({
        "messages": updated_messages,
        "memory_context": memory_context,
    }, config=config)

    return {"messages": response, "image_path": img_path}
    

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

async def summarization_node(state: State):
    """Summarize the long number of messages to reduce context overhead"""
    model = get_chat_model()
    summary = state.get("summary", "")

    if summary:
        summary_message = (
            f"This is summary of the conversation to date between Coach Aria and the user: {summary}\n\n"
            "Extend the summary by taking into account the new messages above."
        )
    else:
        summary_message = (
            "Create a summary of the conversation above between Coach Aria and the User."
            "The summary must be a short description of the conversation so far,"
            "but that captures all the relevant information shared between Coach Aria and the user: "
        )

    messages = state["messages"] + [HumanMessage(content=summary_message)]
    response = await  model.ainvoke(messages)

    delete_messages = [RemoveMessage(id=m.id) for m in state["messages"][:-20]]

    return {"summary": response.content, "messages": delete_messages}

