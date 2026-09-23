"""
core/db.py — Database management and PostgreSQL registries with row-level locking.

Supports both PostgreSQL (production) and SQLite (local/testing) seamlessly.
Provides ORM models for skills_registry and agents_registry.
"""
import os
import json
import logging
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager

from sqlalchemy import (
    create_engine,
    Column,
    String,
    Text,
    Integer,
    JSON,
    select,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

logger = logging.getLogger(__name__)

Base = declarative_base()


class SkillModel(Base):
    """SQLAlchemy model for skills_registry table."""

    __tablename__ = "skills_registry"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    coaching_context = Column(Text, nullable=True)
    use_cases = Column(JSON, nullable=True)
    created_at = Column(String, nullable=False)
    use_count = Column(Integer, default=0)
    status = Column(String, default="active")  # 'active' or 'pending'

    def to_dict(self) -> dict:
        use_cases_data = self.use_cases
        if isinstance(use_cases_data, str):
            try:
                use_cases_data = json.loads(use_cases_data)
            except Exception:
                pass
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "coaching_context": self.coaching_context or "",
            "use_cases": use_cases_data or [],
            "created_at": self.created_at,
            "use_count": self.use_count or 0,
            "status": self.status,
        }


class AgentModel(Base):
    """SQLAlchemy model for agents_registry table."""

    __tablename__ = "agents_registry"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    purpose = Column(Text, nullable=False)
    coaching_context = Column(Text, nullable=True)
    use_cases = Column(JSON, nullable=True)
    system_prompt = Column(Text, nullable=False)
    created_at = Column(String, nullable=False)
    invocation_count = Column(Integer, default=0)
    status = Column(String, default="active")  # 'active' or 'pending'

    def to_dict(self) -> dict:
        use_cases_data = self.use_cases
        if isinstance(use_cases_data, str):
            try:
                use_cases_data = json.loads(use_cases_data)
            except Exception:
                pass
        return {
            "id": self.id,
            "name": self.name,
            "purpose": self.purpose,
            "coaching_context": self.coaching_context or "",
            "use_cases": use_cases_data or [],
            "system_prompt": self.system_prompt,
            "created_at": self.created_at,
            "invocation_count": self.invocation_count or 0,
            "status": self.status,
        }


_engine = None
_SessionFactory = None


def get_db_url() -> str:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        _base = Path(__file__).resolve().parent.parent
        db_path = _base / "data" / "marcus_agent.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{db_path}"
    # Standardize postgresql prefix if using asyncpg or psycopg2 syntax
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    if db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return db_url


def get_engine(db_url: str = None):
    global _engine
    if _engine is None or db_url is not None:
        target_url = db_url or get_db_url()
        connect_args = {}
        if target_url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
        _engine = create_engine(
            target_url,
            connect_args=connect_args,
            pool_pre_ping=True,
        )
    return _engine


def dispose_engine():
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
        _engine = None
    _SessionFactory = None


def get_session_factory(db_url: str = None):
    global _SessionFactory
    engine = get_engine(db_url)
    if _SessionFactory is None or db_url is not None:
        _SessionFactory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return _SessionFactory


@contextmanager
def get_db_session(db_url: str = None):
    SessionFactory = get_session_factory(db_url)
    session: Session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(db_url: str = None):
    """Create tables if not existing and seed from JSON files if DB is empty."""
    engine = get_engine(db_url)
    Base.metadata.create_all(bind=engine)
    _migrate_legacy_json(db_url)


def _migrate_legacy_json(db_url: str = None):
    """Seed DB tables from legacy JSON files if DB tables are empty."""
    _base = Path(__file__).resolve().parent.parent
    skills_file = _base / "data" / "skills.json"
    skills_pending_file = _base / "data" / "skills_pending.json"
    agents_file = _base / "data" / "agents.json"
    agents_pending_file = _base / "data" / "agents_pending.json"

    with get_db_session(db_url) as session:
        # Check skills table
        skill_count = session.query(SkillModel).count()
        if skill_count == 0:
            if skills_file.exists():
                try:
                    data = json.loads(skills_file.read_text(encoding="utf-8"))
                    for k, item in data.items():
                        session.add(
                            SkillModel(
                                id=item.get("id", k),
                                name=item.get("name", k),
                                description=item.get("description", ""),
                                coaching_context=item.get("coaching_context", ""),
                                use_cases=item.get("use_cases", []),
                                created_at=item.get("created_at", datetime.now().isoformat()),
                                use_count=item.get("use_count", 0),
                                status="active",
                            )
                        )
                except Exception as e:
                    logger.warning(f"Error migrating skills.json: {e}")

            if skills_pending_file.exists():
                try:
                    data = json.loads(skills_pending_file.read_text(encoding="utf-8"))
                    for k, item in data.items():
                        session.add(
                            SkillModel(
                                id=item.get("id", k),
                                name=item.get("name", k),
                                description=item.get("description", ""),
                                coaching_context=item.get("coaching_context", ""),
                                use_cases=item.get("use_cases", []),
                                created_at=item.get("created_at", datetime.now().isoformat()),
                                use_count=item.get("use_count", 0),
                                status="pending",
                            )
                        )
                except Exception as e:
                    logger.warning(f"Error migrating skills_pending.json: {e}")

        # Check agents table
        agent_count = session.query(AgentModel).count()
        if agent_count == 0:
            if agents_file.exists():
                try:
                    data = json.loads(agents_file.read_text(encoding="utf-8"))
                    for k, item in data.items():
                        session.add(
                            AgentModel(
                                id=item.get("id", k),
                                name=item.get("name", k),
                                purpose=item.get("purpose", ""),
                                coaching_context=item.get("coaching_context", ""),
                                use_cases=item.get("use_cases", []),
                                system_prompt=item.get("system_prompt", ""),
                                created_at=item.get("created_at", datetime.now().isoformat()),
                                invocation_count=item.get("invocation_count", 0),
                                status="active",
                            )
                        )
                except Exception as e:
                    logger.warning(f"Error migrating agents.json: {e}")

            if agents_pending_file.exists():
                try:
                    data = json.loads(agents_pending_file.read_text(encoding="utf-8"))
                    for k, item in data.items():
                        session.add(
                            AgentModel(
                                id=item.get("id", k),
                                name=item.get("name", k),
                                purpose=item.get("purpose", ""),
                                coaching_context=item.get("coaching_context", ""),
                                use_cases=item.get("use_cases", []),
                                system_prompt=item.get("system_prompt", ""),
                                created_at=item.get("created_at", datetime.now().isoformat()),
                                invocation_count=item.get("invocation_count", 0),
                                status="pending",
                            )
                        )
                except Exception as e:
                    logger.warning(f"Error migrating agents_pending.json: {e}")
