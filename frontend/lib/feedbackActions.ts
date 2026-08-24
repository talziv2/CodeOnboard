import type { RetryOffer } from "@/lib/api";

/**
 * Which actions a verdict offers, and which one is primary.
 *
 * The rule is unchanged and is still the whole content of this module
 * (`ui-direction.md` §2.4):
 *
 *   **the primary is whatever most directly closes the gap between where the
 *   learner is and the objective. Moving on is never primary unless the objective
 *   is met.**
 *
 * ── What changed in M2, and why ───────────────────────────────────────────────
 *
 * This module used to DECIDE whether a retry was possible, from four flags the
 * panel derived from four different slices of the grading reply: `canAnswerAgain`,
 * `checkAvailable`, `canRequestWarmUp`, `warmUpDeclined`. Every defect the
 * learning-loop pass found was a seam between them:
 *
 *   - `canAnswerAgain` was computed, was TRUE after a hint, and the row that read
 *     it was unreachable because `FAILED` short-circuited first. The system wrote
 *     a hint whose prompt forbids it from containing the answer, then removed the
 *     only button that could use it.
 *   - `checkAvailable` could not see a gap's verification budget, so an exhausted
 *     gap was offered and the refusal arrived as an error.
 *   - `warmUpDeclined` was derived two different ways and was wrong on one of
 *     them.
 *
 * None of those flags could be made correct here, because the facts they were
 * approximating are not on this side: gaps and their budgets, the node's
 * remediation rounds, the re-assessment budget, and which questions have already
 * been answered. So the decision moved to `backend/learning/retry.py`, and this
 * module renders `RetryOffer`.
 *
 * **There is now ONE retry action.** `check` and `answerAgain` are gone as
 * separate ids: which mechanism serves *Ask me again* is the backend's business,
 * and a learner asked to choose between "verify a gap" and "re-assess the
 * objective" is being asked to diagnose themselves before they are allowed
 * another go.
 *
 * The warm-up gates stay inputs rather than decisions, exactly as before —
 * offering what would be declined is the bug they exist to prevent.
 */
export type ActionId =
  /** Advance to the next stop on the walk. */
  | "next"
  /**
   * The one retry. A fresh question — about a named misconception, or about the
   * objective — chosen server-side and never shipped with its answer.
   */
  | "askAgain"
  /**
   * Go and read the material this answer rewrote. Only ever offered where there
   * IS rewritten material the learner has not seen.
   */
  | "readMaterial"
  /** Have the Mutator build a prerequisite warm-up. */
  | "warmUp"
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
  /**
   * The server's answer to "what would Ask me again do here". Optional so a
   * client talking to a pre-M2 backend degrades to no retry rather than to a
   * button that 404s.
   */
  retry?: RetryOffer;
  /** A warm-up was spliced in by this reply. */
  warmUpInserted: boolean;
  /** A warm-up was attempted and the backend declined it. */
  warmUpDeclined: boolean;
  /** A warm-up can be offered at all. Panel-owned; never re-derived here. */
  warmUpAvailable: boolean;
  /**
   * A re-teach rewrote this stop's material and the learner has not looked since.
   *
   * THE ONE INPUT THAT IS LEGITIMATELY THE CLIENT'S. Every other decision moved
   * to the server in M2, on the rule that the frontend must not reconstruct what
   * the backend knows — but "have I looked at that tab" is not a fact about
   * understanding and the server cannot observe it. See `lib/materialSeen.ts`.
   *
   * False under the single-column build, where there is nowhere else to go.
   */
  materialUnread?: boolean;
}

const FAILED = ["confused", "off-topic"];

/**
 * Is the objective met?
 *
 * **Not `classification === "understood"`.** That is the latest assessment of one
 * answer; the objective is the node's state, and `understanding_of()` withholds
 * `understood` while any blocking gap is unverified. Reading the assessment as if
 * it were the state is what once returned "Next stop →" as the only action on a
 * `required` stop the server reported `partial`.
 *
 * The server already answers this — `retry.reason === "objective_met"` is exactly
 * it, computed from `understanding_of` — so where the offer is present that is
 * what decides, and the classification is only the pre-M2 fallback.
 */
function objectiveMet(input: ActionInput): boolean {
  if (input.retry) return input.retry.reason === "objective_met";
  return input.classification === "understood";
}

export function feedbackActions(input: ActionInput): ActionPlan {
  const { retry, isCheck, classification, warmUpInserted, warmUpDeclined, warmUpAvailable } =
    input;

  // A warm-up is already in the journey — starting it is the most direct route,
  // and it is more direct than another question about a foundation that is about
  // to be taught.
  if (warmUpInserted) {
    return { primary: "startWarmUp", secondary: "skipWarmUp", tertiary: "moveOn" };
  }

  // Nothing left to do here. `next` leads, and it is the ONLY row where moving on
  // is primary — which is the rule this module exists to hold.
  if (objectiveMet(input)) return { primary: "next" };

  const canRetry = retry?.available ?? false;

  /**
   * Did the most recent graded act show a SHORTFALL?
   *
   * A warm-up remediates confusion, so it is offered only where there is
   * confusion to remediate. Two rows get this wrong if the question is not asked,
   * and both were live:
   *
   *   a check that CLEARED everything — the learner has just positively
   *     demonstrated the corrected model, and offering to step back is the
   *     system disagreeing with the evidence it recorded one line above.
   *     Reported from a real run: "Cleared … what this closed: …" with
   *     "Build me a warm-up" still on the row.
   *   an answer that REACHED the objective while a gap stays open — same
   *     argument: stepping back would be the system disagreeing with its own
   *     grade.
   *
   * On a check the server answers it: `verify` means a blocking gap is still
   * open, so something is still unremediated. `reassess` on that path means
   * everything closed. On an assessment the classification answers it directly —
   * and note that `confused` with no gaps still qualifies, which is §18.11's rule
   * that a confused learner must not be offered FEWER options than a partial one.
   */
  const showedShortfall = isCheck
    ? retry?.mechanism === "verify"
    : classification !== null && classification !== "understood";

  // Never beside a correct answer, never after the backend refused one for this
  // stop, and never where nothing fell short.
  const canWarmUp = warmUpAvailable && !warmUpDeclined && showedShortfall;
  // Whether leaving is the honest second option or an ordinary one. `isCheck` has
  // no classification of its own, and a check that left something open is a
  // shortfall like any other.
  const failed = isCheck || (classification !== null && FAILED.includes(classification));
  const leave: ActionId = failed ? "moveOn" : "next";

  // ── read, then answer ───────────────────────────────────────────────────────
  //
  // A re-teach rewrote the material BECAUSE of this answer, and it names the
  // misconception the answer revealed. Sending the learner straight at another
  // question would let them retry without ever seeing the thing written for them
  // — and worse, the fresh question is built to be fatal to exactly the
  // misconception the unread correction explains, so it sets them up to fail
  // something they were just given the means to get right.
  //
  // GUIDANCE, NOT A GATE. The retry stays on the row, one place down. Nothing is
  // disabled and nothing is hidden: the learner who wants to go straight at it
  // still can, and the ordering only says which we think is more direct. Blocking
  // would be the system deciding they may not know something.
  if (input.materialUnread) {
    return {
      primary: "readMaterial",
      secondary: canRetry ? "askAgain" : leave,
      tertiary: canRetry ? leave : undefined,
    };
  }

  // The objective is unmet and there IS a route to it. Taking it is by definition
  // the most direct thing on offer, whichever mechanism the server picked.
  if (canRetry) {
    return {
      primary: "askAgain",
      secondary: leave,
      tertiary: canWarmUp ? "warmUp" : undefined,
    };
  }

  // Unmet, and nothing can close it right now. A warm-up leads if one is still
  // available — it is slower, but it is the only thing pointing at the objective.
  // Otherwise say plainly that leaving is what is left, rather than dressing it
  // up as an ordinary advance.
  return {
    primary: canWarmUp ? "warmUp" : leave,
    secondary: canWarmUp ? leave : undefined,
  };
}

/** The actions in a plan, in weight order, skipping the ones it does not offer. */
export function plannedActions(plan: ActionPlan): ActionId[] {
  return [plan.primary, plan.secondary, plan.tertiary].filter(Boolean) as ActionId[];
}
