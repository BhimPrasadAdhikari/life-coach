"""
Skill Manager — lets Marcus acquire and persist new coaching frameworks/approaches.
Skills are stored as JSON in data/skills.json and injected into Marcus's system
prompt on every conversation turn.
"""
import json
import logging
from pathlib import Path
from datetime import datetime

_BASE = Path(__file__).resolve().parent.parent.parent
SKILLS_FILE = _BASE / "data" / "skills.json"
SKILLS_PENDING_FILE = _BASE / "data" / "skills_pending.json"

from utils.file_lock import read_json_atomic, write_json_atomic

logger = logging.getLogger(__name__)


class SkillManager:
    """
    Manages Marcus's growing library of coaching skills and frameworks.
    Skills persist between sessions and automatically augment his system prompt.
    """

    def __init__(self):
        SKILLS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        data = read_json_atomic(str(SKILLS_FILE))
        return data or {}

    def _save(self, skills: dict) -> None:
        write_json_atomic(str(SKILLS_FILE), skills)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def acquire_skill(
        self,
        name: str,
        description: str,
        coaching_context: str,
        use_cases: list,
    ) -> dict:
        """
        Persist a new coaching skill/framework to disk.
        Returns the stored skill dict.
        """
        # Persist as a pending skill for human approval
        pending = read_json_atomic(str(SKILLS_PENDING_FILE)) or {}
        skill_id = name.lower().replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "")

        skill = {
            "id": skill_id,
            "name": name,
            "description": description,
            "coaching_context": coaching_context,
            "use_cases": use_cases,
            "created_at": datetime.now().isoformat(),
            "use_count": 0,
            "status": "pending",
        }
        pending[skill_id] = skill
        write_json_atomic(str(SKILLS_PENDING_FILE), pending)

        logger.info(f"SkillManager: acquired pending skill '{name}'")
        return skill

    def list_pending_skills(self) -> list:
        return list((read_json_atomic(str(SKILLS_PENDING_FILE)) or {}).values())

    def approve_skill(self, skill_id: str) -> dict:
        pending = read_json_atomic(str(SKILLS_PENDING_FILE)) or {}
        if skill_id not in pending:
            raise KeyError(f"Pending skill '{skill_id}' not found")
        skill = pending.pop(skill_id)
        skill.pop("status", None)
        skills = self._load()
        skills[skill_id] = skill
        self._save(skills)
        write_json_atomic(str(SKILLS_PENDING_FILE), pending)
        logger.info(f"SkillManager: approved skill '{skill_id}'")
        return skill

    def increment_use(self, skill_id: str) -> None:
        skills = self._load()
        if skill_id in skills:
            skills[skill_id]["use_count"] += 1
            self._save(skills)

    def list_skills(self) -> list:
        return list(self._load().values())

    # ------------------------------------------------------------------
    # Prompt injection
    # ------------------------------------------------------------------

    def get_active_skills_context(self) -> str:
        """
        Return a formatted string ready to be appended to Marcus's system prompt.
        Returns empty string when no skills have been acquired yet.
        """
        skills = self._load()
        if not skills:
            return ""

        lines = [
            "",
            "---",
            "",
            "## COACHING SKILLS & FRAMEWORKS YOU HAVE ACQUIRED",
            "",
            "These are approaches you have intentionally added to your practice. "
            "Draw on them when they fit — don't force them. Integrate naturally.",
            "",
        ]

        for skill in skills.values():
            lines.append(f"### {skill['name']}")
            lines.append(skill["description"])
            if skill.get("coaching_context"):
                lines.append(f"**When to apply:** {skill['coaching_context']}")
            if skill.get("use_cases"):
                lines.append(f"**Use cases:** {', '.join(skill['use_cases'])}")
            lines.append("")

        return "\n".join(lines)

    def get_skill_summary(self) -> str:
        """Human-readable list for Marcus to reference in conversation."""
        skills = self.list_skills()
        if not skills:
            return "No additional frameworks acquired yet."
        lines = ["Frameworks and approaches Marcus has added to his practice:"]
        for s in skills:
            lines.append(f"  • {s['name']} — {s['description']}")
        return "\n".join(lines)


def get_skill_manager() -> SkillManager:
    return SkillManager()
