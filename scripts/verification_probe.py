"""M6 / AC2 — is the verification question actually a new application?

    uv run python scripts/verification_probe.py --dry-run
    CODEONBOARD_GAPS=1 uv run python scripts/verification_probe.py

gap-model.md AC2 requires two things and says the second cannot be asserted:

    "the verification prompt is NOT the original prompt (asserted mechanically),
     and a learner still holding the misconception cannot answer it correctly
     (judged live — the one property no assertion can carry)."

This probes the second by answering each generated question TWICE, with answers
authored before any question was seen:

    holding    — expresses the false belief the question is meant to catch.
    corrected  — expresses the true model, in different words from the lesson.

The pass condition is a DOUBLE dissociation, and both halves matter:
    holding   → resolved: false   (the question catches the misconception)
    corrected → resolved: true    (the question is answerable once understood)

A question that fails everything is not a good question, it is an impossible
one — so `corrected` failing is as much a defect as `holding` passing.

Pre-authoring the answers is what makes this evidence rather than a demo: they
cannot be tuned to a question that did not exist when they were written. The
cost is that a `holding` answer may be judged unresolved for the wrong reason —
"didn't address the question" rather than "asserted something false" — so the
rationale is printed for every case and read, not just the verdict.

A third case probes the rule §18.7 calls the most important: with TWO gaps
pending, an answer correct about one and silent about the other must close only
the one it addressed.
"""

import argparse
import copy
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(override=True)

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import anthropic  # noqa: E402

from backend.agents.grader import verification  # noqa: E402
from backend.agents.teaching import verify as teaching_verify  # noqa: E402
from backend.agents.teaching.agent import _read_node_source  # noqa: E402
from backend.learning import store as learning_store  # noqa: E402
from backend.learning.flags import gaps_enabled  # noqa: E402
from backend.learning.gaps import Gap  # noqa: E402
from backend.learning.graph import LearningGraph  # noqa: E402
from backend.pipeline.state import OnboardState  # noqa: E402
from backend.repo.cloner import clone_repo  # noqa: E402

# The FROZEN v2 fixture database, not the live one.
#
# This probe measures against specific stored sessions — its value is that the
# numbers are reproducible against the sessions the phase was measured on. The
# live database moved to schema v3 (`docs/planning/phases/session-reset.md` D8),
# which makes every v2 session invisible to `load_graph`, so pointing here is
# what keeps these fixtures readable rather than merely archived.
DB = Path("data/sessions-fixtures.db")
SESSION = "a3234f413b024fbfb4242917fa34c173"

# Two real nodes, and for each a real gap the Grader opened on it, with the two
# answers authored up front. `holding` must assert the false belief; `corrected`
# must state the true model WITHOUT reusing the lesson's phrasing, so a pass
# cannot be recall.
CASES = [
    {
        "node": "7ecc5fe3",
        "label": "requests/architecture — AuthBase contract",
        "claim": "The auth handler opens the connection so it can read the "
                 "server's challenge.",
        "objective_part": "where connection management lives",
        "holding":
            "The handler is the thing that talks to the server, so it opens the "
            "connection itself, reads back whatever challenge comes down, and "
            "then decides which credentials to attach based on what it saw. That "
            "is why it has to run at that point in the flow — it needs the "
            "server's response in hand before it can build the header.",
        "corrected":
            "Nothing is sent while the handler runs. It is called during "
            "preparation, so all it can do is edit the request object it was "
            "handed — attach a header, change the body — and hand it back. "
            "Anything that needs the server's reply has to happen after the "
            "request goes out, which is somewhere else entirely; a scheme that "
            "genuinely needs the challenge gets invoked a second time once a "
            "response exists.",
    },
    {
        "node": "b50c4cad",
        "label": "requests/component — auth parameter forms",
        "claim": "Tuples passed as auth are sent directly to the server as "
                 "separate fields in the request body.",
        "objective_part": "what a tuple auth argument becomes",
        "holding":
            "The two values go out as their own fields in the body of the "
            "request, so the server reads them the way it would read any posted "
            "form values. Passing an auth object instead is a different mechanism "
            "that puts them in a header, so the two produce different requests "
            "on the wire.",
        "corrected":
            "A two-item tuple is not a separate mechanism — it is shorthand. It "
            "gets turned into the same basic-auth handler you could have passed "
            "yourself, so by the time anything is sent the credentials are an "
            "encoded header and the body is untouched. Both spellings end up "
            "producing an identical request.",
    },
]

# The two-gap case, on the node where the Grader really did open both.
SILENCE_CASE = {
    "node": "7ecc5fe3",
    "label": "requests/architecture — silence must not close a gap",
    "gaps": [
        ("The auth handler opens the connection so it can read the server's "
         "challenge.", "where connection management lives"),
        ("The auth handler returns a fresh Request object that replaces the "
         "original one.", "what the handler returns"),
    ],
    # Correct about the FIRST gap only, and completely silent about the second.
    "answer":
        "Nothing has been sent at the point the handler runs — it is called while "
        "the request is still being prepared, so there is no connection and no "
        "response to look at. All it can do is work on the request object in "
        "front of it.",
}


def load_node(prefix: str):
    graph = learning_store.load_graph(SESSION, DB)
    if graph is None:
        return None, None
    for node_id, node in graph.nodes.items():
        if node_id.startswith(prefix):
            return graph, node
    return graph, None


def fresh(graph, node):
    isolated = LearningGraph(repo_url=graph.repo_url, goal=graph.goal)
    copied = copy.deepcopy(node)
    copied.gap_state.gaps = []
    copied.gap_state.remediation_rounds = 0
    copied.gap_state.pending_verification = None
    isolated.add_node(copied)
    isolated.set_current(copied.id)
    state = OnboardState(repo_url=graph.repo_url, goal=graph.goal)
    state.graph = isolated
    return state, copied


def overlap(a: str, b: str) -> float:
    """Crude content-word overlap, for the mechanical half of AC2."""
    stop = {"the", "a", "an", "and", "or", "of", "to", "in", "is", "it", "what",
            "does", "do", "how", "why", "that", "this", "for", "on", "at", "by",
            "with", "from", "you", "your", "its", "be", "are", "was", "when"}
    wa = {w.strip(".,?!()`'\"").lower() for w in a.split()} - stop
    wb = {w.strip(".,?!()`'\"").lower() for w in b.split()} - stop
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default="docs/planning/phases/evidence/m6-verification")
    args = parser.parse_args()

    if args.dry_run:
        print(f"session {SESSION}")
        for c in CASES:
            print(f"  {c['node']}  {c['label']}")
            print(f"    claim    : {c['claim']}")
        print(f"  {SILENCE_CASE['node']}  {SILENCE_CASE['label']}")
        print("calls: 2 nodes x (1 generate + 2 grade) + 1 x (1 generate + 1 grade) = 8")
        return 0

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY missing", file=sys.stderr)
        return 2
    if not gaps_enabled():
        print("CODEONBOARD_GAPS=1 required", file=sys.stderr)
        return 2

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=180.0)
    line = "─" * 78
    rows = []

    for case in CASES:
        graph, node = load_node(case["node"])
        if node is None:
            print(f"SKIP {case['node']}: not found", file=sys.stderr)
            continue
        source = _read_node_source(clone_repo(graph.repo_url), node)
        original = (node.cached_lesson or {}).get("prompt", "")

        state, working = fresh(graph, node)
        gap = Gap.create("wrong_model", case["claim"],
                         objective_part=case["objective_part"])
        working.gap_state.gaps.append(gap)
        prompt = teaching_verify.verify(state, working, [gap], source, client=client)
        if prompt is None:
            print(f"FAILED to generate for {case['node']}: {state.errors}")
            continue

        print(f"\n{line}\n{case['label']}\n{line}")
        print(f"false belief under test:\n  {case['claim']}\n")
        print(f"ORIGINAL question:\n  {original}\n")
        print(f"VERIFICATION question:\n  {prompt.question}\n")
        sim = overlap(original, prompt.question)
        print(f"  content-word overlap with the original: {sim:.2f}")

        verdicts = {}
        for kind in ("holding", "corrected"):
            vstate, vnode = fresh(graph, node)
            vgap = Gap.create("wrong_model", case["claim"],
                              objective_part=case["objective_part"])
            vnode.gap_state.gaps.append(vgap)
            teaching_verify.store(vnode, teaching_verify.VerificationPrompt(
                question=prompt.question, targets=[vgap.id]))
            result = verification.grade_verification(
                vstate, vnode, case[kind], client=client)
            resolved = vgap.id in result["resolved"]
            verdicts[kind] = {
                "resolved": resolved,
                "status": vgap.status,
                "attempts": vgap.verification_attempts,
                "rationale": result.get("rationale", ""),
            }
            want = "false" if kind == "holding" else "true"
            got = "true" if resolved else "false"
            mark = "PASS" if got == want else "**FAIL**"
            print(f"  {kind:<10} resolved={got:<5} (want {want:<5}) {mark}")
            print(f"             {result.get('rationale', '')[:150]}")

        ok = (not verdicts["holding"]["resolved"]) and verdicts["corrected"]["resolved"]
        print(f"  → double dissociation: {'PASS' if ok else '**FAIL**'}")
        rows.append({
            "node": case["node"], "label": case["label"], "claim": case["claim"],
            "original_question": original, "verification_question": prompt.question,
            "overlap": round(sim, 3), "verdicts": verdicts, "dissociation_ok": ok,
        })

    # ── silence ───────────────────────────────────────────────────────────────
    graph, node = load_node(SILENCE_CASE["node"])
    silence = None
    if node is not None:
        source = _read_node_source(clone_repo(graph.repo_url), node)
        state, working = fresh(graph, node)
        gaps = [Gap.create("wrong_model", c, objective_part=p)
                for c, p in SILENCE_CASE["gaps"]]
        working.gap_state.gaps.extend(gaps)
        prompt = teaching_verify.verify(state, working, [gaps[0]], source, client=client)
        if prompt is not None:
            teaching_verify.store(working, teaching_verify.VerificationPrompt(
                question=prompt.question, targets=[gaps[0].id]))
            result = verification.grade_verification(
                state, working, SILENCE_CASE["answer"], client=client)
            print(f"\n{line}\n{SILENCE_CASE['label']}\n{line}")
            print(f"question:\n  {prompt.question}\n")
            print("answer addresses gap 1 only, and is silent about gap 2.\n")
            for i, gap in enumerate(gaps, 1):
                print(f"  gap {i} [{gap.status:<8}] attempts={gap.verification_attempts}"
                      f"  {gap.claim[:64]}")
            ok = gaps[0].status == "verified" and gaps[1].status == "open"
            print(f"  → silence did not close gap 2: {'PASS' if ok else '**FAIL**'}")
            silence = {
                "question": prompt.question,
                "gap_1": {"claim": gaps[0].claim, "status": gaps[0].status,
                          "attempts": gaps[0].verification_attempts},
                "gap_2": {"claim": gaps[1].claim, "status": gaps[1].status,
                          "attempts": gaps[1].verification_attempts},
                "ok": ok, "rationale": result.get("rationale", ""),
            }

    print(f"\n{'=' * 78}\nAC2 SUMMARY\n{'=' * 78}")
    for row in rows:
        print(f"  {row['label']:<48} dissociation={'PASS' if row['dissociation_ok'] else 'FAIL'}"
              f"  overlap={row['overlap']:.2f}")
    if silence:
        print(f"  {'silence never closes a gap':<48} {'PASS' if silence['ok'] else 'FAIL'}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "verification-cases.json").write_text(
        json.dumps({"cases": rows, "silence": silence}, indent=2), encoding="utf-8")
    print(f"\nwritten: {out / 'verification-cases.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
