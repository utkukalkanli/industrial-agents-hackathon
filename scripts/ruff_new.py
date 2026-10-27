"""List the ruff findings the staged change adds; findings that already exist in HEAD don't count.

  uv run python scripts/ruff_new.py

For each staged .py file (added, modified or renamed), runs `ruff check` on the HEAD version and on the staged
(index) version and compares findings by (rule code, stripped source line), so a finding whose line only moved is
not new. Exit 0: no new findings. Exit 1: new findings printed as `path:line: CODE message`. Exit 2: error."""

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def staged_python_files() -> list[tuple[str | None, str]]:
    """(path in HEAD or None if new, path in the index) for every staged .py file that still exists."""
    out = git("diff", "--cached", "--name-status", "-M", "--diff-filter=ACMR")
    files = []
    for line in out.splitlines():
        status, *paths = line.split("\t")
        new = paths[-1]
        if not new.endswith(".py"):
            continue
        old = paths[0] if status[0] in "MR" else None
        files.append((old, new))
    return files


def findings(source: str, path: str) -> list[dict]:
    """ruff findings for `source` checked as if it were `path` (so per-path config applies)."""
    result = subprocess.run(
        ["ruff", "check", "--output-format", "json", "--no-fix", "--stdin-filename", path, "-"],
        cwd=ROOT, input=source, capture_output=True, text=True, check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"ruff failed on {path}: {result.stderr.strip()}")
    lines = source.splitlines()
    out = []
    for item in json.loads(result.stdout or "[]"):
        row = item["location"]["row"]
        text = lines[row - 1].strip() if 0 < row <= len(lines) else ""
        out.append({"code": item.get("code") or "syntax-error", "row": row, "text": text,
                    "message": item["message"]})
    return out


def main() -> int:
    new_findings = []
    for old, new in staged_python_files():
        before = Counter()
        if old is not None:
            before = Counter((f["code"], f["text"]) for f in findings(git("show", f"HEAD:{old}"), old))
        for finding in findings(git("show", f":{new}"), new):
            key = (finding["code"], finding["text"])
            if before[key]:
                before[key] -= 1
            else:
                new_findings.append(f"{new}:{finding['row']}: {finding['code']} {finding['message']}")
    for line in new_findings:
        print(line)
    print(f"ruff_new: {len(new_findings)} new finding(s) in staged .py files")
    return 1 if new_findings else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"ruff_new: error: {error}")
        sys.exit(2)
