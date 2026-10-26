"""Stop hook: before Claude ends a turn, make sure tracked changes are recorded in memory-bank/log.md.

If tracked files differ from HEAD (staged or not; memory-bank/log.md and .claude/worklog/ don't count) and
memory-bank/log.md itself is unchanged, the stop is blocked once per session with a reason Claude reads: append a
log.md entry (memory-bank/README.md) or say why none is needed. `stop_hook_active` and a per-session marker in
.git/ keep it from looping or nagging every turn. Any error lets the stop through."""

import json
import subprocess
import sys
from pathlib import Path

LOG = "memory-bank/log.md"
IGNORED = (LOG, ".claude/worklog/")


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout


def main():
    payload = json.load(sys.stdin)
    if payload.get("stop_hook_active"):
        return
    root = Path(git(payload.get("cwd") or ".", "rev-parse", "--show-toplevel").strip())
    changed = [path for path in git(root, "diff", "HEAD", "--name-only").splitlines() if path]
    if LOG in changed or not [path for path in changed if not path.startswith(IGNORED)]:
        return
    marker = Path(git(root, "rev-parse", "--absolute-git-dir").strip()) / "claude-log-reminded" / payload.get("session_id", "unknown")
    if marker.exists():
        return
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    print(json.dumps({"decision": "block", "reason": (
        f"Tracked files changed this session but {LOG} has no new entry. Append one at the top following "
        "memory-bank/README.md (dated heading with time; Did / Learned / Changed docs / Next), update "
        "memory-bank/project-state.md if what exists or what is next changed, then run "
        "`uv run python scripts/check_links.py`. If the changes need no log entry, say why in one line.")}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
