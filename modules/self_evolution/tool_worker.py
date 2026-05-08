#!/usr/bin/env python3
"""Simple worker to run a tool function in a separate process.

Usage: python tool_worker.py /absolute/path/to/tool_file.py function_name

The worker reads stdin (which may contain JSON or plain text) and passes it
as the single argument to the tool function. The function's return value is
printed to stdout. On error the worker writes a traceback to stderr and exits
with non-zero status.
"""
import sys
import json
import traceback
import importlib.util


def main():
    if len(sys.argv) < 3:
        print("Usage: tool_worker.py <tool_file> <function_name>", file=sys.stderr)
        sys.exit(2)

    tool_file = sys.argv[1]
    func_name = sys.argv[2]

    try:
        raw = sys.stdin.read()
        # Try to parse JSON, otherwise pass the raw string
        try:
            payload = json.loads(raw) if raw else None
        except Exception:
            payload = raw

        spec = importlib.util.spec_from_file_location("tool_module", tool_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, func_name):
            print(f"ERROR: function '{func_name}' not found in {tool_file}", file=sys.stderr)
            sys.exit(3)

        func = getattr(module, func_name)

        # Call function with payload if provided, otherwise without args
        if payload is None:
            result = func()
        else:
            result = func(payload)

        # Print JSON for structured outputs, otherwise string
        if isinstance(result, (dict, list)):
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(str(result))

    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
