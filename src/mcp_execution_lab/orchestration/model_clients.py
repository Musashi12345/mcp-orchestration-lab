"""Codex CLI route and external-router protocol. Codex owns authentication."""

import asyncio
import json
import shutil

from mcp_execution_lab import __version__

from .models import OrchestrationError


def structured_schema(model):
    """Structured output requires every property, including nullable optionals."""

    def normalize(value):
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {key: normalize(item) for key, item in value.items() if key != "default"}
        if result.get("type") == "object" and "properties" in result:
            result["required"] = list(result["properties"])
            result["additionalProperties"] = False
        return result

    return normalize(model.model_json_schema())


async def bounded_process(command, *, directory, payload, timeout, stdout_limit=4194304):
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=directory,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def bounded_read(stream, limit):
        collected = bytearray()
        while chunk := await stream.read(8192):
            collected.extend(chunk)
            if len(collected) > limit:
                raise OrchestrationError(
                    "MODEL_RESPONSE_SIZE", "Planner output exceeded its byte limit."
                )
        return bytes(collected)

    try:
        async with asyncio.timeout(timeout):
            process.stdin.write(payload.encode())
            await process.stdin.drain()
            process.stdin.close()
            stdout, stderr = await asyncio.gather(
                bounded_read(process.stdout, stdout_limit),
                bounded_read(process.stderr, 65536),
            )
            await process.wait()
            return process.returncode, stdout.decode(), stderr.decode(errors="replace")
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


class CommandPlanner:
    """A local router receives orchestration.v1 JSON and emits one result JSON."""

    is_model = True
    provider = "command"

    def __init__(self, config):
        self.config = config

    async def generate(self, request, directory):
        if not self.config.command:
            raise OrchestrationError(
                "PLANNER_CONFIG", "External router requires an explicit argv command."
            )
        code, stdout, stderr = await bounded_process(
            self.config.command,
            directory=directory,
            payload=json.dumps(request),
            timeout=self.config.timeout_seconds,
        )
        (directory / "router.stderr.txt").write_text(stderr, encoding="utf-8")
        if code:
            raise OrchestrationError(
                "MODEL_SERVICE_ERROR", f"External router exited with status {code}."
            )
        result = json.loads(stdout)
        if not isinstance(result, dict) or not {"content", "usage", "request_id"} <= result.keys():
            raise OrchestrationError(
                "MODEL_RESULT_SCHEMA", "Router result lacks content, usage or request_id."
            )
        return result | {"provider": self.provider, "cost_usd": result.get("cost_usd")}


class CodexPlanner:
    """Fresh ephemeral Codex invocation for every initial/replanning request."""

    is_model = True
    provider = "codex"
    disabled = [
        "shell_tool",
        "unified_exec",
        "code_mode_host",
        "apps",
        "plugins",
        "multi_agent",
        "multi_agent_v2",
        "browser_use",
        "browser_use_external",
        "computer_use",
        "view_image",
        "image_generation",
        "workspace_dependencies",
        "hooks",
        "skill_search",
        "goals",
    ]

    def __init__(self, config):
        self.config = config
        self.executable = shutil.which("codex")

    async def generate(self, request, directory):
        if not self.executable or not self.config.model_id:
            raise OrchestrationError(
                "PLANNER_CONFIG", "Codex requires an installed CLI and an exact model_id."
            )
        schema = request.get("response_schema")
        if not isinstance(schema, dict) or not schema:
            raise OrchestrationError("MODEL_REQUEST_SCHEMA", "A response schema is required.")
        status = await asyncio.create_subprocess_exec(
            self.executable,
            "login",
            "status",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(status.communicate(), timeout=10)
        if status.returncode or "chatgpt" not in (out + err).decode(errors="replace").lower():
            raise OrchestrationError(
                "CODEX_LOGIN_REQUIRED", "Sign in to the CLI with ChatGPT using codex login."
            )
        schema_path = directory / "response.schema.json"
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
        command = [
            self.executable,
            "--ask-for-approval",
            "never",
            "exec",
            "--ignore-user-config",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--model",
            self.config.model_id,
            "--json",
            "--color",
            "never",
            "--output-schema",
            str(schema_path.resolve()),
            "-c",
            'web_search="disabled"',
            "-c",
            "project_doc_max_bytes=0",
            "-c",
            "model_reasoning_effort=" + json.dumps(self.config.reasoning_effort),
        ]
        for flag in self.disabled:
            command.extend(["--disable", flag])
        command.append("-")
        code, stdout, stderr = await bounded_process(
            command,
            directory=directory,
            payload=json.dumps(request),
            timeout=self.config.timeout_seconds,
        )
        (directory / "codex.events.jsonl").write_text(stdout, encoding="utf-8")
        (directory / "codex.stderr.txt").write_text(stderr, encoding="utf-8")
        events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        content = None
        usage = None
        thread_id = None
        violation = False
        for event in events:
            if event.get("type") == "thread.started":
                thread_id = event.get("thread_id")
            item = event.get("item", {})
            if event.get("type") == "item.completed" and item.get("type") == "agent_message":
                content = item["text"]
            if item.get("type") not in (None, "agent_message", "reasoning", "error"):
                violation = True
            if event.get("type") == "turn.completed":
                usage = event.get("usage")
        if usage is None:
            raise OrchestrationError(
                "MODEL_SERVICE_ERROR",
                f"Codex request did not complete (exit {code}); see retained call logs.",
            )
        failure = None
        if content is not None:
            try:
                content = json.loads(content)
            except (ValueError, TypeError):
                content = None
        if violation:
            failure = {
                "code": "PLANNER_TOOL_VIOLATION",
                "message": "Codex attempted tool activity outside the planning contract.",
            }
        elif code or content is None:
            failure = {
                "code": "MODEL_SERVICE_ERROR",
                "message": f"Codex did not complete (exit {code}); see retained call logs.",
            }
        return {
            "content": content,
            "usage": usage,
            "request_id": thread_id,
            "provider": "codex",
            "model_id": self.config.model_id,
            "cost_usd": None,
            "cost_basis": "ChatGPT subscription usage; no per-call dollar price supplied",
            "failure": failure,
            "diagnostics": [
                event["item"] for event in events if event.get("item", {}).get("type") == "error"
            ],
        }


def make_planner(config):
    if config.provider == "codex":
        return CodexPlanner(config)
    if config.provider == "command":
        return CommandPlanner(config)
    raise OrchestrationError("MODEL_CONFIG", "Choose the codex or command provider.")


async def discover_codex_models(directory):
    executable = shutil.which("codex")
    if not executable:
        raise ValueError("Codex CLI is unavailable.")
    directory.mkdir(parents=True, exist_ok=True)
    messages = [
        {
            "id": 1,
            "method": "initialize",
            "params": {
                "clientInfo": {
                    "name": "mcp_execution_lab",
                    "title": "MCP Execution Lab",
                    "version": __version__,
                }
            },
        },
        {"method": "initialized", "params": {}},
        {"id": 2, "method": "model/list", "params": {"limit": 50, "includeHidden": False}},
    ]
    process = await asyncio.create_subprocess_exec(
        executable,
        "app-server",
        "--listen",
        "stdio://",
        cwd=directory,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(30):
            for message in messages:
                process.stdin.write((json.dumps(message) + "\n").encode())
                await process.stdin.drain()
                if message.get("id"):
                    while True:
                        value = json.loads(await process.stdout.readline())
                        if value.get("id") == message["id"]:
                            if "error" in value:
                                raise ValueError(str(value["error"]))
                            break
            return value["result"]
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()
