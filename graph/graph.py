from langgraph.graph import END, START, StateGraph 
from .nodes import (
    router_node,
    conversation_node,
    memory_saving_node,
    memory_retrieval_node,
    audio_node,
    image_node,
    summarization_node,
    skill_injection_node,
    self_evolve_check_node,
    self_evolve_node,
)
from .state import State 
from .utils.edges import (
    select_workflow,
    should_summarize_conversation,
    route_after_evolve_check,
)

def create_graph():

    graph_builder = StateGraph(State)
    
    # --- Nodes ---
    graph_builder.add_node("skill_injection_node", skill_injection_node)
    graph_builder.add_node("memory_retrieval_node", memory_retrieval_node)
    graph_builder.add_node("self_evolve_check_node", self_evolve_check_node)
    graph_builder.add_node("self_evolve_node", self_evolve_node)
    graph_builder.add_node("router_node", router_node)
    graph_builder.add_node("conversation_node", conversation_node)
    graph_builder.add_node("audio_node", audio_node)
    graph_builder.add_node("image_node", image_node)
    graph_builder.add_node("memory_saving_node", memory_saving_node)
    graph_builder.add_node("summarization_node", summarization_node)

    # --- Flow ---
    # 1. Inject skills + retrieve memories in parallel from state perspective,
    #    but run sequentially: skills first, then memory, then evolve check
    graph_builder.add_edge(START, "skill_injection_node")
    graph_builder.add_edge("skill_injection_node", "memory_retrieval_node")

    # 2. Check if Marcus needs to self-evolve before routing
    graph_builder.add_edge("memory_retrieval_node", "self_evolve_check_node")

    # 3. If self_evolve flagged → self_evolve_node; otherwise → router
    graph_builder.add_conditional_edges(
        "self_evolve_check_node",
        route_after_evolve_check,
        {
            "self_evolve_node": "self_evolve_node",
            "router_node": "router_node",
        },
    )

    # 4. After self-evolution, always run conversation to narrate what happened
    graph_builder.add_edge("self_evolve_node", "memory_saving_node")

    # 5. Normal router → memory_saving → select workflow
    graph_builder.add_edge("router_node", "memory_saving_node")
    graph_builder.add_conditional_edges(
        "memory_saving_node",
        select_workflow,
        {
            "conversation_node": "conversation_node",
            "audio_node": "audio_node",
            "image_node": "image_node",
        },
    )

    # 6. After each response node, check if summarization is needed
    graph_builder.add_conditional_edges(
        "conversation_node",
        should_summarize_conversation,
        {"summarization_node": "summarization_node", "__end__": END},
    )
    graph_builder.add_conditional_edges(
        "audio_node",
        should_summarize_conversation,
        {"summarization_node": "summarization_node", "__end__": END},
    )
    graph_builder.add_conditional_edges(
        "image_node",
        should_summarize_conversation,
        {"summarization_node": "summarization_node", "__end__": END},
    )

    # 7. Summarization always ends
    graph_builder.add_edge("summarization_node", END)

    return graph_builder
