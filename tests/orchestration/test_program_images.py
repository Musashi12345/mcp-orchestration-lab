"""Image lookup remains fail closed when a Desktop tag index is inconsistent."""

import json

import pytest

from mcp_execution_lab.orchestration import program_container
from mcp_execution_lab.orchestration.config import ProgramRunnerConfig
from mcp_execution_lab.orchestration.models import OrchestrationError

IMAGE_ID = "sha256:" + "a" * 64


@pytest.mark.parametrize(
    "case", ["valid", "missing", "ambiguous", "wrong_tag", "wrong_id", "stale"]
)
async def test_image_index_resolution_requires_exact_identity_tag_and_sdk(monkeypatch, case):
    config = ProgramRunnerConfig()
    calls = []
    row = {"Repository": config.image.rsplit(":", 1)[0], "Tag": "dev", "ID": IMAGE_ID}
    rows = [] if case == "missing" else [row]
    if case == "ambiguous":
        rows.append(row | {"ID": "sha256:" + "b" * 64})

    async def docker(*args, **kwargs):
        calls.append(args)
        if args == ("image", "inspect", config.image):
            raise OrchestrationError("DOCKER", "No such image: " + config.image)
        if args[:2] == ("image", "ls"):
            return "\n".join(json.dumps(value) for value in rows).encode()
        assert args == ("image", "inspect", IMAGE_ID)
        return json.dumps(
            [
                {
                    "Id": "sha256:" + "b" * 64 if case == "wrong_id" else IMAGE_ID,
                    "RepoTags": [] if case == "wrong_tag" else [config.image],
                    "Os": "linux",
                    "Config": {
                        "Labels": {
                            "lab.csv_python_sdk_sha256": "stale"
                            if case == "stale"
                            else program_container.sdk_identity()
                        }
                    },
                }
            ]
        ).encode()

    monkeypatch.setattr(program_container, "docker", docker)
    if case == "valid":
        identity = await program_container.image_identity(config)
        assert identity["image_id"] == IMAGE_ID
        assert identity["resolution"] == "verified_tag_index"
        assert len(calls) == 3
    else:
        with pytest.raises(OrchestrationError) as error:
            await program_container.image_identity(config)
        assert error.value.code == "P1_IMAGE"
        if case in {"missing", "ambiguous"}:
            assert len(calls) == 2
