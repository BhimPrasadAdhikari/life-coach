"""Platform-specific asyncio configuration for database drivers."""
from __future__ import annotations

import asyncio
import sys


def configure_event_loop_policy() -> None:
    """Use a selector loop on Windows for Psycopg async compatibility."""
    if sys.platform == "win32" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
