from langgraph.graph import END, START, StateGraph 
from .nodes import conversation_node, memory_saving_node, memory_retrieval_node 
from .state import State 

def create_graph():

    graph_builder = StateGraph(State)
    graph_builder.add_node("memory_saving_node", memory_saving_node)
    graph_builder.add_node("memory_retrieval_node", memory_retrieval_node)
    graph_builder.add_node("conversation_node", conversation_node)
    graph_builder.add_edge(START, "memory_retrieval_node")
    graph_builder.add_edge("memory_retrieval_node", "conversation_node")
    graph_builder.add_edge("conversation_node", "memory_saving_node")
    graph_builder.add_edge("memory_saving_node", END)   

    return graph_builder

