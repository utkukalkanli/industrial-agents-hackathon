"""Smoke test of a running app: a local uvicorn in CI, or a Vercel deployment after a deploy (docs/guides/ci-cd.md).

    uv run python scripts/smoke_test.py http://127.0.0.1:8000 --chat          # CI: backend + Postgres, offline Guide
    uv run python scripts/smoke_test.py https://<deployment> --frontend      # after a deploy

Checks, all through the /api prefix the Vercel rewrite keeps: /health answers ok (retried while the server or a cold
function starts), /buildings lists dev buildings, a conversation is created and read back. --chat also says "I use a
wheelchair" and reads the profile back (a Guide turn: use it only with the offline Guide, a real model costs money).
--frontend checks that / serves the React app. VERCEL_AUTOMATION_BYPASS_SECRET, when set, is sent so a deployment
behind Vercel Authentication answers. Exit code 1 on the first failed check.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


class SmokeError(Exception):
    pass


def request(base: str, path: str, body: dict | None = None, timeout: float = 60) -> tuple[int, str]:
    headers = {"accept": "application/json"}
    if secret := os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET"):
        headers["x-vercel-protection-bypass"] = secret
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["content-type"] = "application/json"
    req = urllib.request.Request(base.rstrip("/") + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode(errors="replace")


def json_or_fail(base: str, path: str, body: dict | None = None) -> object:
    status, text = request(base, path, body)
    if status != 200:
        raise SmokeError(f"{path}: HTTP {status}: {text[:300]}")
    return json.loads(text)


def wait_for_health(base: str, attempts: int, delay: float) -> dict:
    last = "no answer"
    for attempt in range(1, attempts + 1):
        try:
            status, text = request(base, "/api/health", timeout=30)
            if status == 200 and json.loads(text).get("ok") is True:
                return json.loads(text)
            last = f"HTTP {status}: {text[:200]}"
        except (OSError, ValueError) as error:
            last = str(error)
        print(f"  health attempt {attempt}/{attempts}: {last}", file=sys.stderr)
        time.sleep(delay)
    raise SmokeError(f"/api/health never answered ok: {last}")


def run(base: str, chat: bool, frontend: bool, attempts: int, delay: float) -> None:
    health = wait_for_health(base, attempts, delay)
    print(f"ok  /api/health {health}")

    buildings = json_or_fail(base, "/api/buildings")
    dev = [item["id"] for item in buildings if item.get("split") == "dev"]
    if not dev:
        raise SmokeError(f"/api/buildings: no dev building among {len(buildings)}")
    print(f"ok  /api/buildings {len(buildings)} buildings")

    created = json_or_fail(base, "/api/sessions", {"building": dev[0]})
    session_id = created["session_id"]
    json_or_fail(base, f"/api/sessions/{session_id}")
    print(f"ok  /api/sessions created and read back ({dev[0]})")

    if chat:
        json_or_fail(base, "/api/chat", {"session_id": session_id, "message": "I use a wheelchair"})
        profile = json_or_fail(base, f"/api/sessions/{session_id}")["profile"]
        if profile.get("step_free") is not True:
            raise SmokeError(f"after 'I use a wheelchair' the profile is not step-free: {profile}")
        print("ok  /api/chat remembered the wheelchair profile")

    if frontend:
        status, text = request(base, "/")
        if status != 200 or 'id="root"' not in text:
            raise SmokeError(f"/: HTTP {status}, no React root in {text[:200]!r}")
        print("ok  / serves the app")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base_url")
    parser.add_argument("--chat", action="store_true", help="one Guide turn (offline Guide only)")
    parser.add_argument("--frontend", action="store_true", help="check that / serves the React app")
    parser.add_argument("--attempts", type=int, default=20)
    parser.add_argument("--delay", type=float, default=3.0)
    args = parser.parse_args()
    try:
        run(args.base_url, args.chat, args.frontend, args.attempts, args.delay)
    except SmokeError as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    print("smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
