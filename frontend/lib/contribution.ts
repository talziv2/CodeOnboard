import type {
  ChangeBoundary,
  Contribution,
  ContributionStage,
  ScopeCheck,
  SessionGraph,
} from "@/lib/api";

/**
 * The contribution stage's view model — payload in, what a surface renders out.
 *
 * A `lib/` module in the sense `frontend/CLAUDE.md` means: pure functions from
 * the server's payload, with their own tests, and NO learning decision computed
 * here. The gate is `contribution.ready.ready`, the scope verdict is
 * `scope_check.passed`, and the counts are `demonstrated` / `required` — all
 * server-owned. What this file does is decide what is on screen, which is the
 * one thing the client is allowed to decide.
 */

export const STAGES: ContributionStage[] = [
  "plan", "locate", "implement", "validate", "review", "done",
];

/** The stages shown in the OLD in-app stepper. `done` is an outcome, not a step. */
export const VISIBLE_STAGES: ContributionStage[] = STAGES.slice(0, 5);

/**
 * THE CONTRIBUTION FLOW, as it now ends.
 *
 *   Plan -> Locate -> Continue in Claude Code
 *
 * `handoff` is a client-only destination, not a server stage, and deliberately:
 * nothing is stored when a learner reaches it, because nothing has happened yet.
 * `ContributionState.stage` is untouched by this, which is what keeps the old
 * in-app flow working as a fallback while the handoff is being verified.
 *
 * WHY THE FLOW ENDS HERE. CodeOnboard cannot execute, cannot edit a working
 * tree, and cannot open a pull request — `data/repos/<owner>/<name>` is one
 * shared, pinned checkout that the grounding oracle reads. Everything past
 * "write the change" was therefore being simulated, and now goes to a tool that
 * genuinely has those capabilities.
 */
export type StepView = ContributionStage | "handoff";

export const FLOW_STEPS: StepView[] = ["plan", "locate", "handoff"];

/** Where a view sits in the three-step flow. Every old stage past Locate is 2. */
export function flowIndex(view: StepView): number {
  if (view === "handoff") return FLOW_STEPS.length - 1;
  return Math.min(Math.max(stageIndex(view), 0), FLOW_STEPS.length - 1);
}

/** Is this one of the old in-app steps, reachable only as the fallback? */
export function isFallbackStep(view: StepView): boolean {
  return view !== "handoff" && stageIndex(view) >= 2;
}

export function stageIndex(stage: ContributionStage): number {
  const index = STAGES.indexOf(stage);
  return index < 0 ? 0 : index;
}

/**
 * Which phase of the session page is on screen.
 *
 * `learning` and `ready` are both states of a session whose contribution has not
 * started; `stage` means the learner is in it. Deliberately one function rather
 * than three booleans in the page: four flags derived from four slices of one
 * payload is how the lesson panel's seams became defects.
 */
export type ContributionPhase = "none" | "learning" | "ready" | "stage";

export function phaseOf(contribution: Contribution | null): ContributionPhase {
  if (!contribution || !contribution.available) return "none";
  const started = contribution.state != null
    && (contribution.state.plan != null
      || contribution.state.patch.length > 0
      || contribution.state.stage !== "plan");
  if (started) return "stage";
  if (contribution.ready.ready || contribution.state?.proceeded_unready) return "ready";
  return "learning";
}

/**
 * WHICH SURFACE OWNS THE CENTRE COLUMN.
 *
 * Three, and the order of the rules is the whole of the fix:
 *
 *   journey        the lesson and its Understanding tab — the normal product
 *   ready          the gate, when the required set is demonstrated
 *   contribution   Plan → Locate → Implement → Validate → Review
 *
 * THE DEFECT THIS REPLACES. The first version derived the surface from the
 * session alone: `phaseOf(...) === "stage"` put the contribution stage above the
 * lesson branch, with no way back except one button on the final step. So the
 * moment a learner pressed *Start implementing*, the route rail went inert —
 * every stop they clicked still rendered Locate, and the lesson was unreachable
 * for the rest of the session.
 *
 * The mistake was treating "which surface" as a fact about the SESSION. It is a
 * fact about NAVIGATION: selecting a stop is a request to see that stop, and
 * pressing *Start implementing* is a request to see the stage. So an explicit
 * request always wins, and the session state is only the DEFAULT for a learner
 * who has not asked for anything yet.
 *
 * `requested` is genuinely client state — nothing on the server records which of
 * two surfaces someone is looking at, and nothing should. That is the narrow
 * exception D22 already allows for: it decides what is on screen, never what is
 * true about the learner.
 */
export type CentreSurface = "journey" | "ready" | "contribution";

export function centreSurface(
  contribution: Contribution | null,
  requested: "journey" | "contribution" | null,
): CentreSurface {
  // Not a contribution session: there is only ever the journey.
  if (!contribution?.available) return "journey";
  // An explicit request outranks the session's own phase, in both directions.
  if (requested === "journey") return "journey";
  if (requested === "contribution") return "contribution";
  const phase = phaseOf(contribution);
  if (phase === "stage") return "contribution";
  if (phase === "ready") return "ready";
  return "journey";
}

/**
 * Is there an implementation stage to go back to?
 *
 * Drives the one door from the journey into the stage. Without it, a learner who
 * clicks a stop mid-implementation can reach the lesson but never get back —
 * which is the same defect as before, pointing the other way.
 */
export function canResumeContribution(
  contribution: Contribution | null,
  surface: CentreSurface,
): boolean {
  if (!contribution?.available || surface === "contribution") return false;
  return phaseOf(contribution) === "stage";
}

/**
 * Should the quiet override be offered yet?
 *
 * NOT by default, and that is a product decision rather than a styling one: the
 * story is that blocking required knowledge genuinely gates implementation, so
 * an escape hatch on screen from the first stop would undercut the thing being
 * demonstrated.
 *
 * It appears only once the learner has actually WORKED a blocking stop and it
 * has not resolved — a named gap that survived an attempt. Someone who has not
 * yet answered anything is not stuck; they have not started.
 */
export function overrideAvailable(
  contribution: Contribution | null, graph: SessionGraph | null,
): boolean {
  if (!contribution?.available || contribution.ready.ready) return false;
  if (contribution.state?.proceeded_unready) return false;
  const gapBlockers = contribution.ready.blockers.filter((b) => b.reason === "gap");
  if (gapBlockers.length === 0) return false;
  // `attempted` is server-owned ("did they try?") and already on every node, so
  // "they worked it and it did not resolve" needs no second definition here.
  return gapBlockers.some((blocker) =>
    graph?.nodes.some((n) => n.id === blocker.node_id && n.attempted),
  );
}

export interface BoundaryRow {
  file: string;
  symbol: string;
  reason: string;
}

function rows(
  boundary: ChangeBoundary, key: keyof ChangeBoundary, reasonKey: string,
): BoundaryRow[] {
  return (boundary[key] ?? [])
    .filter((e) => e.file)
    .map((e) => ({
      file: String(e.file ?? ""),
      symbol: String(e.symbol ?? ""),
      reason: String((e as Record<string, unknown>)[reasonKey] ?? ""),
    }));
}

export const targetRows = (b: ChangeBoundary) => rows(b, "target", "why_here");
export const forbiddenRows = (b: ChangeBoundary) => rows(b, "must_not_change", "why_not");
export const testRows = (b: ChangeBoundary) => rows(b, "existing_tests", "what_it_guards");

/** The paths a learner is offered as a starting point for a new patch file. */
export function suggestedPaths(boundary: ChangeBoundary): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const row of [...targetRows(boundary), ...testRows(boundary)]) {
    if (row.file && !seen.has(row.file)) {
      seen.add(row.file);
      out.push(row.file);
    }
  }
  return out;
}

/**
 * The Validate surface's rows, in order.
 *
 * A ROW IS OMITTED ONLY WHEN THE CHECK COULD NOT BE MADE, never when it failed —
 * a stage that hides what it could not confirm reads as a pass. The symbol row
 * is the one omission, and it is omitted because the boundary named no target
 * symbol to compare against, so an empty row would be asserting nothing while
 * looking like a result.
 *
 * The tests row is ALWAYS present, always with `tone: "none"`, and never carries
 * a tick: CodeOnboard does not run them, and a stage silent about tests would be
 * read as one that ran them.
 */
export type CheckTone = "pass" | "fail" | "none";

export interface CheckRow {
  key: "scope" | "syntax" | "symbol" | "protected" | "tests" | "execution";
  tone: CheckTone;
  detail: string[];
}

export function checkRows(check: ScopeCheck | null): CheckRow[] {
  if (!check) return [];
  const out: CheckRow[] = [];

  const scopeProblems = [...check.forbidden, ...check.outside_boundary];
  out.push({
    key: "scope",
    tone: check.passed ? "pass" : "fail",
    detail: scopeProblems,
  });

  out.push({
    key: "syntax",
    tone: check.unparseable.length === 0 ? "pass" : "fail",
    detail: check.unparseable,
  });

  if (check.symbol_expected) {
    out.push({
      key: "symbol",
      tone: check.symbol_found ? "pass" : "fail",
      detail: [check.symbol_expected],
    });
  }

  out.push({
    key: "tests",
    tone: check.test_files.length > 0 ? "pass" : "fail",
    detail: check.test_files,
  });

  // ── the two rows that report what did NOT happen ──────────────────────────
  //
  // Last, and adjacent, because they are the same kind of statement and reading
  // them together is what stops either being mistaken for a result. Everything
  // above is a finding; these two are limits.

  // Rendered only when symbol-level constraints actually exist: a "not
  // performed" row on a task with nothing to protect is noise, while never
  // rendering it at all would let a green path result stand for a check nobody
  // made.
  if (check.unchecked_symbols.length > 0) {
    out.push({ key: "protected", tone: "none", detail: check.unchecked_symbols });
  }

  // Never a tick, never conditional, always last.
  out.push({ key: "execution", tone: "none", detail: [] });
  return out;
}

/**
 * THE IMPLEMENTATION SECTION OF THE ROUTE RAIL.
 *
 * The learning route and the implementation stages are TWO PHASES OF ONE
 * JOURNEY, and the rail is where that is said. So the stages are drawn below the
 * chapters, in the same column, rather than the rail collapsing to make room for
 * a second navigation system — which was the alternative, and which would have
 * made implementation read as a different product reached by leaving this one.
 *
 * THESE ARE STILL NOT STOPS, and the shape has to keep saying so. A stop is a
 * pin on a connector carrying an understanding state; nothing here is graded,
 * nothing here is demonstrated, and drawing these with `StatePin` would assert
 * exactly the thing D8 forbids — that writing a patch is evidence of
 * understanding. They get their own container and their own markers.
 *
 * Three statuses, which are the three phases in order:
 *
 *   locked   the learner is still learning — the section is visible and subdued,
 *            so the destination is on screen from the first stop, with the
 *            gate's own counter saying what opens it
 *   ready    every required concept demonstrated, nothing started
 *   active   a stage exists
 *
 * `viewing` is the stage the page is SHOWING, not the server's stage, and it is
 * the same input the stepper inside the stage uses. One source, so the rail
 * cannot highlight one stage while the stepper highlights another.
 */
export type RailStatus = "locked" | "ready" | "active";

export interface RailStage {
  stage: StepView;
  /** `done` is behind you, `current` is on screen, `ahead` is not reachable yet. */
  state: "done" | "current" | "ahead";
  /** Whether clicking it can actually open it. Never true while locked. */
  enterable: boolean;
}

export interface ImplementationRail {
  status: RailStatus;
  stages: RailStage[];
  demonstrated: number;
  required: number;
}

export function implementationRail(
  contribution: Contribution | null,
  viewing: StepView | null,
): ImplementationRail | null {
  if (!contribution?.available) return null;

  const phase = phaseOf(contribution);
  const status: RailStatus =
    phase === "stage" ? "active" : phase === "ready" ? "ready" : "locked";

  // The stepper's rule, verbatim: how far the learner has reached is the
  // furthest of what the server recorded and what they are looking at. `POST
  // /patch` leaves the server on `implement` while Validate is the next thing to
  // do, so the server's stage alone dead-ends them.
  const server = contribution.state?.stage ?? "plan";
  const effective: StepView = viewing ?? server;
  const reached = status === "active"
    ? Math.max(flowIndex(server), flowIndex(effective))
    : -1;

  return {
    status,
    demonstrated: contribution.ready.demonstrated,
    required: contribution.ready.required,
    stages: FLOW_STEPS.map((stage, i) => ({
      stage,
      // `done` is by position, not by outcome: nothing here records a result,
      // and a tick that meant "this went well" would be a claim about the patch.
      // `<= reached`, not `<`: the step the learner is furthest into is behind
      // them once they step back from it. With `<` it rendered as "ahead" while
      // still being clickable — a row that looks unreached and is not.
      state: status !== "active"
        ? "ahead"
        : i === flowIndex(effective)
          ? "current"
          : i <= reached
            ? "done"
            : "ahead",
      enterable: status === "active" && i <= reached,
    })),
  };
}
