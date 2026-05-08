from __future__ import annotations
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from .llm import get_chat_model_from_config, make_llm
from core.config import EVOLVE_CHECK_MODEL_KEY
from core.prompts import SYSTEM_PROMPT, ROUTER_PROMPT
from pydantic import BaseModel, Field
from typing import Literal


class RouterResponse(BaseModel):
    response_type: Literal["conversation", "image", "audio"] = Field(
        description="The response type to give to the user. It must be one of 'conversation', 'image', 'audio'"
    )


def get_router_chain(config: RunnableConfig | None = None):
    """Router uses a fast, cheap model regardless of user preference."""
    model = make_llm(EVOLVE_CHECK_MODEL_KEY, temperature=0.3).with_structured_output(RouterResponse)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", ROUTER_PROMPT),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )
    return prompt | model


def get_character_response_chain(
    summary: str = "",
    active_skills: str = "",
    evolved_context: str = "",
    config: RunnableConfig | None = None,
):
    """
    Build Marcus's main response chain using the user-selected model.
    Falls back through Groq -> Gemini on rate-limit automatically.
    """
    model = get_chat_model_from_config(config, temperature=0.7, with_fallback=True)
    system_message = SYSTEM_PROMPT

    if active_skills:
        system_message += active_skills

    if evolved_context:
        system_message += (
            "\n\n---\n"
            "## WHAT YOU JUST CREATED THIS TURN\n"
            f"{evolved_context}\n\n"
            "In your response, briefly and naturally mention what you built — "
            "in Marcus's voice, grounded and specific, not over-explained. "
            "One or two sentences is enough. Then continue the coaching conversation."
        )

    if summary:
        system_message += f"\n\nSummary of the conversation so far: {summary}"

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_message),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )
    return prompt | model
