"""Stage 0 smoke test — repository-backed anchor resolution on a real checkout.

    uv run python scripts/smoke_stage0.py [repo_path]

Demonstrates the two halves of the Stage-0 migration boundary
(docs/planning/phases/repo-understanding.md §12):

  A. Repository-backed resolution works — file + symbol resolves to an exact
     range, verified against the real files on disk.

  B. Evidence scope is UNCHANGED — a real symbol outside the agent's retrieved
     evidence is now resolvable by the grounding layer, yet is still refused as
     curriculum. Stage 0 improves how we verify anchors; it does not widen what
     the agents may teach from. That only changes at Stage 3.

No LLM calls, no network, no ChromaDB.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.repo import anchors  # noqa: E402
from backend.repo.skeleton import build_skeleton  # noqa: E402


DEFAULT_REPO = "data/repos/requests"


def _rule(title: str) -> None:
    print(f"\n{title}\n{'=' * len(title)}")


def main(repo_path: str) -> int:
    if not Path(repo_path).exists():
        print(f"repo not cloned: {repo_path}")
        return 1

    _rule(f"Layer A — deterministic skeleton for {repo_path}")
    skeleton = build_skeleton(repo_path)
    subsystems = skeleton.subsystems()
    print(f"  files indexed      : {len(skeleton.files)}")
    print(f"  symbols indexed    : {len(skeleton.symbols)}")
    print(f"  source root        : {skeleton.source_root()!r}")
    print(f"  subsystems (OQ7)   : {len(subsystems)}")

    # ── A. successful repository-backed resolution ───────────────────────────
    _rule("A. file + symbol -> resolved exact range -> verified against repository")

    probes = [
        ("Session.send", None),
        ("Session", None),
        ("HTTPBasicAuth", None),
        ("PreparedRequest.prepare", None),
    ]
    resolved_anchors = []
    for symbol, _ in probes:
        found = skeleton.find_symbol(symbol)
        if not found:
            print(f"  {symbol:28s} NOT PRESENT in this repo — skipped")
            continue
        target = found[0]
        res = anchors.resolve(skeleton, target.file, symbol=symbol)
        if not res.ok:
            print(f"  {symbol:28s} REJECTED ({res.reason})")
            continue
        a = res.anchor
        source = skeleton.read_lines(a.file, a.line_start, a.line_end) or ""
        first = source.splitlines()[0].strip() if source else "<empty>"
        print(f"  {symbol:28s} -> {a.file}:{a.line_start}-{a.line_end}")
        print(f"  {'':28s}    verified on disk, first line: {first[:60]}")
        resolved_anchors.append(a)

    _rule("A2. rejections a retrieval-slice check could not make correctly")
    checks = [
        ("nonexistent file", dict(file="requests/teleporter.py", line_start=1, line_end=5)),
        ("nonexistent symbol", dict(file=resolved_anchors[0].file, symbol="Session.teleport")),
        ("range past end of file", dict(file=resolved_anchors[0].file, line_start=99000, line_end=99010)),
        ("inverted range", dict(file=resolved_anchors[0].file, line_start=50, line_end=10)),
    ]
    for label, kwargs in checks:
        res = anchors.resolve(skeleton, **kwargs)
        status = "RESOLVED (unexpected!)" if res.ok else f"rejected: {res.reason}"
        print(f"  {label:28s} -> {status}")

    # Stripped package prefix — the false rejection Stage 0 removes.
    sample = resolved_anchors[0]
    stripped = "/".join(sample.file.split("/")[1:]) or sample.file
    res = anchors.resolve(
        skeleton, stripped, line_start=sample.line_start, line_end=sample.line_end
    )
    print(f"  {'stripped prefix recovery':28s} -> {stripped!r} resolved to "
          f"{res.anchor.file!r}" if res.ok else f"  stripped prefix REJECTED")

    # ── B. migration-boundary preservation ───────────────────────────────────
    _rule("B. real symbol OUTSIDE the retrieved evidence: resolvable, still not curriculum")

    # Simulate what the Mentor actually received: one chunk only.
    shown = resolved_anchors[0]
    evidence = [{
        "file": shown.file,
        "start_line": shown.line_start,
        "end_line": shown.line_end,
        "type": "class",
        "name": shown.symbol or "shown",
        "role": "source",
    }]
    print(f"  evidence given to the agent : {shown.file}:{shown.line_start}-{shown.line_end}")

    outsider = next(
        (a for a in resolved_anchors[1:] if a.file != shown.file),
        resolved_anchors[-1],
    )
    print(f"  candidate anchor            : {outsider.file}:"
          f"{outsider.line_start}-{outsider.line_end} ({outsider.symbol})")

    real = anchors.resolve(
        skeleton, outsider.file,
        line_start=outsider.line_start, line_end=outsider.line_end,
    )
    print(f"    resolve()          -> {'REAL, resolves' if real.ok else 'rejected'}"
          f"  (symbol={real.anchor.symbol if real.ok else None})")

    gated = anchors.resolve_within_evidence(
        skeleton, evidence, outsider.file,
        line_start=outsider.line_start, line_end=outsider.line_end,
    )
    print(f"    within_evidence()  -> {'ALLOWED (BOUNDARY LEAK!)' if gated.ok else f'refused: {gated.reason}'}")

    # And the anchor that WAS shown passes both.
    inside = anchors.resolve_within_evidence(
        skeleton, evidence, shown.file,
        line_start=shown.line_start, line_end=shown.line_end,
    )
    print(f"    shown anchor       -> {'allowed' if inside.ok else f'refused: {inside.reason}'}")

    ok = real.ok and not gated.ok and inside.ok
    _rule("RESULT")
    print("  Stage 0 invariant holds: grounding verifies against the repository,"
          if ok else "  INVARIANT VIOLATED")
    print("  evidence scope is unchanged." if ok else "  investigate before proceeding.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REPO))
