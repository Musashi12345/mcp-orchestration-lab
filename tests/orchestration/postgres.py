"""Temporary native PostgreSQL for integration tests; never touches the user's service."""

import os
import secrets
import shutil
import socket
import subprocess
import time
from pathlib import Path

import psycopg


class LocalPostgres:
    def __init__(self, root: Path):
        binary = shutil.which("psql")
        if binary is None:
            raise FileNotFoundError("Install local PostgreSQL tools to run this integration test.")
        self.bin = Path(binary).parent
        self.root = root
        self.data = root / "data"
        self.password = secrets.token_urlsafe(24)
        self.process = None
        self.log = None
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            self.port = listener.getsockname()[1]
        self.flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    @property
    def url(self):
        return f"postgresql+psycopg://lab_test:{self.password}@127.0.0.1:{self.port}/postgres"

    def start(self):
        self.root.mkdir(parents=True, exist_ok=True)
        password_file = self.root / "password.txt"
        password_file.write_text(self.password, encoding="utf-8")
        init = subprocess.run(
            [
                str(self.bin / "initdb"),
                "-D",
                str(self.data),
                "-U",
                "lab_test",
                "--pwfile",
                str(password_file),
                "--auth-host=scram-sha-256",
                "--auth-local=scram-sha-256",
                "--encoding=UTF8",
                "--locale=C",
            ],
            capture_output=True,
            text=True,
            creationflags=self.flags,
            timeout=60,
        )
        (self.root / "initdb.log").write_text(init.stdout + init.stderr, encoding="utf-8")
        if init.returncode:
            raise RuntimeError(
                f"Temporary PostgreSQL initialization failed; see {self.root / 'initdb.log'}"
            )
        self.log = (self.root / "server.log").open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            [
                str(self.bin / "postgres"),
                "-D",
                str(self.data),
                "-h",
                "127.0.0.1",
                "-p",
                str(self.port),
                "-c",
                "max_connections=20",
            ],
            stdout=self.log,
            stderr=subprocess.STDOUT,
            creationflags=self.flags,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                break
            try:
                with psycopg.connect(
                    host="127.0.0.1",
                    port=self.port,
                    user="lab_test",
                    password=self.password,
                    dbname="postgres",
                    connect_timeout=1,
                ):
                    return self
            except psycopg.OperationalError:
                time.sleep(0.1)
        self.close()
        raise RuntimeError(f"Temporary PostgreSQL did not start; see {self.root / 'server.log'}")

    def close(self):
        if self.process is not None and self.process.poll() is None:
            subprocess.run(
                [str(self.bin / "pg_ctl"), "-D", str(self.data), "-m", "fast", "-w", "stop"],
                capture_output=True,
                creationflags=self.flags,
                timeout=30,
            )
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if self.log:
            self.log.close()
