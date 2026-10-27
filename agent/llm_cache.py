"""Decision cache: every model decision of a benchmark run (the LLM parser's slots, the solver agent's submitted
answer and the code it ran), keyed by the building's content, the question text and the schema version.

A run reads the cache before asking a model, so re-running the benchmark command reproduces the submitted answers
exactly — also without an API key (the organisers may re-run it) — and our own reruns stay stable and cost nothing.
Only decisions are stored, never final numbers: lengths, areas and counts are recomputed by code from the replayed
slots; an agent answer is the value it computed with code, kept with that code for review.

  LLM_CACHE=<path>   cache file (default llm_cache/decisions.json at the repo root, committed)
  LLM_CACHE=off      no cache: every question goes to the model again"""

import hashlib
import json
import os
from pathlib import Path

from agent import llm_client
from core.building_map import BuildingMap

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "llm_cache" / "decisions.json"
_FINGERPRINTS: dict[int, tuple[object, str]] = {}


def building_fingerprint(bmap: BuildingMap) -> str:
    """sha256 of the building's data (stable key order), memoised per BuildingMap object."""
    cached = _FINGERPRINTS.get(id(bmap))
    if cached and cached[0] is bmap.data:
        return cached[1]
    digest = hashlib.sha256(json.dumps(bmap.data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    _FINGERPRINTS[id(bmap)] = (bmap.data, digest)
    return digest


def decision_key(namespace: str, version: str, bmap: BuildingMap, text: str) -> str:
    """Keys are per provider: a run on OpenAI never replays Claude's decisions. Claude's keys keep their original
    form (no tag), so the committed Claude decisions still replay with LLM_PROVIDER=anthropic."""
    question = hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()
    tag = "" if llm_client.provider() == "anthropic" else f"@{llm_client.provider()}"
    return f"{namespace}{tag}/{version}/{building_fingerprint(bmap)[:16]}/{question[:24]}"


class DecisionCache:
    """A JSON file of decisions; `None` as path = in memory only (tests, LLM_CACHE=off)."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.data: dict[str, object] = {}
        if path is not None and path.is_file():
            self.data = json.loads(path.read_text(encoding="utf-8"))

    @classmethod
    def configured(cls) -> "DecisionCache":
        setting = os.environ.get("LLM_CACHE", "")
        if setting.lower() == "off":
            return cls(None)
        return cls(Path(setting) if setting else DEFAULT_PATH)

    def get(self, key: str) -> object | None:
        return self.data.get(key)

    def put(self, key: str, value: object) -> None:
        self.data[key] = value
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        partial = self.path.with_name(self.path.name + ".partial")
        partial.write_text(json.dumps(self.data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        partial.replace(self.path)
