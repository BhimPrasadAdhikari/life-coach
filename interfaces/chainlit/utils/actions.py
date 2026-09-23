from typing import Any
import chainlit as cl

def build_pending_action(pending_action: dict[str, Any] | None) -> list[cl.Action]:
    if not pending_action or not pending_action.get("type"):
        return []
    return [
        cl.Action(
            name=pending_action["type"],
            label=pending_action.get("label", "Approve"),
            payload=pending_action.get("payload", {}),
        )
    ]