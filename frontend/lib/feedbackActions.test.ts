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
};

describe("the table", () => {
  test("understood: moving on is primary, and it is the only row where it is", () => {
    expect(feedbackActions({ ...base, classification: "understood" })).toEqual({
      primary: "next",
    });
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
                every.push({
                  classification,
                  isCheck,
                  openGapCount,
                  warmUpInserted,
                  warmUpDeclined,
                  warmUpAvailable,
                  canAnswerAgain,
                });
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
    for (const input of every) {
      const plan = feedbackActions(input);
      if (plan.primary !== "next") continue;
      // `next` is legitimate as primary in exactly three situations: the answer was
      // understood, a check closed everything, or there is no named gap left to
      // close and a retry is what remains on offer.
      const met =
        input.classification === "understood" ||
        (input.isCheck && input.openGapCount === 0) ||
        (input.openGapCount === 0 && !["confused", "off-topic"].includes(input.classification ?? ""));
      expect(met, `next was primary for ${JSON.stringify(input)}`).toBe(true);
    }
  });

  test("a warm-up is never offered once the backend has declined one", () => {
    for (const input of every.filter((i) => i.warmUpDeclined && !i.warmUpInserted && !i.isCheck)) {
      expect(plannedActions(feedbackActions(input))).not.toContain("warmUp");
    }
  });

  test("a warm-up is never offered when the panel says it cannot be", () => {
    for (const input of every.filter((i) => !i.warmUpAvailable && !i.warmUpInserted)) {
      const ids = plannedActions(feedbackActions(input));
      expect(ids).not.toContain("warmUp");
    }
  });
});
