from langgraph.graph import MessagesState 

class State(MessagesState):
    summary: str 
    memory_context: str 
    
