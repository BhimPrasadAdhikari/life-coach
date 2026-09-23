"""
scripts/test_providers.py — Tests live API connectivity for Groq models.
"""
import sys
import time
import asyncio
from dotenv import load_dotenv

load_dotenv()

from graph.utils.llm import make_llm, get_chat_model


async def test_groq_model(model_key: str):
    print(f"Testing Groq API ({model_key})...")
    t0 = time.perf_counter()
    try:
        llm = get_chat_model(model_key, temperature=0.0)
        res = await llm.ainvoke("Respond with 'Groq OK' and nothing else.")
        t1 = time.perf_counter()
        content = getattr(res, "content", str(res)).strip()
        print(f"[SUCCESS] Groq ({model_key})! [{t1-t0:.3f}s] Response: '{content}'")
        return True, t1 - t0, content
    except Exception as exc:
        t1 = time.perf_counter()
        print(f"[ERROR] Groq ({model_key}) failed! [{t1-t0:.3f}s] Error: {exc}")
        return False, t1 - t0, str(exc)


async def main():
    print("=" * 65)
    print("       LIVE LLM PROVIDER CONNECTIVITY & ACCESSIBILITY TEST")
    print("=" * 65)
    
    groq31_ok, _, _ = await test_groq_model("groq-llama3.1")
    print("-" * 65)
    groq33_ok, _, _ = await test_groq_model("groq-llama3.3")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
