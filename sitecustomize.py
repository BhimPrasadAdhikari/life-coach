"""Process-startup compatibility hooks for the local application."""
from __future__ import annotations

import asyncio
import sys


if sys.platform == "win32" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
