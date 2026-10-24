"""Trusted container entry point. Generated Python is executed only here."""

import asyncio
import sys
from pathlib import Path

# -I excludes the working directory; add only this trusted, image-owned package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from program_sdk.client import SDK  # noqa: E402
from program_sdk.policy import VERSION, validate_source  # noqa: E402
from program_sdk.protocol import encode, read  # noqa: E402


async def run(packet):
    limit = packet["frame_limit"]
    tree = validate_source(packet["source"], set(packet["jobs"]), packet["max_source_chars"])
    namespace = {"__builtins__": {}}
    exec(compile(tree, "<saved-p1-program>", "exec"), namespace)  # container only
    sys.stdout.buffer.write(encode({"type": "ready", "policy": VERSION}, limit))
    sys.stdout.buffer.flush()
    sdk = SDK(sys.stdin.buffer, sys.stdout.buffer, limit)
    try:
        result = await namespace["run"](sdk, packet["inputs"])
    except Exception as exc:
        await sdk.finish({"type": "error", "message": f"{type(exc).__name__}: {exc}"[:2000]})
        return 1
    await sdk.finish({"type": "result", "value": result})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run(read(sys.stdin.buffer))))
    except Exception as exc:
        print(f"Runner stopped: {type(exc).__name__}: {str(exc)[:2000]}", file=sys.stderr)
        raise SystemExit(1) from None
