"""Stage 2 experiment — does Layer B (the repository Survey) earn its place?

    uv run python scripts/experiment_stage2.py --dry-run
    uv run python scripts/experiment_stage2.py --repos requests
    uv run python scripts/experiment_stage2.py --repos requests fastapi --repeats 3

This does not prove the proposed architecture was right. It is built to find out
whether a lightweight, cacheable, goal-agnostic Survey provides enough reusable
repository understanding to justify its cost (H1) — an outcome that includes
"make Layer B much smaller" and "delete Layer B".

Two variables, deliberately separable rather than a full grid:

  EXPLORATION POLICY   A `default`    — the Stage-1 baseline guide
                       B `structural` — prefer symbols/neighbors/search to narrow
                                        the investigation, then read the smallest
                                        range that confirms the hypothesis
  CACHE STRATEGY       `two` / `one`  — conversation cache breakpoints per request

  cells:  (A, two)  baseline
          (B, two)  isolates the POLICY effect against the baseline
          (B, one)  isolates the CACHE effect against (B, two)

Both repositories run on the *same* budget. If a repository cannot produce a
complete survey within it, that is the result — the budget is not raised to make
the run look successful.

Nothing here is wired into the pipeline: this drives backend/repo/survey.py in
isolation, exactly as Stage 1 drove the harness.
"""

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from backend.repo import explore, metrics, survey  # noqa: E402
from backend.repo.explore import Budget  # noqa: E402
from backend.repo.skeleton import build_skeleton  # noqa: E402

load_dotenv(override=True)

# The Windows console defaults to cp1252, which has no box-drawing characters and
# raises rather than degrading. Long experiment runs must not die on a separator.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # already wrapped, or not a real stream
        pass

OUT_DIR = Path("data/experiments")

# One budget for every cell and every repository. Comparability depends on it, and
# so does the honesty of the fastapi result.
# Sized so the *work* can finish, not so the cost lands on a number (§0). The
# first Stage-2 pass used 12 turns to defend the $0.10 figure, and 15/16 runs ran
# out of budget holding a rejected report they had no turns left to repair — the
# cost target became a quality ceiling. These ceilings stop a runaway loop; they
# are not there to ration exploration.
BUDGET = Budget(
    max_turns=18,
    max_tool_calls=120,
    max_result_chars=500_000,
    max_seconds=720.0,
)

CELLS = [
    ("default", "two", explore.TOOL_GUIDE_DEFAULT, 2),
    ("structural", "two", explore.TOOL_GUIDE_STRUCTURAL, 2),
    ("structural", "one", explore.TOOL_GUIDE_STRUCTURAL, 1),
]

REPOS = {
    "requests": "data/repos/requests",
    "fastapi": "data/repos/fastapi",
}

# ── M2 labels: hand-marked, post-hoc, never shown to the model ────────────────
#
# "Does the survey reach the subsystems a competent engineer would call
# essential?" is a judgement, so it is made here once, in the scoring code, and
# applied after the fact. None of this text enters a prompt, the survey schema or
# the exploration seed — a gain that came from telling the model the answer would
# not be a gain in repository exploration.
#
# `fastapi/security` is the regression case: the 80-chunk alphabetical module map
# dropped it silently (P2), and it is the reason the coverage contract exists.
IMPORTANT_SUBSYSTEMS = {
    "requests": ["sessions.py", "adapters.py", "models.py", "auth.py", "api.py"],
    "fastapi": ["security", "routing.py", "dependencies", "applications.py", "params.py"],
}


def _fmt_usd(value: float) -> str:
    return f"${value:.4f}"


def _short(text: str, width: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= width else text[: width - 1] + "…"


# ── scoring that our code can do ──────────────────────────────────────────────


def important_coverage(repo: str, run: survey.SurveyRun) -> dict:
    """M2: were the subsystems a human called essential actually accounted for?"""
    check = run.check
    wanted = IMPORTANT_SUBSYSTEMS.get(repo, [])
    if check is None:
        return {"covered": [], "skipped": [], "missing": wanted}
    covered, skipped, missing = [], [], []
    for name in wanted:
        match = survey._match(survey._name_index(run.skeleton.subsystems()), name)
        if match is None:
            missing.append(f"{name} (not in inventory)")
        elif match in check.coverage.covered:
            covered.append(name)
        elif match in check.coverage.skipped_with_reason:
            skipped.append(f"{name} ({check.coverage.skipped_with_reason[match]})")
        else:
            missing.append(name)
    return {"covered": covered, "skipped": skipped, "missing": missing}


# ── running one cell ──────────────────────────────────────────────────────────


def run_cell(client, repo: str, repo_path: str, policy: str, cache: str,
             guide: str, breakpoints: int, quiet: bool = False):
    skeleton = build_skeleton(repo_path)
    label = f"{repo}/{policy}/{cache}"
    print(f"\n-- {label} " + "-" * max(4, 60 - len(label)))

    def progress(call):
        if quiet:
            return
        mark = " " if call.ok else "!"
        print(f"  {mark} t{call.turn:<2} {call.name:14s} {_short(call.summary, 70)}")

    started = time.time()
    run = survey.run_survey(
        client=client,
        repo_path=repo_path,
        skeleton=skeleton,
        budget=BUDGET,
        tool_guide=guide,
        conversation_breakpoints=breakpoints,
        on_call=progress,
    )
    row = metrics.row(repo, policy, cache, run, explore.MODEL)
    payload = row.as_dict()
    payload["important"] = important_coverage(repo, run)
    payload["survey"] = run.survey
    payload["rejections"] = run.exploration.rejections
    payload["seconds_total"] = time.time() - started

    q, b, c = row.quality, row.behavior, row.cost
    verdict = "ACCEPTED" if q.accepted else ("salvaged" if q.produced else "NO SURVEY")
    print(f"  → {verdict}  stop={row.stop_reason}  rejections={q.rejections}")
    if q.produced and not q.accepted and run.check is not None:
        # Which clause of the contract the returned survey failed. Without this a
        # complete-looking coverage line reads as a pass.
        failed = []
        if run.check.coverage.unaccounted:
            failed.append(f"{len(run.check.coverage.unaccounted)} unaccounted")
        if run.check.unresolved_anchors:
            failed.append(f"{len(run.check.unresolved_anchors)} unresolved anchors")
        if run.check.misfiled:
            failed.append(f"{len(run.check.misfiled)} misfiled")
        if run.check.vacuous:
            failed.append(f"{len(run.check.vacuous)} vacuous")
        print(f"    contract failed on: {', '.join(failed) or 'unknown'}")
        for detail in (run.check.unresolved_anchors + run.check.misfiled)[:4]:
            print(f"      - {_short(detail, 96)}")
    print(f"    coverage   {q.covered} covered / {q.skipped} skipped / "
          f"{q.unaccounted} unaccounted of {q.required_subsystems}")
    print(f"    behaviour  {b.tool_calls} calls  structural {b.structural_share:.0%}  "
          f"{b.source_lines_read} source lines  avg read {b.average_read_lines:.0f}")
    print(f"    cost       {_fmt_usd(c.cost_usd)}  {c.seconds:.0f}s  "
          f"cache {c.cache_hit_rate:.0%}  write {c.cache_write_tokens} / read {c.cache_read_tokens}")
    if payload["important"]["missing"]:
        print(f"    !! MISSING important subsystems: {payload['important']['missing']}")
    if row.errors:
        print(f"    !! errors: {row.errors}")
    return run, payload


# ── reporting ─────────────────────────────────────────────────────────────────


def print_table(rows: list[dict]) -> None:
    print("\n" + "=" * 118)
    print("SIDE BY SIDE")
    print("=" * 118)
    head = (
        f"{'repo':9s} {'policy':11s} {'cache':5s} {'ok':>3s} {'rej':>3s} "
        f"{'cov':>3s} {'skp':>3s} {'unacc':>5s} {'grnd1':>6s} "
        f"{'calls':>5s} {'str%':>5s} {'lines':>6s} {'avg':>4s} "
        f"{'turns':>5s} {'secs':>5s} {'cache%':>6s} {'cost':>9s}"
    )
    print(head)
    print("-" * 118)
    for r in rows:
        q, b, c = r["quality"], r["behavior"], r["cost"]
        print(
            f"{r['repo']:9s} {r['policy']:11s} {r['cache']:5s} "
            f"{'Y' if q['accepted'] else 'n':>3s} {q['rejections']:>3d} "
            f"{q['covered']:>3d} {q['skipped']:>3d} {q['unaccounted']:>5d} "
            f"{q['first_grounding']:>6.0%} "
            f"{b['tool_calls']:>5d} {b['structural_share']:>5.0%} "
            f"{b['source_lines_read']:>6d} {b['average_read_lines']:>4.0f} "
            f"{b['turns']:>5d} {c['seconds']:>5.0f} {c['cache_hit_rate']:>6.0%} "
            f"{c['cost_usd']:>9.4f}"
        )


def _group(rows: list[dict]) -> dict[tuple[str, str, str], list[dict]]:
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for r in rows:
        grouped.setdefault((r["repo"], r["policy"], r["cache"]), []).append(r)
    return grouped


def _values(group: list[dict], section: str, key: str) -> list[float]:
    return [float(r[section][key]) for r in group]


def _stat(group: list[dict], section: str, key: str) -> tuple[float, float, float, int]:
    """(median, min, max, n) — the median resists a single wild run."""
    values = _values(group, section, key)
    if not values:
        return (0.0, 0.0, 0.0, 0)
    return (statistics.median(values), min(values), max(values), len(values))


def _contrast(title: str, subtitle: str, pairs, fields) -> None:
    print("\n" + "=" * 118)
    print(title)
    print(subtitle)
    print("=" * 118)
    for repo, left, right, left_name, right_name in pairs:
        n_left, n_right = len(left), len(right)
        print(f"\n{repo}   ({left_name} n={n_left}  vs  {right_name} n={n_right})")
        if n_left < 2 or n_right < 2:
            print("  ! n<2 in a cell: single runs cannot be separated from run-to-run")
            print("    variance. Treat every delta below as indicative only.")
        for label, section, key, fmt in fields:
            lm, llo, lhi, _ = _stat(left, section, key)
            rm, rlo, rhi, _ = _stat(right, section, key)
            delta = f"   ({(rm - lm) / lm:+.0%})" if lm else ""
            spread = ""
            if n_left > 1 or n_right > 1:
                spread = f"      [{fmt.format(llo)}–{fmt.format(lhi)}] vs [{fmt.format(rlo)}–{fmt.format(rhi)}]"
            print(f"  {label:26s} {fmt.format(lm):>10s} -> {fmt.format(rm):>10s}{delta}{spread}")


BEHAVIOR_FIELDS = [
    ("structural share", "behavior", "structural_share", "{:.0%}"),
    ("read_file calls", "behavior", "read_calls", "{:.0f}"),
    ("source lines read", "behavior", "source_lines_read", "{:.0f}"),
    ("avg read range", "behavior", "average_read_lines", "{:.0f}"),
    ("whole-file reads", "behavior", "whole_file_reads", "{:.0f}"),
    ("outline reads", "behavior", "outline_reads", "{:.0f}"),
    ("tool calls", "behavior", "tool_calls", "{:.0f}"),
    ("subsystems covered", "quality", "covered", "{:.0f}"),
    ("unaccounted", "quality", "unaccounted", "{:.0f}"),
    ("first-submit grounding", "quality", "first_grounding", "{:.0%}"),
    ("flows", "quality", "flows", "{:.0f}"),
    ("widest flow (files)", "quality", "widest_flow_files", "{:.0f}"),
    ("cost", "cost", "cost_usd", "${:.4f}"),
    ("latency", "cost", "seconds", "{:.0f}"),
]

CACHE_FIELDS = [
    # Absolute figures first — but they move with how much a run explored, so the
    # normalised pair underneath is what actually isolates the strategy.
    ("cache write tokens", "cost", "cache_write_tokens", "{:.0f}"),
    ("cache read tokens", "cost", "cache_read_tokens", "{:.0f}"),
    ("prompt tokens", "cost", "prompt_tokens", "{:.0f}"),
    ("output tokens", "cost", "output_tokens", "{:.0f}"),
    ("cache hit rate", "cost", "cache_hit_rate", "{:.0%}"),
    ("total cost", "cost", "cost_usd", "${:.4f}"),
    ("WRITE SHARE of prompt", "cost", "write_share", "{:.1%}"),
    ("COST per 1k prompt tok", "cost", "cost_per_1k_prompt_tokens", "${:.4f}"),
    ("tool calls (confounder)", "behavior", "tool_calls", "{:.0f}"),
    ("subsystems covered", "quality", "covered", "{:.0f}"),
    ("unaccounted", "quality", "unaccounted", "{:.0f}"),
]


def print_contrasts(rows: list[dict]) -> None:
    """The two comparisons the experiment exists to make."""
    grouped = _group(rows)
    repos = sorted({r["repo"] for r in rows})

    policy_pairs = [
        (repo, grouped[(repo, "default", "two")], grouped[(repo, "structural", "two")],
         "default", "structural")
        for repo in repos
        if (repo, "default", "two") in grouped and (repo, "structural", "two") in grouped
    ]
    _contrast(
        "POLICY EFFECT — default vs structural (cache held at two)",
        "Does biasing toward structure reduce raw source consumption without "
        "reducing understanding?",
        policy_pairs, BEHAVIOR_FIELDS,
    )

    cache_pairs = [
        (repo, grouped[(repo, "structural", "two")], grouped[(repo, "structural", "one")],
         "two", "one")
        for repo in repos
        if (repo, "structural", "two") in grouped and (repo, "structural", "one") in grouped
    ]
    _contrast(
        "CACHE EFFECT — two conversation breakpoints vs one (policy held at structural)",
        "Total cost moves with how much a run explored. WRITE SHARE and COST PER "
        "1k PROMPT TOKENS divide that out.",
        cache_pairs, CACHE_FIELDS,
    )


def print_evidence_and_waste(rows: list[dict]) -> None:
    """Accounting vs deep reading, and how much work was repeated."""
    print("\n" + "=" * 118)
    print("EVIDENCE DEPTH — a subsystem 'covered' is not the same as one actually read")
    print("Derived from the trace, not from what the survey claims about itself.")
    print("=" * 118)
    print(f"{'repo':9s} {'policy':11s} {'cache':5s} {'read':>5s} {'outlined':>9s} "
          f"{'named':>6s} {'untouched':>10s}")
    for r in rows:
        ev = r.get("evidence") or {}
        counts = {level: sum(1 for v in ev.values() if v == level)
                  for level in (metrics.READ, metrics.OUTLINED, metrics.NAMED, metrics.UNTOUCHED)}
        print(f"{r['repo']:9s} {r['policy']:11s} {r['cache']:5s} "
              f"{counts[metrics.READ]:>5d} {counts[metrics.OUTLINED]:>9d} "
              f"{counts[metrics.NAMED]:>6d} {counts[metrics.UNTOUCHED]:>10d}")

    print("\n" + "=" * 118)
    print("WASTE — repeated work the run paid for (the only thing §0 permits cutting)")
    print("=" * 118)
    print(f"{'repo':9s} {'policy':11s} {'cache':5s} {'dup calls':>10s} {'overlap rd':>11s} "
          f"{'reread ln':>10s} {'waste %':>8s} {'narrowing %':>12s}")
    for r in rows:
        b = r["behavior"]
        print(f"{r['repo']:9s} {r['policy']:11s} {r['cache']:5s} "
              f"{b['duplicate_calls']:>10d} {b['overlapping_reads']:>11d} "
              f"{b['reread_lines']:>10d} {b['waste_share']:>7.0%} "
              f"{b['narrowing_share']:>11.0%}")

    print("\nTOOL MIX (calls by tool, summed per cell)")
    grouped = _group(rows)
    tools_seen = sorted({t for r in rows for t in r["behavior"]["calls_by_tool"]})
    header = "  " + f"{'cell':28s}" + "".join(f"{t:>15s}" for t in tools_seen)
    print(header)
    for key, group in sorted(grouped.items()):
        cell = "/".join(key)
        totals = [
            sum(r["behavior"]["calls_by_tool"].get(t, 0) for r in group) / len(group)
            for t in tools_seen
        ]
        print("  " + f"{cell:28s}" + "".join(f"{v:>15.1f}" for v in totals))
    print("  (per-run averages. Diagnostic only — a better survey with a different"
          " mix is a good outcome, not a failure.)")


def print_reuse(cell_runs: dict, rows: list[dict]) -> None:
    """What Layer B establishes that Goal Investigation would otherwise redo."""
    print("\n" + "=" * 118)
    print("REUSABLE KNOWLEDGE — what a later Goal Investigation would not have to rediscover")
    print("Facts are counted per run; stability is cross-run agreement. A fact that")
    print("changes every run is not reusable, because nothing downstream could rely on it.")
    print("=" * 118)
    for (repo, policy, cache), group in sorted(cell_runs.items()):
        if policy != "structural" or cache != "two":
            continue
        scores = metrics.reuse(group)
        print(f"\n{repo}  ({len(group)} run(s), structural/two)")
        print(f"  {'category':32s} {'facts':>6s} {'stability':>10s} {'reusable':>9s}")
        for label, score in scores.items():
            print(f"  {label:32s} {score.facts:>6.1f} {score.stability:>9.0%} "
                  f"{score.reusable_facts:>9.1f}")
        total = sum(s.reusable_facts for s in scores.values())
        print(f"  {'TOTAL stability-weighted facts':32s} {'':>6s} {'':>10s} {total:>9.1f}")

    print("\nExploration a cached Survey saves each later session from repeating:")
    for repo in sorted({r["repo"] for r in rows}):
        here = [r for r in rows if r["repo"] == repo]
        print(f"  {repo:9s} {statistics.median([r['behavior']['tool_calls'] for r in here]):.0f} tool calls, "
              f"{statistics.median([r['behavior']['source_lines_read'] for r in here]):.0f} source lines, "
              f"{statistics.median([r['cost']['seconds'] for r in here]):.0f}s, "
              f"{_fmt_usd(statistics.median([r['cost']['cost_usd'] for r in here]))}")


def print_survey(payload: dict) -> None:
    s = payload.get("survey")
    if not s:
        print("  (no survey produced)")
        return
    print(f"\n  architecture: {_short(s.get('architecture'), 300)}")
    print(f"  entry points ({len(s.get('entry_points') or [])}):")
    for e in (s.get("entry_points") or [])[:6]:
        print(f"    {e.get('file')}:{e.get('symbol')} — {_short(e.get('what_it_starts'), 70)}")
    print(f"  core abstractions ({len(s.get('core_abstractions') or [])}):")
    for e in (s.get("core_abstractions") or [])[:8]:
        print(f"    {e.get('file')}:{e.get('symbol')} — {_short(e.get('role'), 70)}")
    for flow in (s.get("flows") or [])[:3]:
        print(f"  flow '{flow.get('name')}':")
        for step in (flow.get("steps") or [])[:8]:
            print(f"    {step.get('file')}:{step.get('symbol')} — "
                  f"{_short(step.get('what_happens'), 62)}")
    print(f"  boundaries ({len(s.get('boundaries') or [])}):")
    for e in (s.get("boundaries") or [])[:5]:
        print(f"    [{e.get('kind')}] {e.get('file')}:{e.get('symbol')} — "
              f"{_short(e.get('note'), 60)}")
    print(f"  testing: {_short(s.get('testing_posture'), 200)}")
    print("  subsystem responsibilities:")
    for e in (s.get("subsystems") or []):
        print(f"    {str(e.get('name')):28s} {_short(e.get('responsibility'), 72)}")
    if s.get("skipped"):
        print("  skipped:")
        for e in s["skipped"]:
            print(f"    {str(e.get('name')):28s} {_short(e.get('reason'), 72)}")


def dry_run() -> int:
    """Everything except the API calls: what would run, and how big the seed is."""
    print("Cells per repository:")
    for policy, cache, _, breakpoints in CELLS:
        print(f"  policy={policy:11s} cache={cache} ({breakpoints} conversation breakpoint(s))")
    print(f"\nBudget (identical for every cell and repository): {BUDGET}")
    for repo, path in REPOS.items():
        if not Path(path).exists():
            print(f"\n{repo}: NOT CLONED at {path}")
            continue
        skeleton = build_skeleton(path)
        inventory = skeleton.subsystems()
        seed = explore.seed_blocks(
            survey.SURVEY_INSTRUCTIONS, skeleton, explore.TOOL_GUIDE_STRUCTURAL
        )
        chars = sum(len(b["text"]) for b in seed)
        print(f"\n{repo}: {len(skeleton.files)} files, {len(skeleton.symbols)} symbols, "
              f"{len(inventory)} subsystems")
        print(f"  seed {chars} chars (~{chars // 4} tokens) — Haiku caches at "
              f"{explore.HAIKU_MIN_CACHEABLE_TOKENS}+")
        index = survey._name_index(inventory)
        for name in IMPORTANT_SUBSYSTEMS.get(repo, []):
            match = survey._match(index, name)
            print(f"  M2 label {name:18s} -> {match or 'NOT IN INVENTORY'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repos", nargs="*", default=["requests"], choices=list(REPOS))
    parser.add_argument("--cells", nargs="*", default=None,
                        help="cells to run, as policy:cache (default: all three)")
    parser.add_argument("--repeats", type=int, default=1,
                        help="runs per cell — n>=2 is what separates an effect from noise")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quiet", action="store_true", help="no per-call progress")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    if args.dry_run:
        return dry_run()

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("ANTHROPIC_API_KEY is not set")
        return 1
    import anthropic

    client = anthropic.Anthropic(api_key=key)

    selected = CELLS
    if args.cells:
        wanted = {tuple(c.split(":")) for c in args.cells}
        selected = [c for c in CELLS if (c[0], c[1]) in wanted]
        if not selected:
            print(f"no cells match {args.cells}; known: "
                  + ", ".join(f"{p}:{c}" for p, c, _, _ in CELLS))
            return 1

    rows: list[dict] = []
    cell_runs: dict[tuple[str, str, str], list[survey.SurveyRun]] = {}

    for repo in args.repos:
        path = REPOS[repo]
        if not Path(path).exists():
            print(f"{repo}: not cloned at {path} — skipped")
            continue
        for policy, cache, guide, breakpoints in selected:
            for attempt in range(max(1, args.repeats)):
                if attempt:
                    print(f"\n(run {attempt + 1} of {args.repeats} for this cell)")
                run, payload = run_cell(client, repo, path, policy, cache, guide,
                                        breakpoints, quiet=args.quiet)
                payload["run"] = attempt + 1
                rows.append(payload)
                cell_runs.setdefault((repo, policy, cache), []).append(run)

    print_table(rows)
    print_contrasts(rows)
    print_evidence_and_waste(rows)
    print_reuse(cell_runs, rows)

    consistency = {}
    for (repo, policy, cache), group in cell_runs.items():
        if len(group) < 2:
            continue
        stats = metrics.consistency(group, explore.MODEL)
        label = f"{repo}/{policy}/{cache}"
        consistency[label] = asdict(stats)
        print(f"\nCONSISTENCY (M10) — {label}, {stats.runs} identical runs")
        print(f"  covered-subsystem overlap : {stats.covered_overlap:.0%}")
        print(f"  cited-anchor overlap      : {stats.anchor_overlap:.0%}")
        print(f"  cost spread               : {_fmt_usd(stats.cost_spread_usd)}")
        print(f"  turn spread               : {stats.turn_spread}")
        rows_here = [r for r in rows
                     if (r["repo"], r["policy"], r["cache"]) == (repo, policy, cache)]
        lines = _values(rows_here, "behavior", "source_lines_read")
        share = _values(rows_here, "behavior", "structural_share")
        print(f"  source lines read         : {min(lines):.0f}–{max(lines):.0f}")
        print(f"  structural share          : {min(share):.0%}–{max(share):.0%}")
        print("  ^ this is the noise floor any policy claim has to clear")

    total = sum(r["cost"]["cost_usd"] for r in rows)
    print("\nCOST - reported, not thresholded (see repo-understanding.md section 0)")
    print(f"  total {_fmt_usd(total)} over {len(rows)} runs, "
          f"mean {_fmt_usd(total / len(rows)) if rows else '$0'}")
    for repo in sorted({r["repo"] for r in rows}):
        here = [r["cost"]["cost_usd"] for r in rows if r["repo"] == repo]
        print(f"  {repo:9s} median {_fmt_usd(statistics.median(here))}  "
              f"range {_fmt_usd(min(here))}-{_fmt_usd(max(here))}"
              f"   (paid once per repo+commit, shared by every later session)")

    for payload in rows:
        if payload.get("repeat"):
            continue
        print("\n" + "=" * 118)
        print(f"SURVEY — {payload['repo']} / {payload['policy']} / {payload['cache']}")
        print("=" * 118)
        print_survey(payload)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = Path(args.out) if args.out else OUT_DIR / f"stage2-{stamp}.json"
    out.write_text(json.dumps({
        "model": explore.MODEL,
        "budget": asdict(BUDGET),
        "cells": [(p, c) for p, c, _, _ in CELLS],
        "rows": rows,
        "consistency": consistency,
        "total_cost_usd": total,
    }, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
