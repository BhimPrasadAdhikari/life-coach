"""Centralized configuration for model keys, thresholds, and fallbacks.

Read settings from environment with sensible defaults. Import this module
wherever model selection or similarity thresholds are required.
"""
import os

# Model keys (provider-agnostic keys used by graph.utils.llm.make_llm)
DEFAULT_MODEL_KEY = os.getenv("DEFAULT_MODEL_KEY", "groq-llama3.3")
FALLBACK_MODEL_KEY = os.getenv("FALLBACK_MODEL_KEY", "groq-llama3.1")

# Specialized model keys for certain tasks
ROUTER_MODEL_KEY = os.getenv("ROUTER_MODEL_KEY", "groq-llama3.1")
EVOLVE_CHECK_MODEL_KEY = os.getenv("EVOLVE_CHECK_MODEL_KEY", "groq-llama3.1")
MEMORY_ANALYSIS_MODEL_KEY = os.getenv("MEMORY_ANALYSIS_MODEL_KEY", DEFAULT_MODEL_KEY)

# Temperatures for different usages
DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "0.7"))
EVALUATION_TEMPERATURE = float(os.getenv("EVALUATION_TEMPERATURE", "0.0"))

# Memory vector similarity threshold (0-1)
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.9"))

# Production state and resilience settings
CHECKPOINT_DATABASE_URL = os.getenv("CHECKPOINT_DATABASE_URL", os.getenv("DATABASE_URL", ""))
LLM_RETRY_ATTEMPTS = int(os.getenv("LLM_RETRY_ATTEMPTS", "3"))
LLM_RETRY_MIN_SECONDS = float(os.getenv("LLM_RETRY_MIN_SECONDS", "1"))
LLM_RETRY_MAX_SECONDS = float(os.getenv("LLM_RETRY_MAX_SECONDS", "8"))
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
IDEMPOTENCY_TTL_SECONDS = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "86400"))
QDRANT_MEMORY_COLLECTION = os.getenv("QDRANT_MEMORY_COLLECTION", "marcus_memories")

# WhatsApp Webhook Integration Settings
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "MY_VERIFY_TOKEN")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
WHATSAPP_PROVIDER = os.getenv("WHATSAPP_PROVIDER", "meta").lower()
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v20.0")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "")
WHATSAPP_HTTP_TIMEOUT = float(os.getenv("WHATSAPP_HTTP_TIMEOUT", "15"))

