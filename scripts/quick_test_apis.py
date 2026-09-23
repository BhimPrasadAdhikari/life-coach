"""
scripts/quick_test_apis.py — Fast API tester for Groq models with timeouts.
"""
import asyncio
import time
from dotenv import load_dotenv

load_dotenv()

from graph.utils.llm import get_chat_model, MODELS


async def test_single_model(model_key: str):
    print(f"Testing model_key='{model_key}'...")
    t0 = time.perf_counter()
    try:
        model = get_chat_model(model_key, temperature=0.0)
        res = await asyncio.wait_for(model.ainvoke("Say hello in 3 words."), timeout=10.0)
        t1 = time.perf_counter()
        content = getattr(res, "content", str(res)).strip()
        print(f"[SUCCESS] {model_key} -> Response ({t1-t0:.2f}s): {content}")
        return True
    except asyncio.TimeoutError:
        print(f"[TIMEOUT] {model_key} timed out after 10 seconds.")
        return False
    except Exception as exc:
        t1 = time.perf_counter()
        print(f"[FAILED] {model_key} failed ({t1-t0:.2f}s): {exc}")
        return False


async def main():
    print("=" * 60)
    print("TESTING ALL CONFIGURED LLM PROVIDERS")
    print("=" * 60)
    
    for key in ["groq-llama3.1", "groq-llama3.3", "groq-qwen27b"]:
        await test_single_model(key)
        print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())
