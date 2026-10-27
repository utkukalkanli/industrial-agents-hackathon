# BENCHMARK — how to reproduce our answers

One command from the repo root, no manual steps between input and output. It runs in the default `hybrid` parser
mode: the template parser first (deterministic, no LLM), and an LLM only for wording no template matches. The LLM
only maps the question to a kind and room/floor ids (or hands it to the solver agent, below); every number still
comes from code. It needs `OPENAI_API_KEY` in `.env` (copy `.env.example`; `LLM_PROVIDER=anthropic` with `ANTHROPIC_API_KEY`
for Claude); the runner reads `.env` itself, so
`--env-file .env` is optional.

```bash
uv sync
# Sunday: one building directory (holds building.json) + its question file
uv run python -m agent.run_benchmark_v1 <building_dir> <questions file> SUBMISSION/answers.json
# Public test set (145 questions, buildings under data/test/<building_id>/) — this produced SUBMISSION/answers.json
uv run --env-file .env python -m agent.run_benchmark_v1 data/test data/test/questions.csv SUBMISSION/answers.json
```

No API key: the same command replays every model decision from `llm_cache/decisions.json` (see below) and
reproduces our `answers.json`. `PARSER_MODE=regex` in front of the command is fully deterministic and needs no
network, but a question whose wording matches no template then gets no answer (reworded questions we tried on dev
buildings: 0/6 and 1/14 answered in regex mode; 6/6 and 14/14 in hybrid). All 145 test questions match a template,
so both modes write identical replies (checked 2026-10-25).

- `<building_dir>`: one building, or a split directory with one sub-directory per `building_id`.
- Question file: `.jsonl`, `.json` (a list, or `{"questions": [...]}`) or `.csv`; each question needs an id
  (`id` or `question_id`) and its text (`question`), plus `building_id` when the first argument is a split.
- The output extension picks the format. `.json` (our submission): one object per question with `question_id`,
  the full `reply` (ending in the `Answer:` line), `answer`, `kind`, `parser` (`regex`, `llm`, `agent`, or `llm-cache` / `agent-cache` on replay), resolved
  `inputs`, the top-level ids `item_id` (located item), `space_id` (its room, or the answer room), `space_path`
  (the whole route as one ordered list of spaces, stops joined), `element_path`, `length_m` and `reachable`
  (`false` = no route under the question's rules), the solver's structured `result`, and for routing kinds
  `route` = `{optimal_length_m, legs: [{from_space_id, to_space_id, optimal_length_m, space_path,
  element_path}]}` (the kit's warm-up answer format); `error` when unanswered. `--layout dict` writes the same
  objects keyed by question id. `.csv` writes `question_id,answer` with the full replies (the test-set CSV format).
- The answers file is rewritten after every question; a failing question (unknown wording, API error) becomes an
  `error` entry and the run goes on.

How it works: question text → template parser (`core/question_parser.py`, `agent/parsing.py`) → solver per kind
(`core/solvers_v1.py`) → reply with a deterministic `Answer:` line (`agent/answer.py`). Routes are Dijkstra on the
kit's door-to-door route model (`core/building_map.py`). Every number comes from code, not from an LLM.

Unseen wording goes to the LLM parser (`agent/llm_parser.py`), which only fills slots from the building's own
vocabulary: route questions become one spec (start, stops, destination — rooms, room types or items — with any
mix of step-free, forklift, minimum door width and closures), solved by `core/route_query.py` on the same route
model. Questions no solver kind answers go to the solver agent (`agent/solver_agent.py`): Claude computes the
answer with Python over the loaded building and submits it; the `Answer:` line is still written by code.

**Reproducible without an API key:** every model decision (the parser's slots, the agent's submitted answer and
the code it ran) is stored in `llm_cache/decisions.json`, keyed by the building's content, the question text, a
schema version and the provider (OpenAI by default, also with no key).
Re-running the command replays them — no key needed — and reproduces `answers.json`; the
`parser` field then reads `llm-cache` / `agent-cache`. `LLM_CACHE=off` asks the model again.

Kinds covered: `route_query` (combined route constraints), `agent` (solver agent), the benchmark kinds (`largest_room`, `floor_area_total`, `shared_walls_count`, `room_stacked`,
`straight_line_3d`, `errand`, `what_if_door`, `wide_delivery_count`, `step_free_reachable_count`) and the warm-up
kinds (`locate`, `count`, `route`, `route_step_free`, `route_with_closure`, `tour`).

## Our own scores

```bash
PARSER_MODE=regex uv run python -m benchmark.evaluate data/dev --agent agent.answer:answer   # dev 138/138
uv run pytest tests/test_routes.py -q     # 1,338/1,338 train+dev warm-up routes exact (length, space_path, element_path)
uv run pytest tests/test_warm_up.py -q    # warm-up from question text: 2,120/2,130
```

The 10 warm-up misses (and 2 of 517 train benchmark questions) name a room whose name several rooms share, so the
text cannot say which one is meant.

## Second pipeline (kept for comparison)

`agent/run_benchmark.py` → `agent/benchmark_agent.py` → `core/solvers/` gives the same benchmark answers (test set:
same rooms and numbers; solvers 655/655 on gold inputs) with richer `evidence` fields, but has no solvers for the
warm-up kinds (routes, locate, count), so it is not the submission pipeline:

```bash
PARSER_MODE=regex uv run python -m agent.run_benchmark data/test data/test/questions.csv /tmp/answers.json --csv /tmp/answers.csv
PARSER_MODE=regex uv run python -m benchmark.evaluate data/dev --agent agent.benchmark_agent:answer   # 138/138
```
