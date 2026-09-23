"""Start Chainlit with a Windows-compatible asyncio policy."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
existing_pythonpath = os.environ.get("PYTHONPATH", "")
os.environ["PYTHONPATH"] = (
    str(ROOT)
    if not existing_pythonpath
    else str(ROOT) + os.pathsep + existing_pythonpath
)

if sys.platform == "win32" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if __name__ == "__main__":
    chainlit_executable = Path(sys.executable).with_name("chainlit.exe")
    sys.argv[0] = str(chainlit_executable)
    from chainlit.cli import cli

    cli()
