import sys
import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Add project root to python path
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

load_dotenv()

from langsmith import Client
from langchain_core.messages import HumanMessage
from langsmith.evaluation import evaluate
from graph.graph import create_graph

# Initialize LangSmith client
client = Client()

dataset_name = "whatsapp_agent_eval_dataset"

def setup_dataset():
    if not client.has_dataset(dataset_name=dataset_name):
        dataset = client.create_dataset(
            dataset_name=dataset_name,
            description="Sample evaluation dataset for the whatsapp_agent."
        )
        
        inputs = [
            "Hi there! How are you doing today?",
            "I'm feeling a bit overwhelmed with my work and need some guidance.",
            "Can you help me plan my tasks for tomorrow?"
        ]
        
        for text in inputs:
            client.create_example(
                inputs={"input": text},
                outputs={"expected_output": "A helpful, empathetic and structured response."},
                dataset_id=dataset.id,
            )
            
        print(f"Created dataset: {dataset_name} with {len(inputs)} examples.")
    else:
        print(f"Dataset '{dataset_name}' already exists.")

# Define the target function to evaluate
async def predict(inputs: dict) -> dict:
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    import uuid
    
    user_input = inputs["input"]
    thread_id = str(uuid.uuid4())
    
    # Use actual checkpoint.db memory pattern from app.py
    async with AsyncSqliteSaver.from_conn_string("checkpoint.db") as saver:
        graph = create_graph().compile(checkpointer=saver)
        from core.config import DEFAULT_MODEL_KEY
        output_state = await graph.ainvoke(
            {"messages": [HumanMessage(content=user_input)]},
            {"configurable": {"thread_id": thread_id, "model_key": DEFAULT_MODEL_KEY}}
        )
        
    final_message = output_state["messages"][-1].content
    return {"output": final_message}

# Define an LLM evaluator using your agent's LLM tools
async def llm_evaluator(run, example):
    from graph.utils.llm import make_llm
    
    if example and example.inputs and "input" in example.inputs:
        input_text = example.inputs["input"]
    elif run and run.inputs and "input" in run.inputs:
        input_text = run.inputs["input"]
    else:
        input_text = str(example.inputs) if example else ""

    if run and run.outputs and "output" in run.outputs:
        output_text = run.outputs["output"]
    elif run and hasattr(run, "error") and run.error:
        output_text = f"Error during execution: {run.error}"
    else:
        output_text = str(run.outputs) if run and run.outputs else "None"
    
    # We use a reliable fast model for evaluation
    from core.config import DEFAULT_MODEL_KEY
    llm = make_llm(DEFAULT_MODEL_KEY, temperature=0)
    
    # LLM-as-a-judge prompt
    prompt = f"""
You are an expert evaluator assessing an AI coaching assistant's response.
Evaluate the helpfulness and empathy of the following agent response to the user's input.
Choose EXACTLY ONE categorical score from the list below:
- Very Unhelpful
- Unhelpful
- Neutral
- Helpful
- Very Helpful

Output ONLY the exact category name and absolutely nothing else.

User Input: {input_text}
Agent Response: {output_text}
"""
    try:
        response = await llm.ainvoke(prompt)
        score = response.content.strip()
        # Validate that the score is one of the choices
        valid_scores = ["Very Unhelpful", "Unhelpful", "Neutral", "Helpful", "Very Helpful"]
        if score not in valid_scores:
            # Try to match if it's partially correct
            for valid in valid_scores:
                if valid.lower() in score.lower():
                    score = valid
                    break
            else:
                score = "Neutral" # Fallback
    except Exception as e:
        print(f"Eval error: {e}")
        score = "Error" # Error fallback
        
    return {"key": "helpfulness", "score": score}

async def main():
    if not os.getenv("LANGCHAIN_API_KEY"):
        print("ERROR: LANGCHAIN_API_KEY is not set. Please set it in your .env file.")
        sys.exit(1)
        
    print("Setting up LangSmith dataset...")
    setup_dataset()
    
    print(f"\nRunning evaluation on dataset '{dataset_name}'...")
    from langsmith.evaluation import aevaluate
    results = await aevaluate(
        predict,
        data=dataset_name,
        evaluators=[llm_evaluator],
        experiment_prefix="whatsapp-agent-baseline",
        max_concurrency=2, # Limiting concurrency to avoid rate limits
    )
    
    print("\nEvaluation complete! View your results at https://smith.langchain.com/")

if __name__ == "__main__":
    asyncio.run(main())
