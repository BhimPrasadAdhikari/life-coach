"""
interfaces/_base.py — Unified data models for channel interfaces.
Converts native channel format into single unified AgentRequest Pydantic model.
"""
from __future__ import annotations
from typing import Literal, Any
from pydantic import BaseModel, Field


class MediaAttachment(BaseModel):
    """Media item attached to a message (audio, image, document)."""
    type: str = Field(description="Media type, e.g. 'image', 'audio', 'document'")
    url: str | None = Field(default=None, description="URL or URI of the media asset")
    mime_type: str | None = Field(default=None, description="MIME type if known")


class AgentRequest(BaseModel):
    """Unified request model across all incoming client channels."""
    user_id: str = Field(description="Globally unique user identifier, e.g., 'wa_+1512...', 'cl_uuid'")
    thread_id: str = Field(description="Conversation thread identifier")
    content: str = Field(description="Normalized user text message content")
    media: list[MediaAttachment] = Field(default_factory=list, description="Attached media items")
    channel: Literal["whatsapp", "chainlit", "slack", "instagram", "api"] = Field(
        description="Channel platform origin"
    )
    model_key: str = Field(default="groq-llama3.3", description="Requested LLM model key")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Raw channel-specific metadata")


class AgentResponse(BaseModel):
    """Unified response model returned from graph execution."""
    user_id: str
    thread_id: str
    content: str
    workflow: str = Field(default="conversation", description="Executed workflow mode: conversation, audio, image, self_evolve")
    media_url: str | None = Field(default=None, description="Generated media output URL if audio/image")
    metadata: dict[str, Any] = Field(default_factory=dict)
