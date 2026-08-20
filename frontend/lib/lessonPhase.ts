/**
 * What the lesson is currently DOING, as one derived value.
 *
 * The problem this exists to solve is counted, not felt. Inside the feedback
 * branch of the practice well there are sixteen independent conditional
 * sub-blocks, eleven `<Button>` call sites of which one to four render at once,
 * and twenty-one distinct copy strings — and around them the setup prose, the
 * trace path, the gap list, the attempt history and the reveal with its two
 * callouts. The reason it reads as busy is not spacing: it is that presentation
 * is keyed off many independent flags instead of off one state. That is the same
 * failure D2b exposed at a smaller scale, where a working backend produced a
 * silent UI because two flags disagreed about who was rendering.
 *
 * So the first step is to name the states. There are four, and every one of the
 * thirteen situations the plan enumerates lands in one of them:
 *
 *   STUDY     nothing has been graded on screen. Covers a fresh arrival AND a
 *             revisit — a returning learner has attempts but no `result`, and is
 *             reading rather than being tested, which is why `revealed` is true
 *             for them while the phase is still STUDY. Reveal is orthogonal to
 *             phase; do not fold it in.
 *
 *   FEEDBACK  an assessment verdict is on screen. This is the crowded one: every
 *             classification, every adaptation (hint, re-teach, prune, warm-up
 *             inserted, warm-up declined) and the pending-attempt path are all
 *             THIS ONE PHASE. Naming that is the point — the variants are
 *             content within a state, not states.
 *
 *   VERIFY    a verification question is outstanding and unanswered. Requesting
 *             one clears `result`, so this phase never coexists with a verdict;
 *             that is what keeps a single composer on screen.
 *
 *   RESOLVED  a verification has come back. Distinct from FEEDBACK because the
 *             backend returns `classification: null` here on purpose — a check is
 *             evidence about named beliefs, not a re-grade of the objective — so
 *             every branch that keys off `classification` is silent, and the
 *             panel must read `resolved` / `unresolved` instead. Collapsing this
 *             into FEEDBACK is precisely the bug D2b fixed.
 *
 * L1 introduces this and nothing consumes it. `L4` is where rendering keys off
 * it, and where §3a's open questions get answered — what belongs on screen after
 * a correct answer, whether adaptation notices belong to the feedback or to the
 * adaptation channel, whether gaps collapse to a counter the moment a verdict
 * lands. Those are decisions about which phase owns which information, and they
 * cannot be made until the phases have names.
 */
export type LessonPhase = "STUDY" | "FEEDBACK" | "VERIFY" | "RESOLVED";

/**
 * The two pieces of state that decide the phase.
 *
 * Deliberately narrow. `attempts`, `node` and `graph` shape what a phase
 * CONTAINS — how many attempts to list, which gaps are open, whether recovery
 * happened — but none of them changes which phase it is. Taking them here would
 * invite exactly the coupling this replaces.
 */
export interface PhaseState {
  /**
   * The last reply from the server, or null/undefined. A reply to a verification
   * carries `kind: "verification"`; an assessment carries no `kind` (or
   * "assessment").
   *
   * `unknown` rather than a shape, and that is deliberate rather than lazy. This
   * module reads exactly ONE optional field off an opaque reply, and every
   * narrower signature was worse: `{ kind?: string | null }` is a weak type, so
   * TypeScript rejects any literal without `kind` — which is every assessment,
   * the common case — and adding an index signature to fix that then rejects
   * `RespondResult`, because interfaces are not assignable to indexed types. So
   * the parameter says what it means: something arrived, and this looks at one
   * field of it.
   */
  result: unknown;
  /** An outstanding verification question, or null once answered or dismissed. */
  verification: unknown;
}

/** A reply that is a check on named beliefs rather than a grade of the objective. */
export function isCheckResult(result: unknown): boolean {
  return (
    typeof result === "object" &&
    result !== null &&
    (result as { kind?: unknown }).kind === "verification"
  );
}

export function lessonPhase({ result, verification }: PhaseState): LessonPhase {
  // Outstanding question first. The two are mutually exclusive in practice —
  // requesting a verification clears `result` and answering it clears
  // `verification` — but the ordering is stated rather than assumed, because a
  // future path that set both would otherwise silently render a verdict over an
  // unanswered question, which is the two-composer bug wearing a new hat.
  if (verification !== null && verification !== undefined) return "VERIFY";
  if (isCheckResult(result)) return "RESOLVED";
  if (result !== null && result !== undefined) return "FEEDBACK";
  return "STUDY";
}

/**
 * Whether the learner is being asked something right now.
 *
 * True in the two phases that own a question, false in the two that own a
 * report. This is the distinction the single-composer invariant rests on, and
 * naming it here is what will let `L4` stop re-deriving it from flag pairs.
 */
export function isAsking(phase: LessonPhase): boolean {
  return phase === "STUDY" || phase === "VERIFY";
}
