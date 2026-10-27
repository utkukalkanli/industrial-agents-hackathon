"""Record that the current staged tree passed verification. Called by the /ship skill after a PASS.

  python3 .claude/hooks/stamp-verified.py .claude/worklog/history/<entry>.md

Refuses unless the entry contains a `VERDICT: PASS` line (commit-verifier) and a `REVIEW: PASS` line
(code-reviewer) and is itself staged."""

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAMP = ROOT / ".claude" / "worklog" / ".verified"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    entry = Path(sys.argv[1]).resolve()
    if not entry.exists():
        print(f"refused: {entry} does not exist")
        return 1
    text = entry.read_text(encoding="utf-8")
    for line in ("VERDICT", "REVIEW"):
        if not re.search(rf"^{line}:\s*PASS\b", text, flags=re.MULTILINE):
            print(f"refused: the worklog entry has no '{line}: PASS' line")
            return 1
    relative = entry.relative_to(ROOT).as_posix()
    if relative not in git("diff", "--cached", "--name-only").split():
        print(f"refused: {relative} is not staged")
        return 1
    tree = git("write-tree").strip()
    STAMP.write_text(f"{tree} {datetime.now().isoformat(timespec='seconds')} {relative}\n", encoding="utf-8")
    print(f"stamped staged tree {tree}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
