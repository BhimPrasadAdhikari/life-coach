"""Centralized configuration for model keys, thresholds, and fallbacks.

Read settings from environment with sensible defaults. Import this module
wherever model selection or similarity thresholds are required.
"""
import os

# Model keys (provider-agnostic keys used by graph.utils.llm.make_llm)
DEFAULT_MODEL_KEY = os.getenv("DEFAULT_MODEL_KEY", "groq-llama3.3")
FALLBACK_MODEL_KEY = os.getenv("FALLBACK_MODEL_KEY", "gemini-flash")

# Specialized model keys for certain tasks
EVOLVE_CHECK_MODEL_KEY = os.getenv("EVOLVE_CHECK_MODEL_KEY", "groq-llama3.1")
MEMORY_ANALYSIS_MODEL_KEY = os.getenv("MEMORY_ANALYSIS_MODEL_KEY", DEFAULT_MODEL_KEY)

# Temperatures for different usages
DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "0.7"))
EVALUATION_TEMPERATURE = float(os.getenv("EVALUATION_TEMPERATURE", "0.0"))

# Memory vector similarity threshold (0-1)
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.9"))
