"""
modules/skills/skill_manager.py — Re-export SkillManager from modules.self_evolution.skill_manager
"""
from modules.self_evolution.skill_manager import SkillManager, get_skill_manager

__all__ = ["SkillManager", "get_skill_manager"]
