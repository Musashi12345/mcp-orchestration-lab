"""Resolve/check report source citations and save current file identities.

This audits links and hashes only; it does not rerun the production test suite.
"""

import ast
import hashlib
import json
import re
from pathlib import Path

from mcp_execution_lab.orchestration.provenance import source_identity

ROOT = Path(__file__).resolve().parents[3]
REPORT = ROOT / "docs/Cross-check"


def file_path(name):
    direct = ROOT / name
    return direct if direct.exists() else ROOT / "src/mcp_execution_lab" / name


def symbols(path):
    found = {}

    def visit(node, prefix=""):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                key = prefix + child.name
                found[key] = {"line": child.lineno, "end_line": child.end_lineno}
                visit(child, key + ".")
            elif isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        found[prefix + target.id] = {
                            "line": child.lineno,
                            "end_line": child.end_lineno,
                        }

    visit(ast.parse(path.read_text(encoding="utf-8")))
    return found


def main():
    references = []
    linked_paths = set()

    def code(match):
        name, symbol = match.group(1).split("#", 1)
        path = file_path(name)
        if symbol.isdigit():
            line = int(symbol)
            assert 1 <= line <= len(path.read_text(encoding="utf-8").splitlines())
        else:
            line = symbols(path)[symbol]["line"]
        label = f"{path.name}:{line}" if symbol.isdigit() else f"{symbol} ({path.name}:{line})"
        return f"[{label}]({path.as_posix()}:{line})"

    links = re.compile(r"\[([^\]]+)\]\((" + re.escape(ROOT.as_posix()) + r"/[^)\n]+):(\d+)\)")
    for document in sorted(REPORT.glob("*.md")):
        original = document.read_text(encoding="utf-8")
        updated = re.sub(r"\{\{code:([^}]+)\}\}", code, original)
        if updated != original:
            document.write_text(updated, encoding="utf-8")
        assert "{{code:" not in updated, document
        for label, name, line_text in links.findall(updated):
            path, line = Path(name), int(line_text)
            assert path.is_file(), name
            assert 1 <= line <= len(path.read_text(encoding="utf-8").splitlines()), name
            symbol = label.split(" (")[0] if " (" in label else line_text
            if not symbol.isdigit():
                assert symbols(path)[symbol]["line"] == line, (name, symbol, line)
            references.append(
                {
                    "document": document.relative_to(REPORT).as_posix(),
                    "file": path.relative_to(ROOT).as_posix(),
                    "symbol": symbol,
                    "line": line,
                }
            )
            linked_paths.add(path)
    paths = sorted(
        set((ROOT / "src").rglob("*.py"))
        | set((ROOT / "tests").rglob("*.py"))
        | set((ROOT / "scripts").glob("*.ps1"))
        | set((ROOT / "configs").glob("*.yaml"))
        | linked_paths
        | {
            ROOT / "start_agents.ps1",
            ROOT / "stop_agents.ps1",
            ROOT / ".env.example",
            ROOT / "pyproject.toml",
            ROOT / "uv.lock",
            ROOT / "fixtures/data_analysis_evals/development/manifest.json",
            ROOT / "fixtures/data_analysis_evals/development/tasks.json",
        }
    )
    manifest = {
        "audit_date": "2026-10-23",
        "date_basis": "User client date, Asia/Calcutta",
        **source_identity(),
        "files": {
            path.relative_to(ROOT).as_posix(): {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "lines": len(path.read_text(encoding="utf-8").splitlines()),
                **({"symbols": symbols(path)} if path.suffix == ".py" else {}),
            }
            for path in paths
        },
        "resolved_code_citations": references,
    }
    (REPORT / "evidence/source_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "files_snapshotted": len(paths),
                "citations_resolved": len(references),
                "source": source_identity(),
            }
        )
    )


if __name__ == "__main__":
    main()
