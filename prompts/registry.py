"""
prompts/registry.py — Versioned YAML prompt registry with hot-reloading support.
"""
from __future__ import annotations
import os
import re
import logging
from pathlib import Path
from typing import Any, Dict
import yaml

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent


class PromptRegistry:
    """
    Singleton Prompt Registry loading versioned YAML prompt definitions.
    Supports hot-reloading and dynamic template rendering.
    """

    _instance: PromptRegistry | None = None

    def __new__(cls) -> PromptRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._prompts = {}
            cls._instance.reload_prompts()
        return cls._instance

    def reload_prompts(self) -> None:
        """Scan prompts directory and reload all YAML templates."""
        self._prompts.clear()
        if not PROMPTS_DIR.exists():
            logger.warning(f"Prompts directory {PROMPTS_DIR} does not exist.")
            return

        for version_dir in PROMPTS_DIR.iterdir():
            if version_dir.is_dir() and not version_dir.name.startswith((".", "_")):
                version = version_dir.name  # e.g., 'v1'
                self._prompts[version] = {}

                for yaml_file in version_dir.glob("*.yaml"):
                    try:
                        with open(yaml_file, "r", encoding="utf-8") as f:
                            data = yaml.safe_load(f)
                            if isinstance(data, dict):
                                prompt_name = data.get("name", yaml_file.stem)
                                self._prompts[version][prompt_name] = data
                    except Exception as exc:
                        logger.error(f"Failed loading prompt YAML {yaml_file}: {exc}")

        logger.info(f"Loaded prompts for versions: {list(self._prompts.keys())}")

    def get_prompt(self, name: str, version: str = "v1") -> Dict[str, Any]:
        """Retrieve raw prompt definition dictionary."""
        version_prompts = self._prompts.get(version, {})
        if name in version_prompts:
            return version_prompts[name]
        
        # Fallback to v1 if version not found
        if version != "v1" and "v1" in self._prompts and name in self._prompts["v1"]:
            return self._prompts["v1"][name]

        raise KeyError(f"Prompt '{name}' not found for version '{version}'. Available: {list(version_prompts.keys())}")

    def render_prompt(self, name: str, version: str = "v1", **kwargs: Any) -> str:
        """
        Render template string for prompt name with provided keyword arguments.
        Handles Jinja2-style tags like {% if ... %}, {{ var }}, etc.
        """
        prompt_data = self.get_prompt(name, version)
        template_str = prompt_data.get("template", "")

        context = dict(prompt_data)
        context.update(kwargs)

        try:
            from jinja2 import Template
            template = Template(template_str)
            return template.render(**context).strip()
        except ImportError:
            # Basic fallback formatting if jinja2 is not available
            res = template_str
            for key, val in context.items():
                res = res.replace(f"{{{{ {key} }}}}", str(val)).replace(f"{{{key}}}", str(val))
            # Clean unused tags
            res = re.sub(r"\{\{.*?\}\}", "", res)
            res = re.sub(r"\{% if .*? %\}[\s\S]*?\{% endif %\}", "", res)
            return res.strip()



def get_prompt_registry() -> PromptRegistry:
    """Returns singleton instance of PromptRegistry."""
    return PromptRegistry()
