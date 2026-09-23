from langgraph.graph import END, START, StateGraph

from core.paths import initialize_runtime_directories

from .nodes import (
    router_node,
    conversation_node,
    memory_saving_node,
    audio_node,
    image_node,
    summarization_node,
    self_evolve_node,
)

initialize_runtime_directories()

from .state import State
from .utils.edges import (
    select_router_workflow,
    should_summarize_conversation,
)


def create_graph():
    graph_builder = StateGraph(State)

    graph_builder.add_node("router_node", router_node)
    graph_builder.add_node("self_evolve_node", self_evolve_node)
    graph_builder.add_node("conversation_node", conversation_node)
    graph_builder.add_node("audio_node", audio_node)
    graph_builder.add_node("image_node", image_node)
    graph_builder.add_node("memory_saving_node", memory_saving_node)
    graph_builder.add_node("summarization_node", summarization_node)

    # 1. START -> ReAct tool-calling router node
    graph_builder.add_edge(START, "router_node")

    # 2. Router branches based on tool call selection / workflow state
    graph_builder.add_conditional_edges(
        "router_node",
        select_router_workflow,
        {
            "self_evolve_node": "self_evolve_node",
            "conversation_node": "conversation_node",
            "audio_node": "audio_node",
            "image_node": "image_node",
        },
    )

    # 3. Self evolve node outputs to conversation_node to narrate results
    graph_builder.add_edge("self_evolve_node", "conversation_node")

    # 4. Response nodes route to memory_saving_node (saving post-response)
    graph_builder.add_edge("conversation_node", "memory_saving_node")
    graph_builder.add_edge("audio_node", "memory_saving_node")
    graph_builder.add_edge("image_node", "memory_saving_node")

    # 5. After memory_saving_node, check if summarization is needed
    graph_builder.add_conditional_edges(
        "memory_saving_node",
        should_summarize_conversation,
        {
            "summarization_node": "summarization_node",
            "__end__": END,
        },
    )

    # 6. Summarization ends
    graph_builder.add_edge("summarization_node", END)

    return graph_builder


_builder = create_graph()


def get_compiled_app(checkpointer):
    return _builder.compile(checkpointer=checkpointer)