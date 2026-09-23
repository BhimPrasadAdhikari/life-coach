from __future__ import annotations
import asyncio
import logging
from core.asyncio_compat import configure_event_loop_policy

configure_event_loop_policy()

logging.getLogger(__name__).info(
    "Chainlit asyncio policy: %s",
    type(asyncio.get_event_loop_policy()).__name__,
)

import sys
from pathlib import Path

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from core.paths import initialize_runtime_directories

initialize_runtime_directories()

# Register project root into runtime Python path
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import all Chainlit event hooks to register handlers with the engine
from interfaces.chainlit.handlers.auth import auth_callback
from interfaces.chainlit.handlers.profiles import set_chat_profiles
from interfaces.chainlit.handlers.chat import on_chat_start, on_chat_resume, on_mcp_connect
from interfaces.chainlit.handlers.actions import approve_skill_action, new_conversation_callback
from interfaces.chainlit.handlers.message import on_message
from interfaces.chainlit.handlers.audio import on_audio_start, on_audio_chunk, on_audio_end

__all__ = [
    "auth_callback",
    "set_chat_profiles",
    "on_chat_start",
    "on_chat_resume",
    "on_mcp_connect",
    "approve_skill_action",
    "new_conversation_callback",
    "on_message",
    "on_audio_start",
    "on_audio_chunk",
    "on_audio_end",
]