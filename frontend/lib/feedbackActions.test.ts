import { describe, expect, test } from "vitest";
import { feedbackActions, plannedActions, type ActionInput } from "@/lib/feedbackActions";

/**
 * The verdict branch table, row by row.
 *
 * `ui-direction.md` §2.4's rule is that the primary is whatever most directly
 * closes the gap between where the learner is and the objective, and that moving on
 * is never primary unless the objective is met. Both halves are asserted here — the
 * second one globally, because it is the claim most easily broken by a later edit.
 */

const base: ActionInput = {
  classification: "partial",
  isCheck: false,
  openGapCount: 0,
  warmUpInserted: false,
  warmUpDeclined: false,
  warmUpAvailable: true,
  canAnswerAgain: true,
  checkAvailable: true,
};

describe("the table", () => {
  test("understood with nothing outstanding: moving on is primary", () => {
    expect(feedbackActions({ ...base, classification: "understood" })).toEqual({
      primary: "next",
    });
  });

  // ── S0 defect 2 ─────────────────────────────────────────────────────────────
  test("understood with a gap still open: the check leads, because only it can close it", () => {
    // Observed live on a `required` stop the server reported `partial`: the whole
    // action row was "Next stop →". Verification is the only caller of
    // `Gap.mark_verified`, so the one thing that could close the gap was the one
    // thing not offered, and the learner was shown "1 unresolved" beside a single
    // button that walked away from it.
    const plan = feedbackActions({ ...base, classification: "understood", openGapCount: 1 });
    expect(plan.primary).toBe("check");
    expect(plan.secondary).toBe("next");
    // Not a warm-up: this answer REACHED the objective. Stepping back would be the
    // system disagreeing with its own grade.
    expect(plannedActions(plan)).not.toContain("warmUp");
  });

  test("understood with a gap open but nothing verifiable: moving on, and it says so", () => {
    // The node's remediation cap has fired or every gap is exhausted, so `/verify`
    // would 409. Offering a check we know would be refused is the same defect as
    // offering a declined warm-up.
    const plan = feedbackActions({
      ...base,
      classification: "understood",
      openGapCount: 1,
      checkAvailable: false,
    });
    expect(plan).toEqual({ primary: "next" });
  });

  test("a check is offered on the strength of open gaps, not of `canAnswerAgain`", () => {
    // `canAnswerAgain` means "the system invited another attempt at the same
    // question" — true only for hint/followup/reteach, and false for `understood`,
    // which is exactly where verification is most clearly the right act. Gating the
    // check on it made the correct action unreachable precisely when it was correct.
    const plan = feedbackActions({
      ...base,
      classification: "understood",
      openGapCount: 1,
      canAnswerAgain: false,
    });
    expect(plan.primary).toBe("check");
  });

  test("partial with a gap open: a check leads", () => {
    const plan = feedbackActions({ ...base, classification: "partial", openGapCount: 1 });
    expect(plan.primary).toBe("check");
    expect(plan.secondary).toBe("next");
    expect(plan.tertiary).toBe("warmUp");
  });

  test("partial with nothing named: answering again is offered, not led with", () => {
    const plan = feedbackActions({ ...base, classification: "partial", openGapCount: 0 });
    expect(plan.primary).toBe("next");
    expect(plan.secondary).toBe("answerAgain");
  });

  test("confused with a warm-up inserted: starting it leads", () => {
    const plan = feedbackActions({
      ...base,
      classification: "confused",
      warmUpInserted: true,
      openGapCount: 1,
    });
    expect(plan).toEqual({ primary: "startWarmUp", secondary: "skipWarmUp", tertiary: "moveOn" });
  });

  test("confused with a gap and no warm-up yet: a check leads, moving on is secondary", () => {
    const plan = feedbackActions({ ...base, classification: "confused", openGapCount: 2 });
    expect(plan.primary).toBe("check");
    expect(plan.secondary).toBe("moveOn");
    expect(plan.tertiary).toBe("warmUp");
  });

  test("confused with nothing named: the warm-up leads, slow as it is", () => {
    const plan = feedbackActions({
      ...base,
      classification: "confused",
      openGapCount: 0,
      canAnswerAgain: false,
    });
    expect(plan.primary).toBe("warmUp");
    expect(plan.secondary).toBe("moveOn");
  });

  test("warm-up declined by the backend: never offered again", () => {
    const plan = feedbackActions({
      ...base,
      classification: "confused",
      warmUpDeclined: true,
      openGapCount: 1,
    });
    expect(plannedActions(plan)).not.toContain("warmUp");
    expect(plan.primary).toBe("check");
  });

  test("off-topic behaves as confused, not as its own thing", () => {
    const a = feedbackActions({ ...base, classification: "confused", openGapCount: 1 });
    const b = feedbackActions({ ...base, classification: "off-topic", openGapCount: 1 });
    expect(b).toEqual(a);
  });
});

describe("the check path, where classification is null", () => {
  test("something still open: another check leads", () => {
    const plan = feedbackActions({ ...base, classification: null, isCheck: true, openGapCount: 1 });
    expect(plan.primary).toBe("check");
    expect(plan.secondary).toBe("next");
  });

  test("nothing left open: moving on, and nothing else", () => {
    const plan = feedbackActions({ ...base, classification: null, isCheck: true, openGapCount: 0 });
    expect(plan).toEqual({ primary: "next" });
  });

  // ── S0 defect 3, the half that lived in this branch ─────────────────────────
  test("a warm-up declined earlier is not offered again from the check path", () => {
    // This branch read `warmUpAvailable && !warmUpInserted` and never consulted
    // `warmUpDeclined` at all, so a refusal recorded on the assessment path
    // reappeared as a tertiary here.
    const plan = feedbackActions({
      ...base,
      classification: null,
      isCheck: true,
      openGapCount: 1,
      warmUpDeclined: true,
    });
    expect(plannedActions(plan)).not.toContain("warmUp");
    expect(plan.primary).toBe("check");
  });

  test("a null classification never falls through to a warm-up primary", () => {
    // The exact bug: `null !== "understood"` was true, so "Build me a warm-up"
    // became the only button offered after a correct check.
    for (const gaps of [0, 1, 3]) {
      const plan = feedbackActions({
        ...base,
        classification: null,
        isCheck: true,
        openGapCount: gaps,
      });
      expect(plan.primary).not.toBe("warmUp");
    }
  });
});

describe("the rules that hold across every row", () => {
  const every: ActionInput[] = [];
  for (const classification of ["understood", "partial", "confused", "off-topic", null]) {
    for (const isCheck of [true, false]) {
      for (const openGapCount of [0, 2]) {
        for (const warmUpInserted of [true, false]) {
          for (const warmUpDeclined of [true, false]) {
            for (const warmUpAvailable of [true, false]) {
              for (const canAnswerAgain of [true, false]) {
                for (const checkAvailable of [true, false]) {
                  every.push({
                    classification,
                    isCheck,
                    openGapCount,
                    warmUpInserted,
                    warmUpDeclined,
                    warmUpAvailable,
                    canAnswerAgain,
                    checkAvailable,
                  });
                }
              }
            }
          }
        }
      }
    }
  }

  test("there is always exactly one primary", () => {
    for (const input of every) {
      const plan = feedbackActions(input);
      expect(plan.primary, JSON.stringify(input)).toBeTruthy();
    }
  });

  test("no action is offered twice in the same plan", () => {
    for (const input of every) {
      const ids = plannedActions(feedbackActions(input));
      expect(new Set(ids).size, JSON.stringify(input)).toBe(ids.length);
    }
  });

  test("at most three actions, so the row never becomes four equal buttons again", () => {
    for (const input of every) {
      expect(plannedActions(feedbackActions(input)).length).toBeLessThanOrEqual(3);
    }
  });

  test("moving on is primary only when the objective is met", () => {
    // THE INVARIANT'S QUANTITY, CORRECTED. This used to accept
    // `classification === "understood"` on its own, which is the latest assessment
    // of one answer and not the node's state: `understanding_of()` withholds
    // `understood` while any blocking gap is unverified. So the sweep asserted the
    // invariant against the same wrong premise the code held, and passed while
    // "Next stop →" was the only action on a stop the server called `partial`.
    //
    // The objective is met when the answer landed AND nothing is outstanding — or
    // when something is outstanding and nothing on offer could close it, which is
    // the honest version of leaving.
    for (const input of every) {
      const plan = feedbackActions(input);
      if (plan.primary !== "next") continue;
      const nothingOutstanding = input.openGapCount === 0;
      const nothingCouldClose = !input.checkAvailable;
      const met =
        (input.classification === "understood" && (nothingOutstanding || nothingCouldClose)) ||
        (input.isCheck && (nothingOutstanding || nothingCouldClose)) ||
        (nothingOutstanding &&
          !["confused", "off-topic"].includes(input.classification ?? ""));
      expect(met, `next was primary for ${JSON.stringify(input)}`).toBe(true);
    }
  });

  test("a warm-up is never offered once one has been declined, on either path", () => {
    // `!i.isCheck` used to be part of this filter, which is precisely how the
    // check branch got away with never reading `warmUpDeclined`.
    for (const input of every.filter((i) => i.warmUpDeclined && !i.warmUpInserted)) {
      expect(
        plannedActions(feedbackActions(input)),
        JSON.stringify(input)
      ).not.toContain("warmUp");
    }
  });

  test("a warm-up is never offered when the panel says it cannot be", () => {
    for (const input of every.filter((i) => !i.warmUpAvailable && !i.warmUpInserted)) {
      const ids = plannedActions(feedbackActions(input));
      expect(ids).not.toContain("warmUp");
    }
  });
});
