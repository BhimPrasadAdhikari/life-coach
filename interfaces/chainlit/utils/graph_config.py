import chainlit as cl
from core.config import DEFAULT_MODEL_KEY

def build_chainlit_graph_config() -> dict:
    thread_id = cl.user_session.get("thread_id")
    model_key = cl.user_session.get("model_key", DEFAULT_MODEL_KEY)
    return {
        "configurable": {
            "thread_id": thread_id,
            "model_key": model_key,
        }
    }