"""PostToolUse hook: after Claude writes or edits a .py file, lint that file with ruff and show Claude the findings.

Report-only: runs `ruff check` (no --fix, no format) so diffs stay limited to what Claude actually changed; Claude
reads the findings as context and fixes what its change introduced. A repo-wide `ruff format` is a separate, one-off
commit. Clean files, non-Python files and any error produce no output."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    payload = json.load(sys.stdin)
    path = Path((payload.get("tool_input") or {}).get("file_path", ""))
    if path.suffix != ".py" or not path.is_file():
        return
    venv_ruff = ROOT / ".venv" / "bin" / "ruff"
    ruff = [str(venv_ruff)] if venv_ruff.exists() else ["uv", "run", "--quiet", "ruff"]
    result = subprocess.run(
        [*ruff, "check", "--output-format", "concise", "--no-fix", str(path)],
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode != 1 or not result.stdout.strip():
        return
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": (
        f"ruff check found issues in {path.name}. Fix the ones your edit introduced; leave pre-existing ones "
        f"in untouched code alone unless asked.\n{result.stdout.strip()}")}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001, S110 — a lint hook must never break an edit
        pass
