import { describe, expect, test } from "vitest";
import type { RetryOffer } from "@/lib/api";
import { feedbackActions, plannedActions, type ActionInput } from "@/lib/feedbackActions";

/**
 * The verdict branch table, row by row.
 *
 * `ui-direction.md` §2.4's rule is that the primary is whatever most directly
 * closes the gap between where the learner is and the objective, and that moving on
 * is never primary unless the objective is met. Both halves are asserted here — the
 * second one globally, because it is the claim most easily broken by a later edit.
 *
 * ── What M2 changed about this file ──────────────────────────────────────────
 *
 * The old suite swept `openGapCount × checkAvailable × canAnswerAgain × …` because
 * this module used to DECIDE whether a retry was possible from those four flags.
 * It no longer does: the decision is `backend/learning/retry.py`'s, and the flags
 * it was reconstructed from could not be made correct on this side — gap budgets,
 * remediation rounds and the re-assessment budget are simply not here.
 *
 * So the sweep collapses to `RetryOffer`, and the module's whole remaining job is
 * to weight what it is handed. That is a smaller thing to test and a smaller thing
 * to get wrong, which is the point of moving it.
 */

const OFFER: RetryOffer = {
  available: true,
  mechanism: "reassess",
  reason: "",
  gap_id: null,
  reassessments_left: 2,
};
const NO_OFFER: RetryOffer = {
  available: false,
  mechanism: null,
  reason: "budget_spent",
  gap_id: null,
  reassessments_left: 0,
};
const MET: RetryOffer = { ...NO_OFFER, reason: "objective_met" };

const base: ActionInput = {
  classification: "partial",
  isCheck: false,
  retry: OFFER,
  warmUpInserted: false,
  warmUpDeclined: false,
  warmUpAvailable: true,
};

describe("the table", () => {
  test("objective met: moving on is primary, and it is the only action", () => {
    expect(
      feedbackActions({ ...base, classification: "understood", retry: MET })
    ).toEqual({ primary: "next" });
  });

  test("`understood` is NOT the same as the objective being met", () => {
    // The quantity that used to be wrong here. `classification` is the latest
    // assessment of one answer; the objective is the NODE's state, and
    // `understanding_of()` withholds `understood` while any blocking gap is
    // unverified. Reading the first as the second is what once returned
    // "Next stop →" as the only action on a stop the server called `partial`.
    const plan = feedbackActions({ ...base, classification: "understood", retry: OFFER });
    expect(plan.primary).toBe("askAgain");
    expect(plan.secondary).toBe("next");
  });

  test("a shortfall with a retry available: the retry leads", () => {
    const plan = feedbackActions({ ...base, classification: "confused" });
    expect(plan.primary).toBe("askAgain");
    // Failed, so leaving is named honestly rather than dressed as an advance.
    expect(plan.secondary).toBe("moveOn");
  });

  test("the mechanism does not change the button", () => {
    // The learner meets ONE retry. Which machinery serves it is our bookkeeping,
    // and a label that leaked it would be asking them to diagnose themselves.
    for (const mechanism of ["verify", "reassess", "answer"] as const) {
      const plan = feedbackActions({ ...base, retry: { ...OFFER, mechanism } });
      expect(plan.primary, mechanism).toBe("askAgain");
    }
  });

  test("no retry, warm-up available: the warm-up leads even though it is slower", () => {
    // It is the only thing left pointing at the objective.
    const plan = feedbackActions({ ...base, classification: "confused", retry: NO_OFFER });
    expect(plan.primary).toBe("warmUp");
    expect(plan.secondary).toBe("moveOn");
  });

  test("no retry and no warm-up: leaving is what is left, and it says so", () => {
    const plan = feedbackActions({
      ...base,
      classification: "confused",
      retry: NO_OFFER,
      warmUpAvailable: false,
    });
    expect(plan).toEqual({ primary: "moveOn" });
  });

  test("an inserted warm-up outranks everything", () => {
    // Another question about a foundation that is about to be taught is not more
    // direct than teaching it.
    const plan = feedbackActions({ ...base, warmUpInserted: true });
    expect(plan.primary).toBe("startWarmUp");
    expect(plannedActions(plan)).toEqual(["startWarmUp", "skipWarmUp", "moveOn"]);
  });

  test("a check that left something open still leads with the retry", () => {
    const plan = feedbackActions({ ...base, classification: null, isCheck: true });
    expect(plan.primary).toBe("askAgain");
    // A check with something outstanding is a shortfall like any other.
    expect(plan.secondary).toBe("moveOn");
  });

  test("a check that cleared everything moves on", () => {
    expect(
      feedbackActions({ ...base, classification: null, isCheck: true, retry: MET })
    ).toEqual({ primary: "next" });
  });

  test("a declined warm-up is never offered again, on either path", () => {
    for (const isCheck of [true, false]) {
      const plan = feedbackActions({
        ...base,
        classification: isCheck ? null : "confused",
        isCheck,
        warmUpDeclined: true,
      });
      expect(plannedActions(plan), String(isCheck)).not.toContain("warmUp");
    }
  });

  test("a pre-M2 backend degrades to no retry rather than a button that 404s", () => {
    const plan = feedbackActions({ ...base, retry: undefined, classification: "confused" });
    expect(plannedActions(plan)).not.toContain("askAgain");
  });

  test("without an offer, `understood` still means met", () => {
    // The pre-M2 fallback path, so an older backend keeps behaving.
    expect(
      feedbackActions({ ...base, retry: undefined, classification: "understood" })
    ).toEqual({ primary: "next" });
  });
});

// ── the exhaustive sweep ─────────────────────────────────────────────────────

const CLASSIFICATIONS = ["understood", "partial", "confused", "off-topic", null];
const OFFERS: (RetryOffer | undefined)[] = [
  OFFER,
  { ...OFFER, mechanism: "verify", gap_id: "g1" },
  { ...OFFER, mechanism: "answer" },
  NO_OFFER,
  MET,
  undefined,
];

const every: ActionInput[] = [];
for (const classification of CLASSIFICATIONS)
  for (const retry of OFFERS)
    for (const isCheck of [true, false])
      for (const warmUpInserted of [true, false])
        for (const warmUpDeclined of [true, false])
          for (const warmUpAvailable of [true, false])
            every.push({
              classification: isCheck ? null : classification,
              isCheck,
              retry,
              warmUpInserted,
              warmUpDeclined,
              warmUpAvailable,
            });

describe("invariants, over every reachable input", () => {
  test("there is always exactly one primary", () => {
    for (const input of every) {
      expect(plannedActions(feedbackActions(input)).length, JSON.stringify(input))
        .toBeGreaterThan(0);
    }
  });

  test("MOVING ON IS NEVER PRIMARY WHILE A RETRY IS AVAILABLE", () => {
    // §2.4's rule, in the one form that cannot be satisfied by a wrong quantity.
    // The old sweep checked it against `openGapCount`/`checkAvailable`, which is
    // what this module used to guess with — so it asserted the invariant against
    // the same premise the code held and passed while the rule was broken.
    // `retry.available` is the server's answer, computed from the real state.
    for (const input of every) {
      const plan = feedbackActions(input);
      if (plan.primary !== "next" && plan.primary !== "moveOn") continue;
      if (input.warmUpInserted) continue; // its own row; a warm-up leads there
      expect(
        input.retry?.available ?? false,
        `left was primary while a retry was available: ${JSON.stringify(input)}`
      ).toBe(false);
    }
  });

  test("the retry is offered whenever the server says it is available", () => {
    // The other direction, and the one that caught the original defect: a retry
    // that exists must never be silently dropped. `warmUpInserted` is the sole
    // exception, and it is an explicit row rather than a fall-through.
    for (const input of every.filter((i) => i.retry?.available && !i.warmUpInserted)) {
      expect(
        plannedActions(feedbackActions(input)),
        JSON.stringify(input)
      ).toContain("askAgain");
    }
  });

  test("a warm-up is never offered once one has been declined", () => {
    for (const input of every.filter((i) => i.warmUpDeclined && !i.warmUpInserted)) {
      expect(
        plannedActions(feedbackActions(input)),
        JSON.stringify(input)
      ).not.toContain("warmUp");
    }
  });

  test("a warm-up is never offered where nothing fell short", () => {
    // The invariant behind the two regressions above, swept. A warm-up
    // remediates confusion; where the latest act showed none there is nothing
    // for it to remediate, and offering it contradicts the evidence just
    // recorded.
    for (const input of every) {
      if (input.warmUpInserted) continue; // its own row: starting one, not building
      const shortfall = input.isCheck
        ? input.retry?.mechanism === "verify"
        : input.classification !== null && input.classification !== "understood";
      if (shortfall) continue;
      expect(
        plannedActions(feedbackActions(input)),
        JSON.stringify(input)
      ).not.toContain("warmUp");
    }
  });

  test("a warm-up is never offered when the panel says it cannot be", () => {
    for (const input of every.filter((i) => !i.warmUpAvailable && !i.warmUpInserted)) {
      expect(
        plannedActions(feedbackActions(input)),
        JSON.stringify(input)
      ).not.toContain("warmUp");
    }
  });

  test("no action is ever offered twice", () => {
    for (const input of every) {
      const actions = plannedActions(feedbackActions(input));
      expect(new Set(actions).size, JSON.stringify(input)).toBe(actions.length);
    }
  });
});

// ── M3: read before you answer again ─────────────────────────────────────────

describe("rewritten material the learner has not read", () => {
  test("leads, ahead of the retry", () => {
    // The fresh question is built to be fatal to exactly the misconception the
    // unread correction explains. Sending the learner straight at it would set
    // them up to fail something they were just given the means to get right.
    const plan = feedbackActions({ ...base, classification: "confused", materialUnread: true });
    expect(plan.primary).toBe("readMaterial");
    expect(plan.secondary).toBe("askAgain");
  });

  test("does NOT remove the retry — this is guidance, not a gate", () => {
    // Blocking would be the system deciding the learner may not know something.
    // The ordering says which we think is more direct and nothing more.
    const plan = feedbackActions({ ...base, classification: "confused", materialUnread: true });
    expect(plannedActions(plan)).toContain("askAgain");
  });

  test("still offers a way out when there is no retry", () => {
    const plan = feedbackActions({
      ...base, classification: "confused", materialUnread: true,
      retry: NO_OFFER, warmUpAvailable: false,
    });
    expect(plan.primary).toBe("readMaterial");
    expect(plan.secondary).toBe("moveOn");
  });

  test("never outranks a warm-up that is already in the journey", () => {
    // Starting a foundation that is about to be taught beats reading a
    // correction to the stop it unblocks.
    const plan = feedbackActions({ ...base, materialUnread: true, warmUpInserted: true });
    expect(plan.primary).toBe("startWarmUp");
  });

  test("never appears once the objective is met", () => {
    // Nothing is outstanding, so there is nothing to go and read FOR.
    const plan = feedbackActions({
      ...base, classification: "understood", retry: MET, materialUnread: true,
    });
    expect(plan).toEqual({ primary: "next" });
  });

  test("is absent by default, so the single column is unchanged", () => {
    expect(plannedActions(feedbackActions({ ...base, classification: "confused" })))
      .not.toContain("readMaterial");
  });
});

// ── a warm-up needs something to remediate ───────────────────────────────────

describe("the warm-up is offered only where something fell short", () => {
  /**
   * Both rows here were live regressions, reported from a real run. The rewrite
   * that moved the retry decision to the server collapsed the old `isCheck`
   * early-return, and with it two rules: a check that cleared everything used to
   * return `{primary: "next"}` with no warm-up, and an `understood` answer
   * refused one outright.
   */
  const CHECK_CLEARED: RetryOffer = { ...OFFER, mechanism: "reassess" };
  const CHECK_LEFT_OPEN: RetryOffer = { ...OFFER, mechanism: "verify", gap_id: "g1" };

  test("a check that CLEARED everything does not offer one", () => {
    // "Cleared — what this closed: …" with "Build me a warm-up" beside it. The
    // learner has just positively demonstrated the corrected model; offering to
    // step back disagrees with the evidence recorded one line above.
    const plan = feedbackActions({
      ...base, classification: null, isCheck: true, retry: CHECK_CLEARED,
    });
    expect(plannedActions(plan)).not.toContain("warmUp");
    // And the retry still leads — it is the only route to crediting the stop.
    expect(plan.primary).toBe("askAgain");
  });

  test("a check that left something open still offers one", () => {
    const plan = feedbackActions({
      ...base, classification: null, isCheck: true, retry: CHECK_LEFT_OPEN,
    });
    expect(plannedActions(plan)).toContain("warmUp");
  });

  test("an answer that reached the objective does not, even with a gap open", () => {
    // Stepping back would be the system disagreeing with its own grade.
    const plan = feedbackActions({
      ...base, classification: "understood", retry: CHECK_LEFT_OPEN,
    });
    expect(plannedActions(plan)).not.toContain("warmUp");
  });

  test("a confused answer with no gaps named still offers one", () => {
    // §18.11: a confused learner must not be offered FEWER options than a
    // partial one. This is the row that gate must not break.
    const plan = feedbackActions({ ...base, classification: "confused" });
    expect(plannedActions(plan)).toContain("warmUp");
  });
});

describe("the explanation an answer unlocks", () => {
  /**
   * #2. The withheld explanation opens on the first graded answer, and under the
   * surface split it opens on the OTHER TAB. All that said so was a dot; the
   * relationship — *answered → material appeared → read it* — was left for the
   * learner to infer from one bit of chrome, and "it is easy to continue without
   * realising there is new material to read" is exactly what happened.
   */
  test("a correct answer leads with the explanation, and keeps Next beside it", () => {
    const plan = feedbackActions({
      ...base,
      classification: "understood",
      retry: MET,
      explanationUnread: true,
    });

    expect(plan.primary).toBe("readExplanation");
    // GUIDANCE, NOT A GATE. Moving on is one click away, exactly as before.
    expect(plan.secondary).toBe("next");
  });

  test("and offers Next alone once there is nothing new to read", () => {
    const plan = feedbackActions({
      ...base,
      classification: "understood",
      retry: MET,
      explanationUnread: false,
    });

    expect(plannedActions(plan)).toEqual(["next"]);
  });

  test("reading it is offered on a shortfall too, ahead of another go", () => {
    // The explanation is what the next attempt would be built on, so sending the
    // learner straight back at the question would waste it.
    const plan = feedbackActions({ ...base, explanationUnread: true });

    expect(plannedActions(plan)).toEqual(["readExplanation", "askAgain", "next"]);
  });

  test("a REWRITE outranks it — they are never both on the row", () => {
    // A re-teach installs a new reveal with the new lesson, so the rewrite is the
    // newer claim and the one that names the misconception.
    const plan = feedbackActions({
      ...base,
      materialUnread: true,
      explanationUnread: true,
    });

    expect(plan.primary).toBe("readMaterial");
    expect(plannedActions(plan)).not.toContain("readExplanation");
  });

  test("a warm-up just spliced in outranks both", () => {
    const plan = feedbackActions({
      ...base,
      warmUpInserted: true,
      explanationUnread: true,
    });

    expect(plan.primary).toBe("startWarmUp");
    expect(plannedActions(plan)).not.toContain("readExplanation");
  });
});
