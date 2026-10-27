# Floorwise

*Talk to your building.* Agent-first indoor navigation for the Industrial Agents Hackathon 2026, Track 01 (Synera). Ask a building where
things are, how to get there, and what changes when a lift closes; a deterministic geometry/graph core computes
every answer and the LLM handles the language.

Project knowledge base: [CLAUDE.md](CLAUDE.md) → [docs/README.md](docs/README.md). All commands:
[docs/guides/commands.md](docs/guides/commands.md).

## Setup

You need Python ≥ 3.12, [uv](https://docs.astral.sh/uv/) and an OpenAI or Anthropic API key (`LLM_PROVIDER`, D-024). The organiser kit's dataset
is committed in `data/`, so one clone is enough.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh      # if uv is missing
git clone https://github.com/atahankilc/industrial-agents-hackathon.git
cd industrial-agents-hackathon
uv sync
cp .env.example .env                                  # put OPENAI_API_KEY (or ANTHROPIC_API_KEY) in .env, never commit it
```

## Running the Synera kit

The rest of the kit (starter agent) lives in `archive/initial-repo/`; run it from the repo root with
`PYTHONPATH=archive/initial-repo`.

```bash
# Warm-up questions with the kit's tools only (free, no API): expect 369/369
PYTHONPATH=archive/initial-repo uv run python -m starter_agent.evaluate data/dev --oracle

# Chat with one building using the starter agent (uses API credits)
PYTHONPATH=archive/initial-repo uv run --env-file .env python -m starter_agent data/dev/proc-factory-dev-003

# Benchmark questions with the starter agent (about $0.10–0.25 per question)
PYTHONPATH=archive/initial-repo uv run --env-file .env python -m benchmark.evaluate data/dev --per-kind 3
```

## Running our code

```bash
uv run pytest                                          # offline tests

# Our agent on dev, then the test submission (function answer(building_directory, question_text) -> str)
uv run --env-file .env python -m benchmark.evaluate data/dev --agent agent.answer:answer
uv run --env-file .env python -m benchmark.evaluate data/test --agent agent.answer:answer --submission-csv submissions/team_jaRAG.csv

# One-command benchmark run (building or split dir, questions file, answers .csv or .json)
uv run --env-file .env python -m agent.run_benchmark_v1 <building_dir> <questions> <answers>
```

`benchmark/score.py` is the official scorer; never edit it. The benchmark command, formats and current scores are
in [SUBMISSION/BENCHMARK.md](SUBMISSION/BENCHMARK.md); our answers file is `SUBMISSION/answers.json`. Still open: the
exact Sunday input/output format ([Q-001](memory-bank/open-questions.md#q-001)).

## Licences

Our code is MIT ([LICENSE](LICENSE)). Kit code and data keep their own terms: see [NOTICE.md](NOTICE.md),
[ATTRIBUTION.md](ATTRIBUTION.md) and [data/README.md](data/README.md). Anything derived from the OpenStreetMap
buildings stays under the ODbL and credits © OpenStreetMap contributors.
