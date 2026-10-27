"""Voice transcript rewriter (D-013): one small, fast model call that normalises a speech-to-text transcript to the
building's vocabulary before the Guide sees it ("lab two seventeen" → "Lab 2.17").

It only normalises names and numbers: no interpretation, no answering. The vocabulary is the building's floors,
room and asset types, lifts/stairs and space names (agent/llm_parser.py `building_vocabulary`), cached as the system
prompt. Any doubt keeps the transcript as heard: an API error, a refusal, an empty answer, or a number that is
neither in the transcript nor in the building. The Guide gets both versions, so a dropped nuance stays visible.

GUIDE_REWRITER_MODEL (default claude-haiku-5-5), GUIDE_REWRITER=off disables it."""

import json
import os
import re

import anthropic

from agent import llm_client
from agent.llm_parser import LlmUsage, building_vocabulary
from core.building_map import BuildingMap

DEFAULT_MODEL = "claude-haiku-5-5"
MAX_TOKENS = 2000
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
SCHEMA = {
    "type": "object",
    "properties": {"rewritten": {"type": "string"}},
    "required": ["rewritten"],
    "additionalProperties": False,
}
RULES = """You clean up speech-to-text transcripts for a building guide. You get one transcript of what a person \
said about this building. Rewrite it so that room names, refs, floor names, lift and stair names, asset names and \
numbers are written exactly as in the building vocabulary below ("lab two seventeen" → "Lab 2.17", "lift one" → \
"Lift 1", "floor three" → "Floor 3"). Fix obvious mishearings only when one vocabulary entry clearly fits. Keep \
ordinal floor words ("the second floor", "first floor") as said: they mean different floors in different countries.

Change nothing else: keep the person's words, language, order and meaning, including vague parts ("the printer", \
"somewhere near the kitchen"). Never answer, explain, add or drop information, and never pick one of several rooms \
the person did not name. If nothing needs normalising, return the transcript unchanged. Reply with the rewritten \
transcript in the `rewritten` field."""


def invented_numbers(rewritten: str, transcript: str, vocabulary: str) -> list[str]:
    """Numbers in the rewrite that appear neither in the transcript nor in the building vocabulary."""
    known = set(NUMBER.findall(transcript)) | set(NUMBER.findall(vocabulary))
    return [number for number in dict.fromkeys(NUMBER.findall(rewritten)) if number not in known]


class TranscriptRewriter:
    def __init__(self, building: BuildingMap, client: object | None = None, model: str | None = None) -> None:
        self.client = client if client is not None else llm_client.make()
        self.model = model or os.environ.get("GUIDE_REWRITER_MODEL", DEFAULT_MODEL)
        self.vocabulary = building_vocabulary(building)
        self.system = [
            {"type": "text", "text": RULES},
            {"type": "text", "text": "Building vocabulary:\n" + self.vocabulary, "cache_control": {"type": "ephemeral"}},
        ]
        self.usage = LlmUsage()

    def rewrite(self, transcript: str) -> str:
        """The transcript normalised to the building's vocabulary, or unchanged when in any doubt."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=self.system,
                messages=[{"role": "user", "content": f"Transcript:\n{transcript}"}],
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            )
        except anthropic.APIError:
            return transcript
        self.track(response.usage)
        if response.stop_reason != "end_turn":  # refusal, max_tokens: keep what was heard
            return transcript
        try:
            text = next(block.text for block in response.content if block.type == "text")
            rewritten = str(json.loads(text)["rewritten"]).strip()
        except (StopIteration, ValueError, KeyError, TypeError):
            return transcript
        if not rewritten or invented_numbers(rewritten, transcript, self.vocabulary):
            return transcript
        return rewritten

    def track(self, usage: object) -> None:
        self.usage.input_tokens += usage.input_tokens
        self.usage.output_tokens += usage.output_tokens
        self.usage.cache_read_input_tokens += usage.cache_read_input_tokens or 0
        self.usage.cache_creation_input_tokens += usage.cache_creation_input_tokens or 0

