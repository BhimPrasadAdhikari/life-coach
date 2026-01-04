from langgraph.graph import END, START, StateGraph 
from .nodes import (
    router_node,
    conversation_node,
    memory_saving_node,
    memory_retrieval_node,
    audio_node,
    image_node,
    summarization_node
)
from .state import State 
from .utils.edges import select_workflow, should_summarize_conversation

def create_graph():

    graph_builder = StateGraph(State)
    
    # Add all nodes
    graph_builder.add_node("memory_retrieval_node", memory_retrieval_node)
    graph_builder.add_node("router_node", router_node)
    graph_builder.add_node("conversation_node", conversation_node)
    graph_builder.add_node("audio_node", audio_node)
    graph_builder.add_node("image_node", image_node)
    graph_builder.add_node("memory_saving_node", memory_saving_node)
    graph_builder.add_node("summarization_node", summarization_node)


    # Flow: START → memory_retrieval → router → [conditional] → response → memory_saving → END
    
    # 1. First retrieve relevant memories
    graph_builder.add_edge(START, "memory_retrieval_node")

    # 2. Then determine response type (conversation, audio, or image)
    graph_builder.add_edge("memory_retrieval_node", "router_node")
    graph_builder.add_edge("router_node", "memory_saving_node")

    # 3. Route to appropriate response node based on workflow type
    graph_builder.add_conditional_edges(
        "memory_saving_node",
        select_workflow,
        {
            "conversation_node": "conversation_node",
            "audio_node": "audio_node",
            "image_node": "image_node",
        }
    )

    # 4. After response, check if summarization is needed
    graph_builder.add_conditional_edges(
        "conversation_node",
        should_summarize_conversation,
        {"summarization_node": "summarization_node", "__end__": END}
    )
    graph_builder.add_conditional_edges(
        "audio_node",
        should_summarize_conversation,
        {"summarization_node": "summarization_node", "__end__": END}
    )
    graph_builder.add_conditional_edges(
        "image_node",
        should_summarize_conversation,
        {"summarization_node": "summarization_node", "__end__": END}
    )

    # 5. End after saving memory
    graph_builder.add_edge("summarization_node", END)

    return graph_builder
