import json
import logging
from typing import Any, Callable, Awaitable
from graph.utils.llm import make_llm
from core.config import DEFAULT_MODEL_KEY

logger = logging.getLogger(__name__)

class MCPService:
    """Channel-agnostic service for multi-turn Model Context Protocol (MCP) tool orchestration."""

    def format_mcp_tools_for_openai(self, mcp_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", f"Tool: {tool['name']}"),
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}})
                }
            }
            for tool in mcp_tools
        ]

    async def run_mcp_loop(
        self,
        user_message: str,
        mcp_tools: list[dict[str, Any]],
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[str]],
        stream_callback: Callable[[str], Awaitable[None]] | None = None,
        model_key: str = DEFAULT_MODEL_KEY,
        max_turns: int = 10,
    ) -> str:
        if not mcp_tools:
            return ""

        openai_tools = self.format_mcp_tools_for_openai(mcp_tools)
        client = make_llm(model_key, temperature=0.3)
        model_with_tools = client.bind_tools(openai_tools, tool_choice="auto")

        messages = [
            {"role": "system", "content": "You are Marcus Reyes, a life coach with Stripe MCP tools access."},
            {"role": "user", "content": user_message}
        ]

        final_response = ""
        for _ in range(max_turns):
            response = await model_with_tools.ainvoke(messages)
            tool_calls = getattr(response, "tool_calls", None)

            if not tool_calls:
                final_response = response.content
                if stream_callback and final_response:
                    await stream_callback(final_response)
                return final_response

            for tool_call in tool_calls:
                sanitized_args = {
                    k: v for k, v in tool_call["args"].items() 
                    if v is not None and str(v).lower() not in ("null", "none", "")
                }
                result = await tool_executor(tool_call["name"], sanitized_args)
                messages.append({"role": "assistant", "content": "", "tool_calls": [tool_call]})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", tool_call["name"]),
                    "content": str(result)[:3000]
                })

        return final_response

mcp_service = MCPService()