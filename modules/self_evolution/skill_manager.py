import threading
import logging
from datetime import datetime

from core.db import init_db, get_db_session, SkillModel
from core.cache import get_redis_cache

logger = logging.getLogger(__name__)


class SkillManager:
    """
    Manages Marcus's growing library of coaching skills and frameworks.
    Skills persist in PostgreSQL (skills_registry) with row-level locking.
    Thread-safe singleton with Redis context caching.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        init_db()
        self.cache = get_redis_cache()
        self._initialized = True

    # ------------------------------------------------------------------
    # Core operations backed by PostgreSQL / SQLAlchemy
    # ------------------------------------------------------------------

    def acquire_skill(
        self,
        name: str,
        description: str,
        coaching_context: str,
        use_cases: list,
    ) -> dict:
        """
        Persist a new coaching skill/framework to database as 'pending'.
        Returns the stored skill dict.
        """
        skill_id = name.lower().replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "")
        now_str = datetime.now().isoformat()

        with get_db_session() as session:
            existing = session.query(SkillModel).filter(SkillModel.id == skill_id).with_for_update().first()
            if existing:
                existing.name = name
                existing.description = description
                existing.coaching_context = coaching_context
                existing.use_cases = use_cases
                existing.status = "pending"
                skill_obj = existing
            else:
                skill_obj = SkillModel(
                    id=skill_id,
                    name=name,
                    description=description,
                    coaching_context=coaching_context,
                    use_cases=use_cases,
                    created_at=now_str,
                    use_count=0,
                    status="pending",
                )
                session.add(skill_obj)
            session.flush()
            result = skill_obj.to_dict()

        logger.info(f"SkillManager: acquired pending skill '{name}' (id={skill_id})")
        return result

    def list_pending_skills(self) -> list:
        with get_db_session() as session:
            records = session.query(SkillModel).filter(SkillModel.status == "pending").all()
            return [r.to_dict() for r in records]

    def approve_skill(self, skill_id: str) -> dict:
        with get_db_session() as session:
            skill_obj = (
                session.query(SkillModel)
                .filter(SkillModel.id == skill_id, SkillModel.status == "pending")
                .with_for_update()
                .first()
            )
            if not skill_obj:
                raise KeyError(f"Pending skill '{skill_id}' not found")

            skill_obj.status = "active"
            session.flush()
            result = skill_obj.to_dict()

        self.cache.invalidate_skills_cache()
        logger.info(f"SkillManager: approved skill '{skill_id}'")
        return result

    def increment_use(self, skill_id: str) -> None:
        with get_db_session() as session:
            skill_obj = (
                session.query(SkillModel)
                .filter(SkillModel.id == skill_id)
                .with_for_update()
                .first()
            )
            if skill_obj:
                skill_obj.use_count = (skill_obj.use_count or 0) + 1

    def list_skills(self) -> list:
        with get_db_session() as session:
            records = session.query(SkillModel).filter(SkillModel.status == "active").all()
            return [r.to_dict() for r in records]

    # ------------------------------------------------------------------
    # Prompt injection
    # ------------------------------------------------------------------

    def get_active_skills_context(self, user_id: str = "default_user") -> str:
        """
        Return a formatted string ready to be appended to Marcus's system prompt.
        Uses Redis cache (TTL: 5 min). Returns empty string when no active skills.
        """
        cached = self.cache.get_skills_context(user_id)
        if cached is not None:
            return cached

        skills = self.list_skills()
        if not skills:
            context = ""
        else:
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

            for skill in skills:
                lines.append(f"### {skill['name']}")
                lines.append(skill["description"])
                if skill.get("coaching_context"):
                    lines.append(f"**When to apply:** {skill['coaching_context']}")
                if skill.get("use_cases"):
                    lines.append(f"**Use cases:** {', '.join(skill['use_cases'])}")
                lines.append("")

            context = "\n".join(lines)

        self.cache.set_skills_context(user_id, context, ttl=300)
        return context

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
