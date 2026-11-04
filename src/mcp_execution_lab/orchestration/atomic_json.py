"""Replace mutable JSON snapshots without retrying any model or tool operation."""

import json
import time
import uuid
from pathlib import Path


def save_json(path, value):
    path = Path(path)
    # A unique sibling prevents concurrent writers from sharing a temporary filename.
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")
    delays = (0.025, 0.05, 0.1, 0.2, 0.4)
    for attempt in range(len(delays) + 1):
        try:
            temporary.replace(path)
            return
        except PermissionError as exc:
            # Windows readers/scanners can briefly hold an existing snapshot open.
            # A permanent denial remains an error; retain the temporary evidence.
            if getattr(exc, "winerror", None) not in {5, 32, 33} or attempt == len(delays):
                raise
            time.sleep(delays[attempt])
