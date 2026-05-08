"""
Tool Creator — lets Marcus write and save Python tools on the fly.
Each tool is a self-contained Python function stored under graph/tools/dynamic/
and tracked in data/tools_registry.json.
"""
import os
import ast
import json
import logging
import importlib.util
import subprocess
import sys
import shutil
import shlex
from pathlib import Path
from datetime import datetime
from utils.file_lock import read_json_atomic, write_json_atomic

# Paths — resolve relative to this file so imports work regardless of cwd
_BASE = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = _BASE / "graph" / "tools" / "dynamic"
REGISTRY_FILE = _BASE / "data" / "tools_registry.json"
REGISTRY_PENDING_FILE = _BASE / "data" / "tools_registry_pending.json"

logger = logging.getLogger(__name__)


class ToolCreator:
    """Creates, stores, and executes dynamically generated Python tools."""

    def __init__(self):
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._llm = None  # lazy-initialized on first use

    def _get_llm(self):
        if self._llm is None:
            from graph.utils.llm import make_llm
            from core.config import DEFAULT_TEMPERATURE, DEFAULT_MODEL_KEY

            self._llm = make_llm(DEFAULT_MODEL_KEY, temperature=0.2)
        return self._llm

    # ------------------------------------------------------------------
    # Registry helpers
    # ------------------------------------------------------------------

    def _load_registry(self) -> dict:
        data = read_json_atomic(str(REGISTRY_FILE))
        return data or {}

    def _save_registry(self, registry: dict) -> None:
        write_json_atomic(str(REGISTRY_FILE), registry)

    # ------------------------------------------------------------------
    # Core create / load / execute
    # ------------------------------------------------------------------

    async def create_tool(self, spec: dict) -> dict:
        """
        Ask the LLM to write a Python tool based on *spec*, validate it,
        save it to disk, and register it.

        spec keys (from SELF_EVOLVE_DISPATCH_PROMPT output):
          - function_name
          - input_description
          - output_description
          - name         (display name)
          - description  (human-readable)
        """
        from core.prompts import TOOL_CREATION_PROMPT

        prompt = TOOL_CREATION_PROMPT.format(spec=json.dumps(spec, indent=2))
        response = await self._get_llm().ainvoke(prompt)
        code = response.content.strip()

        # Strip markdown code fences if the LLM wrapped the output
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0].strip()
        elif "```" in code:
            code = code.split("```")[1].split("```")[0].strip()

        # Validate syntax before touching disk
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            logger.error(f"ToolCreator: syntax error in generated code: {e}")
            raise ValueError(f"Generated tool has a syntax error: {e}")

        # Extract the first function name
        func_names = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        ]
        if not func_names:
            raise ValueError("No function definition found in generated tool code.")

        func_name = spec.get("function_name") or func_names[0]
        tool_id = func_name

        # Write to a pending file and register as pending for human approval
        pending_file = TOOLS_DIR / f"pending_{tool_id}.py"
        with open(pending_file, "w", encoding="utf-8") as f:
            f.write(code)

        pending = read_json_atomic(str(REGISTRY_PENDING_FILE)) or {}
        entry = {
            "id": tool_id,
            "name": spec.get("name", tool_id),
            "description": spec.get("description", ""),
            "function_name": func_name,
            "file_path": str(pending_file),
            "created_at": datetime.now().isoformat(),
            "call_count": 0,
            "status": "pending",
        }
        pending[tool_id] = entry
        write_json_atomic(str(REGISTRY_PENDING_FILE), pending)

        logger.info(f"ToolCreator: created pending tool '{tool_id}' at {pending_file}")
        return entry

    def list_pending_tools(self) -> list:
        return list((read_json_atomic(str(REGISTRY_PENDING_FILE)) or {}).values())

    def approve_tool(self, tool_id: str) -> dict:
        pending = read_json_atomic(str(REGISTRY_PENDING_FILE)) or {}
        if tool_id not in pending:
            raise KeyError(f"Pending tool '{tool_id}' not found")

        entry = pending.pop(tool_id)
        pending_path = Path(entry["file_path"])
        final_path = TOOLS_DIR / f"{tool_id}.py"

        # Move file into place
        os.replace(str(pending_path), str(final_path))

        # Add to main registry
        registry = self._load_registry()
        entry.pop("status", None)
        entry["file_path"] = str(final_path)
        entry["approved_at"] = datetime.now().isoformat()
        registry[tool_id] = entry
        self._save_registry(registry)
        write_json_atomic(str(REGISTRY_PENDING_FILE), pending)

        logger.info(f"ToolCreator: approved tool '{tool_id}' -> {final_path}")
        return entry

    def load_all_tools(self) -> list:
        """Return a list of all registered tool metadata dicts."""
        return list(self._load_registry().values())

    def execute_tool(self, tool_id: str, input_data: str) -> str:
        """
        Dynamically load and run a registered tool.
        Returns the tool's string output, or an error message.
        """
        registry = self._load_registry()
        if tool_id not in registry:
            return f"Tool '{tool_id}' is not registered."

        entry = registry[tool_id]
        tool_file = Path(entry["file_path"])

        if not tool_file.exists():
            return f"Tool file missing: {tool_file}"
        # Choose execution mode: 'docker' for containerized sandbox, otherwise local worker
        exec_mode = os.getenv("TOOL_EXECUTION_MODE", "worker").lower()

        def _run_worker():
            worker_path = Path(__file__).resolve().parent / "tool_worker.py"
            try:
                proc = subprocess.run(
                    [sys.executable, str(worker_path), str(tool_file), entry["function_name"]],
                    input=(input_data or "").encode("utf-8"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=int(os.getenv("TOOL_EXECUTION_TIMEOUT", "10")),
                )

                if proc.returncode != 0:
                    err = proc.stderr.decode("utf-8", errors="replace")
                    logger.error(f"ToolCreator: worker error for '{tool_id}': {err}")
                    return False, f"Error running tool '{tool_id}': {err.strip()}"

                return True, proc.stdout.decode("utf-8", errors="replace")

            except subprocess.TimeoutExpired:
                logger.error(f"ToolCreator: tool '{tool_id}' timed out (worker)")
                return False, f"Error running tool '{tool_id}': timeout"
            except Exception as e:
                logger.error(f"ToolCreator: unexpected error executing '{tool_id}' (worker): {e}")
                return False, f"Error running tool '{tool_id}': {e}"

        def _run_docker():
            # Ensure docker is available
            docker_bin = shutil.which("docker")
            if not docker_bin:
                return False, "docker not available on PATH"

            # Prepare container constraints
            mem = os.getenv("TOOL_DOCKER_MEMORY", "128m")
            cpus = os.getenv("TOOL_DOCKER_CPUS", "0.5")
            pids = os.getenv("TOOL_DOCKER_PIDS", "64")
            timeout_sec = int(os.getenv("TOOL_EXECUTION_TIMEOUT", "10"))

            tools_dir = str(tool_file.parent.resolve())
            tool_name = tool_file.name
            func = entry["function_name"]

            # Build docker command
            cmd = [
                docker_bin,
                "run",
                "--rm",
                "--network",
                "none",
                "--memory",
                mem,
                "--pids-limit",
                pids,
                "--cpus",
                cpus,
                "-v",
                f"{tools_dir}:/tools:ro",
                "-w",
                "/tools",
                "python:3.11-slim",
                "python",
                tool_name,
                func,
            ]

            try:
                proc = subprocess.run(
                    cmd,
                    input=(input_data or "").encode("utf-8"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout_sec,
                )

                if proc.returncode != 0:
                    err = proc.stderr.decode("utf-8", errors="replace")
                    logger.error(f"ToolCreator: docker worker error for '{tool_id}': {err}")
                    return False, f"Error running tool '{tool_id}' in docker: {err.strip()}"

                return True, proc.stdout.decode("utf-8", errors="replace")

            except subprocess.TimeoutExpired:
                logger.error(f"ToolCreator: tool '{tool_id}' timed out (docker)")
                return False, f"Error running tool '{tool_id}': timeout"
            except Exception as e:
                logger.error(f"ToolCreator: unexpected error executing '{tool_id}' (docker): {e}")
                return False, f"Error running tool '{tool_id}': {e}"

        # Execute according to chosen mode
        if exec_mode == "docker":
            ok, out = _run_docker()
            if not ok:
                # Fallback to worker if docker unavailable or failed
                logger.info(f"ToolCreator: docker execution failed for '{tool_id}', falling back to worker: {out}")
                ok, out = _run_worker()
        else:
            ok, out = _run_worker()

        # Increment call count when execution succeeded
        if ok:
            registry[tool_id]["call_count"] += 1
            self._save_registry(registry)
            return out.strip()

        return out

    def get_tool_summary(self) -> str:
        """Human-readable list of all tools Marcus currently has."""
        tools = self.load_all_tools()
        if not tools:
            return "No custom tools built yet."
        lines = ["Custom tools Marcus has built:"]
        for t in tools:
            lines.append(f"  • {t['name']} — {t['description']}")
        return "\n".join(lines)


def get_tool_creator() -> ToolCreator:
    return ToolCreator()
