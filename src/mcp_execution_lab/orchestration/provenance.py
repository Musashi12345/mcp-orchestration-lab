"""Record source and environment identities without exposing private fixtures."""

import hashlib
from pathlib import Path

from .models import fingerprint


def source_identity():
    package = Path(__file__).resolve().parents[1]
    root = package.parent.parent
    sources = {
        path.relative_to(package).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(package.rglob("*.py"))
    }
    lock = root / "uv.lock"
    return {
        "source_sha256": fingerprint(sources),
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest() if lock.is_file() else None,
    }
