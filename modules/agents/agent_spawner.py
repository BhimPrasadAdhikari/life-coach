"""
modules/agents/agent_spawner.py — Re-export AgentSpawner from modules.self_evolution.agent_spawner
"""
from modules.self_evolution.agent_spawner import AgentSpawner, get_agent_spawner

__all__ = ["AgentSpawner", "get_agent_spawner"]
