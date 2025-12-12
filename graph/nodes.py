from .state import State 
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from .utils.chains import get_character_response_chain
from modules.memory.long_term.memory_manager import get_memory_manager

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
    
    memory_manager = get_memory_manager() 
    await memory_manager.extract_and_save_context(state["messages"][-1])
    return {}

def memory_retrieval_node(state: State):
    """Retrieve and inject relevant memories into the system prompt"""
    memory_manager = get_memory_manager()
    
    recent_context = " ".join([msg.content for msg in state["messages"][-3:]])
    memories = memory_manager.get_relevant_memories(recent_context)

    memory_context = memory_manager.format_memories_for_prompt(memories)
    return {"memory_context": memory_context}
