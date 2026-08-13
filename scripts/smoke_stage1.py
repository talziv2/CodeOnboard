"""Stage 1 smoke test — the tool layer and the budgeted exploration harness.

    uv run python scripts/smoke_stage1.py [repo_path] [--live] [--turns N]
    uv run python scripts/smoke_stage1.py --live --goal "understand authentication"

Two halves, matching docs/planning/phases/repo-understanding.md §12 Stage 1:

  A. THE TOOLS (default, offline). Exercises all six primitives against a real
     checkout and prints what each returns. No LLM, no network, no API key.

  B. THE LOOP (--live, costs money). Runs one real exploration on Haiku and
     reports the M8/M9/H6 numbers the evaluation plan asks for: wall clock,
     tokens, cache hit ratio, USD, and the full tool trace.

Stage 1 wires nothing into the pipeline, so this script is the only caller of
backend/repo/explore.py. Its purpose is to make the harness's behaviour — and
its cost — observable before any agent depends on it.
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from backend.repo import explore, tools  # noqa: E402
from backend.repo.skeleton import build_skeleton  # noqa: E402

load_dotenv(override=True)   # ANTHROPIC_API_KEY lives in .env, as elsewhere

DEFAULT_REPO = "data/repos/requests"

# Stage 2 will own the real survey brief. This is deliberately a thin stand-in:
# enough to make the loop do recognisable work, not a prompt anyone should
# inherit. The coverage contract (D13) is not enforced here — that lands with
# the Survey.
INSTRUCTIONS = """\
You are surveying an unfamiliar Python repository so that someone can be taught
how it works. You have the complete file and subsystem inventory below; you do
not need to discover what exists, only what it means.

Establish, with evidence you have actually read:
  - the repository's main entry points, and what a caller does first
  - the two or three core abstractions everything else routes through
  - one end-to-end flow across at least three files
  - for each claim, a file and symbol you verified with propose_anchor

Stop when you can state those things. Prefer depth on what matters over a tour
of everything."""


def _rule(title: str) -> None:
    print(f"\n{title}\n{'=' * len(title)}")


def _show(label: str, result: dict, *, lines: int = 6) -> None:
    """Print a tool result the way the harness renders it for the model."""
    if not result.get("ok"):
        print(f"  {label:34s} rejected: {result['error']} — {result['detail']}")
        return
    text, summary = explore._render(label.split("(")[0].strip(), result)
    print(f"  {label:34s} {summary}")
    for line in text.splitlines()[1:lines + 1]:
        print(f"  {'':34s} | {line[:96]}")


# ── A. the tool layer ─────────────────────────────────────────────────────────


def check_tools(repo_path: str) -> bool:
    _rule(f"Layer A — deterministic skeleton for {repo_path}")
    skeleton = build_skeleton(repo_path)
    subsystems = skeleton.subsystems()
    print(f"  files indexed   : {len(skeleton.files)}")
    print(f"  symbols indexed : {len(skeleton.symbols)}")
    print(f"  subsystems      : {len(subsystems)}")

    _rule("1. list_files — what is here, with metadata that comes free")
    _show("list_files (source)", tools.list_files(repo_path, role="source", limit=8, skeleton=skeleton))
    _show("list_files (tests)", tools.list_files(repo_path, role="test", limit=4, skeleton=skeleton), lines=4)

    _rule("2. symbols — what is defined, and exactly where")
    biggest = max(
        (f for f in skeleton.files.values() if f.role == "source"),
        key=lambda f: f.symbol_count, default=None,
    )
    if biggest is None:
        print("  no source files indexed — nothing to survey")
        return False
    print(f"  densest source file: {biggest.path} ({biggest.symbol_count} symbols)")
    _show("symbols (one file)", tools.symbols(repo_path, path=biggest.path, limit=8, skeleton=skeleton))
    _show("symbols (classes)", tools.symbols(repo_path, kind="class", limit=6, skeleton=skeleton))

    target = next(
        (s for s in skeleton.symbols if s.role == "source" and s.kind == "function"
         and s.parent and s.line_count > 3),
        skeleton.symbols[0],
    )
    print(f"\n  probe symbol: {target.qualified_name} in {target.file}")

    _rule("3. read_file — bounded, line-numbered, outline when too long")
    _show(
        "read_file (a symbol's range)",
        tools.read_file(repo_path, target.file, start=target.line_start,
                        end=min(target.line_end, target.line_start + 8), skeleton=skeleton),
        lines=9,
    )
    _show("read_file (whole file)", tools.read_file(repo_path, target.file, skeleton=skeleton), lines=4)
    _show(
        "read_file (over the cap)",
        tools.read_file(repo_path, target.file, start=1, end=tools.MAX_READ_LINES + 1,
                        skeleton=skeleton),
    )
    stripped = target.file.split("/", 1)[-1] if "/" in target.file else target.file
    _show(
        f"read_file ({stripped!r})",
        tools.read_file(repo_path, stripped, start=1, end=2, skeleton=skeleton), lines=2,
    )

    _rule("4. search_code — where does this text appear")
    _show("search_code (the symbol)", tools.search_code(repo_path, rf"\b{target.name}\b", max_results=6))
    _show("search_code (raise sites)", tools.search_code(repo_path, r"raise \w+Error", glob="*.py", max_results=4))
    _show("search_code (bad regex)", tools.search_code(repo_path, "(unclosed"))

    _rule("5. neighbors — what is this connected to")
    _show(
        "neighbors (all relations)",
        tools.neighbors(repo_path, target.qualified_name, file=target.file, limit=12,
                        skeleton=skeleton),
        lines=12,
    )
    _show("neighbors (unknown symbol)", tools.neighbors(repo_path, "Teleporter", skeleton=skeleton))

    _rule("6. propose_anchor — is this citation real")
    verified = tools.propose_anchor(
        repo_path, target.file, symbol=target.qualified_name, skeleton=skeleton
    )
    _show("propose_anchor (symbol)", verified)
    _show(
        "propose_anchor (invented symbol)",
        tools.propose_anchor(repo_path, target.file, symbol="teleport", skeleton=skeleton),
    )
    _show(
        "propose_anchor (range past EOF)",
        tools.propose_anchor(repo_path, target.file, line_start=99000, line_end=99010,
                             skeleton=skeleton),
    )

    _rule("Dispatch — a bad call is a result, not a crash")
    for name, kwargs in [
        ("semantic_search", {"query": "auth"}),
        ("read_file", {"filepath": target.file}),
        ("read_file", {"path": "../../../etc/passwd"}),
    ]:
        outcome = tools.run_tool(name, repo_path, **kwargs)
        print(f"  {name:16s} {str(kwargs)[:44]:46s} -> {outcome['error']}")

    ok = verified.get("ok") and verified["symbol"] == target.qualified_name
    print(f"\n  tool layer: {'OK' if ok else 'FAILED'}")
    return bool(ok)


# ── B. the exploration loop ───────────────────────────────────────────────────

SURVEY = explore.ReportSpec(
    name="submit_survey",
    description="Submit the finished survey. Call this once, when your findings are complete.",
    input_schema={
        "type": "object",
        "properties": {
            "entry_points": {
                "type": "array",
                "items": {"type": "string"},
                "description": "How a caller enters this system, as file:symbol.",
            },
            "core_abstractions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "file": {"type": "string"},
                        "why_it_matters": {"type": "string"},
                    },
                    "required": ["symbol", "file", "why_it_matters"],
                },
            },
            "flow": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "step": {"type": "integer"},
                        "file": {"type": "string"},
                        "symbol": {"type": "string"},
                        "what_happens": {"type": "string"},
                    },
                    "required": ["step", "file", "symbol", "what_happens"],
                },
                "description": "One end-to-end flow, ordered, across at least three files.",
            },
            "not_covered": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Subsystems you did not investigate, and why.",
            },
        },
        "required": ["entry_points", "core_abstractions", "flow", "not_covered"],
    },
)


def run_loop(repo_path: str, goal: str, turns: int) -> bool:
    import anthropic

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("  ANTHROPIC_API_KEY is not set — cannot run the live half")
        return False

    skeleton = build_skeleton(repo_path)
    seed = explore.seed_blocks(INSTRUCTIONS, skeleton)
    seed_chars = sum(len(b["text"]) for b in seed)
    _rule(f"Layer B/C harness — live exploration of {repo_path}")
    print(f"  model           : {explore.MODEL}")
    print(f"  seed            : {seed_chars} chars (~{seed_chars // 4} tokens) in {len(seed)} blocks")
    if seed_chars // 4 < explore.HAIKU_MIN_CACHEABLE_TOKENS:
        print(f"  NOTE            : the seed is below Haiku's {explore.HAIKU_MIN_CACHEABLE_TOKENS}-token"
              " cache minimum, so the seed breakpoint alone will not cache.")
        print("                    The conversation breakpoints still do, once tool"
              " results push the prefix past the minimum (H6).")
    print(f"  task            : {goal}")

    budget = explore.Budget(max_turns=turns)
    print(f"  budget          : {budget.max_turns} turns, {budget.max_tool_calls} calls, "
          f"{budget.max_result_chars} result chars, {budget.max_seconds:.0f}s\n")

    def progress(call) -> None:
        mark = " " if call.ok else "!"
        print(f"  {mark} turn {call.turn:>2}  {call.name:15s} {call.summary[:78]}")

    result = explore.explore(
        client=anthropic.Anthropic(api_key=key),
        repo_path=repo_path,
        instructions=INSTRUCTIONS,
        task=goal,
        skeleton=skeleton,
        report=SURVEY,
        budget=budget,
        on_call=progress,
    )

    _rule("Result")
    print(f"  stop reason     : {result.stop_reason}"
          f"{'  (partial, by design)' if result.budget_exhausted else ''}")
    print(f"  turns           : {result.turns}")
    print(f"  tool calls      : {len(result.trace)}"
          f"  ({sum(1 for c in result.trace if not c.ok)} rejected)")
    print(f"  tool output     : {result.result_chars} chars")

    _rule("M8 latency / M9 cost / H6 caching")
    usage = result.usage
    print(f"  wall clock      : {result.seconds:.1f}s over {usage.api_calls} API calls")
    print(f"  input tokens    : {usage.input_tokens}")
    print(f"  output tokens   : {usage.output_tokens}")
    print(f"  cache write     : {usage.cache_creation_input_tokens}")
    print(f"  cache read      : {usage.cache_read_input_tokens}")
    print(f"  cache hit ratio : {usage.cache_hit_ratio:.0%}")
    cost = usage.cost_usd(explore.MODEL)
    print(f"  cost            : ${cost:.4f}   (${0.10:.2f}/run target — "
          f"{'within' if cost <= 0.10 else 'OVER'})")

    if result.errors:
        _rule("Errors")
        for message in result.errors:
            print(f"  {message}")

    if result.output:
        _rule("Survey (validated against the report schema)")
        for entry in result.output.get("entry_points", []):
            print(f"  entry     {entry}")
        for item in result.output.get("core_abstractions", []):
            print(f"  core      {item.get('symbol')} — {item.get('file')}")
            print(f"            {str(item.get('why_it_matters'))[:88]}")
        for step in result.output.get("flow", []):
            print(f"  flow {step.get('step')}    {step.get('file')}:{step.get('symbol')}"
                  f" — {str(step.get('what_happens'))[:60]}")
        for skipped in result.output.get("not_covered", []):
            print(f"  skipped   {skipped}")

        _rule("Grounding — every cited anchor re-verified independently")
        cited = [
            (item.get("file"), item.get("symbol"))
            for item in result.output.get("core_abstractions", [])
        ] + [
            (step.get("file"), step.get("symbol"))
            for step in result.output.get("flow", [])
        ]
        resolved = 0
        for file, symbol in cited:
            if not file or not symbol:
                continue
            check = tools.propose_anchor(repo_path, file, symbol=symbol, skeleton=skeleton)
            if check["ok"]:
                resolved += 1
                print(f"  ok      {file}:{check['line_start']}-{check['line_end']}  {symbol}")
            else:
                print(f"  FAILED  {file}  {symbol} — {check['error']}")
        if cited:
            print(f"\n  M5 grounding accuracy: {resolved}/{len(cited)} anchors resolve")
    elif result.text:
        _rule("Prose (no structured report was submitted)")
        print(result.text[:1200])

    return result.output is not None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_path", nargs="?", default=DEFAULT_REPO)
    parser.add_argument("--live", action="store_true",
                        help="run one real exploration (costs money)")
    parser.add_argument("--turns", type=int, default=8, help="turn budget for --live")
    parser.add_argument("--goal", default="Survey this repository for a new contributor.")
    args = parser.parse_args()

    if not Path(args.repo_path).exists():
        print(f"repo not cloned: {args.repo_path}")
        return 1

    ok = check_tools(args.repo_path)
    if args.live:
        ok = run_loop(args.repo_path, args.goal, args.turns) and ok
    else:
        _rule("The loop")
        print("  skipped — pass --live to run one real exploration (needs ANTHROPIC_API_KEY)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
