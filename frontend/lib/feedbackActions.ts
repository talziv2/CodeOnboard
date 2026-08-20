/**
 * Which actions a verdict offers, and which one is primary.
 *
 * The feedback row could show four equally weighted buttons, so it said nothing
 * about what to do next. `ui-direction.md` §2.4 fixes that with one rule:
 *
 *   **the primary is whatever most directly closes the gap between where the
 *   learner is and the objective. Moving on is never primary unless the objective
 *   is met.**
 *
 * That rule is the whole content of this module, and it is a pure function because
 * the table it generates has six rows plus the check path, and a six-row table
 * expressed as nested JSX conditionals is how the sixteen-conditional feedback
 * branch got that way in the first place.
 *
 * Two gates from §3 are inputs rather than decisions made here, because the panel
 * owns them: `warmUpAvailable` encodes the Mutator's one-per-node cap and the
 * §18.11 rule that a `confused` learner must not get FEWER options than a `partial`
 * one, and `canAnswerAgain` encodes whether a retry is live at all. Offering what
 * would be declined is the bug those flags exist to prevent, so this never
 * re-derives them.
 *
 * Both bugs the exhaustive sweep in the test file caught were of exactly that kind:
 * `next` became primary with a gap still open by falling through the tail, and the
 * check path offered a warm-up without consulting the gate at all.
 */
export type ActionId =
  /** Advance to the next stop on the walk. */
  | "next"
  /** Ask a NEW question about the same misconception — not a re-ask. */
  | "check"
  /** Have the Mutator build a prerequisite warm-up. */
  | "warmUp"
  /** Clear the verdict and answer the same question again. */
  | "answerAgain"
  /** Begin the warm-up that was just inserted. */
  | "startWarmUp"
  /** Leave the inserted warm-up unvisited and continue here. */
  | "skipWarmUp"
  /** Move on without reaching the objective. */
  | "moveOn";

export interface ActionPlan {
  primary: ActionId;
  secondary?: ActionId;
  tertiary?: ActionId;
}

export interface ActionInput {
  /** Null on a check: the backend does not re-grade the objective there. */
  classification: string | null;
  /** This reply is a verification result rather than an assessment. */
  isCheck: boolean;
  openGapCount: number;
  /** A warm-up was spliced in by this reply. */
  warmUpInserted: boolean;
  /** A warm-up was attempted and the backend declined it. */
  warmUpDeclined: boolean;
  /**
   * A warm-up can be offered at all.
   *
   * ONE gate, computed by the panel, because the two paths reach it differently:
   * `canRequestWarmUp` covers the assessment path (and already encodes the
   * Mutator's one-per-node cap and §18.11), while on a CHECK that flag is false by
   * construction and a warm-up is still deliberately reachable while something is
   * unresolved. Passing the union means this module never has to know which path it
   * is on to obey "never offer what would be declined" — which it broke when it had
   * to remember.
   */
  warmUpAvailable: boolean;
  /** The panel's gate: answering again is live. */
  canAnswerAgain: boolean;
}

const FAILED = ["confused", "off-topic"];

export function feedbackActions({
  classification,
  isCheck,
  openGapCount,
  warmUpInserted,
  warmUpDeclined,
  warmUpAvailable,
  canAnswerAgain,
}: ActionInput): ActionPlan {
  // A check first, because `classification` is null on this path and every test
  // below it would fall through. What most directly closes the gap after a check is
  // another check while anything is still open; otherwise the objective is met and
  // moving on becomes legitimate.
  if (isCheck) {
    if (openGapCount > 0) {
      return {
        primary: "check",
        secondary: "next",
        tertiary: warmUpAvailable && !warmUpInserted ? "warmUp" : undefined,
      };
    }
    return { primary: "next" };
  }

  // The objective is met: this is the one row where moving on is primary.
  if (classification === "understood") {
    return { primary: "next" };
  }

  // A warm-up is already in the journey — starting it is the most direct route.
  if (warmUpInserted) {
    return { primary: "startWarmUp", secondary: "skipWarmUp", tertiary: "moveOn" };
  }

  // Asked for and refused. Do not offer it again; a check is what is left.
  if (warmUpDeclined) {
    return {
      primary: canAnswerAgain && openGapCount > 0 ? "check" : "moveOn",
      secondary: canAnswerAgain && openGapCount > 0 ? "moveOn" : undefined,
    };
  }

  const failed = classification !== null && FAILED.includes(classification);

  // Something is named and still open: closing it is more direct than anything
  // else on offer, and a check asks a NEW question about it rather than re-asking
  // the one whose answer the reveal has already given away.
  if (openGapCount > 0 && canAnswerAgain) {
    return {
      primary: "check",
      secondary: failed ? "moveOn" : "next",
      tertiary: warmUpAvailable ? "warmUp" : undefined,
    };
  }

  // Partly there with nothing named. Another attempt at the same question is
  // meaningful here precisely because there is no gap for a check to target.
  if (!failed && canAnswerAgain) {
    return {
      primary: "next",
      secondary: "answerAgain",
      tertiary: warmUpAvailable ? "warmUp" : undefined,
    };
  }

  // Failed, nothing named, no retry: a warm-up is the only route back toward the
  // objective, so it leads even though it is slower.
  if (failed) {
    return {
      primary: warmUpAvailable ? "warmUp" : "moveOn",
      secondary: warmUpAvailable ? "moveOn" : undefined,
    };
  }

  // A gap is named and nothing on offer can close it — no retry, and the warm-up
  // is either used up or unavailable. Then there is genuinely nothing more direct
  // than leaving, and saying so beats pretending otherwise. Reached explicitly
  // rather than by falling through, which is how `next` briefly became primary
  // with a gap still open.
  if (openGapCount > 0) {
    return {
      primary: warmUpAvailable ? "warmUp" : "moveOn",
      secondary: warmUpAvailable ? "moveOn" : undefined,
    };
  }

  return { primary: "next", tertiary: warmUpAvailable ? "warmUp" : undefined };
}

/** The actions in a plan, in weight order, skipping the ones it does not offer. */
export function plannedActions(plan: ActionPlan): ActionId[] {
  return [plan.primary, plan.secondary, plan.tertiary].filter(Boolean) as ActionId[];
}
