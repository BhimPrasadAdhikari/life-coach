"""
modules/evolution/sandbox.py — Hardened Docker-only execution sandbox.
Host subprocess execution is strictly disabled for security.
"""
from __future__ import annotations
import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class DockerSandbox:
    """Executes untrusted LLM-generated code strictly inside a isolated Docker container."""

    def __init__(
        self,
        memory_limit: str = "128m",
        cpus: str = "0.5",
        pids_limit: str = "64",
        timeout: int = 10,
    ) -> None:
        self.memory_limit = os.getenv("TOOL_DOCKER_MEMORY", memory_limit)
        self.cpus = os.getenv("TOOL_DOCKER_CPUS", cpus)
        self.pids_limit = os.getenv("TOOL_DOCKER_PIDS", pids_limit)
        self.timeout = int(os.getenv("TOOL_EXECUTION_TIMEOUT", str(timeout)))

    def is_docker_available(self) -> bool:
        """Check if Docker CLI is installed and the Docker daemon is responsive."""
        docker_bin = shutil.which("docker")
        if not docker_bin:
            return False
        try:
            res = subprocess.run(
                [docker_bin, "info"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=3,
            )
            return res.returncode == 0
        except Exception:
            return False

    def run_tool(
        self,
        tool_file: Path,
        func_name: str,
        input_data: str = "",
    ) -> tuple[bool, str]:
        """
        Execute a Python tool file inside a isolated Docker container.
        Fails hard with RuntimeError if Docker is unavailable.
        """
        if not self.is_docker_available():
            raise RuntimeError(
                "CRITICAL SECURITY VIOLATION: Docker is required for code sandbox execution. "
                "Subprocess fallback is disabled for security reasons."
            )

        docker_bin = shutil.which("docker")
        tools_dir = str(tool_file.parent.resolve())
        tool_name = tool_file.name

        cmd = [
            docker_bin,
            "run",
            "--rm",
            "--network",
            "none",
            "--memory",
            self.memory_limit,
            "--pids-limit",
            self.pids_limit,
            "--cpus",
            self.cpus,
            "-v",
            f"{tools_dir}:/tools:ro",
            "-w",
            "/tools",
            "python:3.11-slim",
            "python",
            tool_name,
            func_name,
        ]

        try:
            proc = subprocess.run(
                cmd,
                input=(input_data or "").encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout,
            )

            if proc.returncode != 0:
                err = proc.stderr.decode("utf-8", errors="replace")
                logger.error(f"DockerSandbox error: {err}")
                return False, f"Error running tool in docker: {err.strip()}"

            return True, proc.stdout.decode("utf-8", errors="replace")

        except subprocess.TimeoutExpired:
            logger.error("DockerSandbox: execution timed out")
            return False, "Error running tool: timeout"
        except Exception as e:
            logger.error(f"DockerSandbox: unexpected error: {e}")
            return False, f"Error running tool in docker: {e}"


def get_sandbox() -> DockerSandbox:
    return DockerSandbox()
