"""CSV planning, execution, evaluation, and local model discovery commands."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .orchestration.model_clients import discover_codex_models


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    # Forward the complete tail so each module owns its arguments and help text.
    if arguments and arguments[0] == "analysis":
        from .orchestration.cli import main as analysis_main

        return analysis_main(arguments[1:])
    if arguments and arguments[0] == "eval":
        from .evaluation.cli import main as evaluation_main

        return evaluation_main(arguments[1:])

    parser = argparse.ArgumentParser(description="CSV data-analysis research harness")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("analysis", help="Plan, execute, and inspect CSV runs")
    commands.add_parser("eval", help="Grade CSV runs and compare D1/D2/P1/P2 development batches")
    commands.add_parser("models", help="List models available through the local Codex CLI")
    parser.parse_args(arguments)
    try:
        result = asyncio.run(discover_codex_models(Path.cwd() / "runs" / "model_discovery"))
    except (ValueError, OSError, TimeoutError) as exc:
        print(json.dumps({"error": getattr(exc, "code", type(exc).__name__), "message": str(exc)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
