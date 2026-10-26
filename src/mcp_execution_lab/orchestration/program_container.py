"""CSV-only Docker boundary and bounded pipe protocol; no host-code fallback."""

import asyncio
import hashlib
import json
import os
import re
import shutil
import uuid
from pathlib import Path

from ..program_sdk.policy import VERSION
from ..program_sdk.protocol import ProtocolError, encode, read_async
from .models import OrchestrationError

PROJECT = Path(__file__).resolve().parents[3]
SDK_DIRECTORY = PROJECT / "src/mcp_execution_lab/program_sdk"
BASE_IMAGE = (
    "python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704"
)


class ProgramRevised(Exception):
    """Host-controlled supersession after all underlying tool work has settled."""


def sdk_identity():
    digest = hashlib.sha256()
    for path in sorted(SDK_DIRECTORY.glob("*.py")):
        digest.update(path.name.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def docker_binary():
    binary = shutil.which("docker")
    if not binary and os.name == "nt":
        candidate = Path("C:/Program Files/Docker/Docker/resources/bin/docker.exe")
        if candidate.is_file():
            binary = str(candidate)
    if not binary:
        raise OrchestrationError(
            "DOCKER_UNAVAILABLE", "Install and start Docker with Linux containers."
        )
    return binary


async def docker(*args, timeout=30):
    process = await asyncio.create_subprocess_exec(
        docker_binary(), *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise OrchestrationError("DOCKER", stderr.decode(errors="replace")[-4000:])
    return stdout


async def build_image(config):
    await docker(
        "build",
        "--pull=false",
        "--build-arg",
        f"SDK_SHA256={sdk_identity()}",
        "--tag",
        config.image,
        "--file",
        str(PROJECT / "containers/csv_python/Dockerfile"),
        str(PROJECT),
        timeout=300,
    )
    return await image_identity(config)


async def inspect_image(reference):
    try:
        return json.loads(await docker("image", "inspect", reference))[0], "reference"
    except OrchestrationError as original:
        if "no such image" not in str(original).lower():
            raise
        # Some Desktop stores list a valid tag but cannot inspect it by name. Require
        # one exact tag match, then independently check that immutable image's tags.
        tag = reference
        if "@" not in tag and ":" not in tag.rsplit("/", 1)[-1]:
            tag += ":latest"
        rows = await docker(
            "image",
            "ls",
            "--no-trunc",
            "--filter",
            f"reference={tag}",
            "--format",
            "{{json .}}",
        )
        try:
            matches = set()
            for line in rows.decode().splitlines():
                row = json.loads(line)
                identity = row.get("ID", "")
                if row.get("Repository", "") + ":" + row.get("Tag", "") == tag and re.fullmatch(
                    r"sha256:[a-f0-9]{64}", identity
                ):
                    matches.add(identity)
            if len(matches) != 1:
                raise original
            identity = matches.pop()
            info = json.loads(await docker("image", "inspect", identity))[0]
            if info.get("Id") != identity or tag not in info.get("RepoTags", []):
                raise original
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise original from exc
        return info, "verified_tag_index"


async def image_identity(config):
    try:
        info, resolution = await inspect_image(config.image)
    except OrchestrationError as exc:
        raise OrchestrationError(
            "P1_IMAGE", "Build the CSV P1 image with analysis runner-build."
        ) from exc
    expected = sdk_identity()
    if (
        info.get("Os") != "linux"
        or info["Config"].get("Labels", {}).get("lab.csv_python_sdk_sha256") != expected
    ):
        raise OrchestrationError(
            "P1_IMAGE", "CSV runner SDK changed. Rebuild with analysis runner-build."
        )
    return {
        "image_id": info["Id"],
        "configured_image": config.image,
        "resolution": resolution,
        "sdk_sha256": expected,
        "base_image": BASE_IMAGE,
        "policy": VERSION,
        "controls": config.model_dump(mode="json"),
    }


class Container:
    def __init__(self, config, identity, frame_limit):
        self.config, self.identity, self.limit = config, identity, frame_limit
        self.name = "mcp-lab-p1-" + uuid.uuid4().hex
        self.process = None
        self.stderr = bytearray()
        self.cleanup = None

    async def _stderr(self):
        while chunk := await self.process.stderr.read(4096):
            self.stderr.extend(chunk)
            del self.stderr[:-8192]

    async def run(self, start, on_call, on_start):
        config = self.config
        pending, read_task, stderr_task = {}, None, None
        try:
            await docker(
                "create",
                "--name",
                self.name,
                "--interactive",
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--user=65532:65532",
                f"--cpus={config.cpus}",
                f"--memory={config.memory_mib}m",
                f"--memory-swap={config.memory_mib}m",
                f"--pids-limit={config.pids}",
                "--log-driver=none",
                "--tmpfs",
                f"/tmp:rw,noexec,nosuid,nodev,size={config.tmp_mib}m,mode=1777",
                self.identity["image_id"],
            )
            actual = json.loads(await docker("inspect", self.name))[0]
            await on_start(
                {
                    "container_id": actual["Id"],
                    "name": self.name,
                    "image_id": actual["Image"],
                    "host_config": actual["HostConfig"],
                    "user": actual["Config"]["User"],
                    "mounts": actual["Mounts"],
                }
            )
            self.process = await asyncio.create_subprocess_exec(
                docker_binary(),
                "start",
                "--attach",
                "--interactive",
                self.name,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stderr_task = asyncio.create_task(self._stderr())
            self.process.stdin.write(encode(start, self.limit))
            await self.process.stdin.drain()
            seen, ready = set(), False
            read_task = asyncio.create_task(read_async(self.process.stdout, self.limit))
            while True:
                done, _ = await asyncio.wait(
                    [read_task, *pending], return_when=asyncio.FIRST_COMPLETED
                )
                for task in done - {read_task}:
                    request_id = pending.pop(task)
                    value = task.result()  # uncertain outcomes abort the whole bridge
                    self.process.stdin.write(
                        encode({"type": "reply", "id": request_id, "result": value}, self.limit)
                    )
                    await self.process.stdin.drain()
                if read_task not in done:
                    continue
                packet = read_task.result()
                kind = packet.get("type")
                if kind == "ready" and not ready and packet == {"type": "ready", "policy": VERSION}:
                    ready = True
                elif kind == "call" and ready:
                    if set(packet) != {"type", "id", "subtask_id", "arguments", "handles"}:
                        raise ProtocolError("Unexpected tool request fields.")
                    key = packet["id"]
                    if not isinstance(key, str) or not key or len(key) > 64 or key in seen:
                        raise ProtocolError("Invalid or repeated request ID.")
                    if len(seen) >= len(start["jobs"]):
                        raise ProtocolError("Program exceeded its assigned call count.")
                    seen.add(key)
                    pending[asyncio.create_task(on_call(packet))] = key
                elif kind in {"result", "error"} and ready and not pending:
                    if set(packet) != (
                        {"type", "value"} if kind == "result" else {"type", "message"}
                    ):
                        raise ProtocolError("Unexpected final response fields.")
                    self.process.stdin.write(encode({"type": "finished"}, self.limit))
                    await self.process.stdin.drain()
                    self.process.stdin.close()
                    exit_code = await asyncio.wait_for(self.process.wait(), 5)
                    if kind == "error" or exit_code:
                        raise OrchestrationError(
                            "PROGRAM_FAILED",
                            str(packet.get("message", "Runner exited unsuccessfully."))[:2000],
                        )
                    return packet["value"]
                else:
                    raise ProtocolError("Unexpected runner message or unfinished calls at return.")
                read_task = asyncio.create_task(read_async(self.process.stdout, self.limit))
        except (ProtocolError, EOFError, BrokenPipeError, ConnectionResetError) as exc:
            raise OrchestrationError("PROGRAM_PROTOCOL", str(exc)[:2000]) from exc
        finally:
            tasks = [*pending, *([read_task] if read_task else [])]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            # Always remove only this invocation's random, owned container.
            try:
                await docker("rm", "--force", self.name, timeout=15)
                self.cleanup = "REMOVED"
            except (OrchestrationError, TimeoutError) as exc:
                self.cleanup = {"status": "CHECK_REQUIRED", "message": str(exc)[:1000]}
            if self.process and self.process.returncode is None:
                self.process.kill()
                await self.process.wait()
            if stderr_task:
                await stderr_task
