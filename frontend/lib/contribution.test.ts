import { describe, expect, it } from "vitest";
import type {
  Contribution, ContributionStage, ScopeCheck, SessionGraph,
} from "@/lib/api";
import {
  canResumeContribution, centreSurface, checkRows, forbiddenRows,
  implementationRail, overrideAvailable, phaseOf, stageIndex, suggestedPaths,
  targetRows,
} from "@/lib/contribution";

/**
 * The contribution view model.
 *
 * Two behaviours here carry product decisions rather than layout ones, and both
 * are asserted at the level of what a learner can see:
 *
 *   `overrideAvailable` — the escape hatch is NOT offered by default. The story
 *   is that blocking required knowledge genuinely gates implementation, so a way
 *   past it on screen from the first stop would undercut it.
 *
 *   `checkRows` — the execution row is always present and never carries a tick.
 *   A validate stage silent about tests reads as one that ran them.
 */

const BOUNDARY = {
  target: [{ file: "src/requests/cookies.py", symbol: "Jar.get_all", why_here: "owns lookup" }],
  must_not_change: [{ file: "src/requests/sessions.py", symbol: "send", why_not: "unrelated" }],
  existing_tests: [{ file: "tests/test_requests.py", symbol: "TestJar", what_it_guards: "conflict" }],
};

function contribution(over: Partial<Contribution> = {}): Contribution {
  return {
    available: true,
    task: "Add Jar.get_all",
    boundary: BOUNDARY,
    ready: { ready: true, required: 2, demonstrated: 2, blockers: [] },
    state: null,
    validation_command: "pytest tests/test_requests.py -q",
    ...over,
  };
}

function blocked(reason: "gap" | "unverified" = "gap"): Contribution {
  return contribution({
    ready: {
      ready: false, required: 2, demonstrated: 1,
      blockers: [{
        node_id: "n2", title: "The conflict contract", objective: "Explain…",
        reason,
        gaps: reason === "gap"
          ? [{ id: "g1", kind: "wrong_model", claim: "it picks one silently" }]
          : [],
      }],
    },
  });
}

function graph(attempted: boolean): SessionGraph {
  return {
    nodes: [{ id: "n2", attempted } as SessionGraph["nodes"][number]],
  } as SessionGraph;
}

function check(over: Partial<ScopeCheck> = {}): ScopeCheck {
  return {
    in_boundary: ["src/requests/cookies.py"],
    outside_boundary: [], forbidden: [], unparseable: [],
    symbols_defined: ["get_all"], test_files: ["tests/test_requests.py"],
    misnamed_tests: [], unchecked_symbols: [],
    symbol_expected: "get_all", symbol_found: true,
    passed: true,
    ...over,
  };
}

describe("phaseOf", () => {
  it("is none for a session that is not a contribution", () => {
    expect(phaseOf(null)).toBe("none");
    expect(phaseOf(contribution({ available: false }))).toBe("none");
  });

  it("is learning while a required concept is undemonstrated", () => {
    expect(phaseOf(blocked())).toBe("learning");
  });

  it("is ready once everything is demonstrated", () => {
    expect(phaseOf(contribution())).toBe("ready");
  });

  it("is ready once the learner has recorded the decision to go on", () => {
    const c = blocked();
    c.state = {
      stage: "plan", plan: null, patch: [], scope_check: null, review: null,
      pr: null, proceeded_unready: true, validation_command: "",
    };
    expect(phaseOf(c)).toBe("ready");
  });

  it("is stage once the work has actually started", () => {
    const c = contribution();
    c.state = {
      stage: "plan", plan: { steps: [{ title: "t", detail: "d" }] }, patch: [],
      scope_check: null, review: null, pr: null, proceeded_unready: false,
      validation_command: "",
    };
    expect(phaseOf(c)).toBe("stage");
  });
});

describe("overrideAvailable", () => {
  it("is not offered when the gate is open", () => {
    expect(overrideAvailable(contribution(), graph(true))).toBe(false);
  });

  it("is not offered to a learner who has not answered anything", () => {
    // They are not stuck; they have not started. Offering a way past the
    // learning here is what would undercut the claim the gate is making.
    expect(overrideAvailable(blocked(), graph(false))).toBe(false);
  });

  it("is not offered when nothing has been diagnosed", () => {
    // `unverified` means no evidence yet, which is a reason to keep going
    // rather than a reason to be let past.
    expect(overrideAvailable(blocked("unverified"), graph(true))).toBe(false);
  });

  it("is offered once a diagnosed gap has survived an attempt", () => {
    expect(overrideAvailable(blocked(), graph(true))).toBe(true);
  });

  it("is not offered twice", () => {
    const c = blocked();
    c.state = {
      stage: "plan", plan: null, patch: [], scope_check: null, review: null,
      pr: null, proceeded_unready: true, validation_command: "",
    };
    expect(overrideAvailable(c, graph(true))).toBe(false);
  });
});

describe("checkRows", () => {
  it("always ends with the execution row, and it never passes", () => {
    const rows = checkRows(check());
    const last = rows[rows.length - 1];
    expect(last.key).toBe("execution");
    expect(last.tone).toBe("none");
  });

  it("keeps the execution row when everything else failed", () => {
    const rows = checkRows(check({ outside_boundary: ["x.py"], passed: false }));
    expect(rows.some((r) => r.key === "execution")).toBe(true);
  });

  it("omits the symbol row when the boundary named no symbol", () => {
    // Omitted because the check could not be MADE, never because it failed —
    // an empty row would look like a result while asserting nothing.
    const rows = checkRows(check({ symbol_expected: "", symbol_found: false }));
    expect(rows.some((r) => r.key === "symbol")).toBe(false);
  });

  it("shows the symbol row as failed when the symbol is missing", () => {
    const rows = checkRows(check({ symbol_found: false }));
    expect(rows.find((r) => r.key === "symbol")?.tone).toBe("fail");
  });

  it("names the files that left the boundary", () => {
    const rows = checkRows(check({
      outside_boundary: ["src/requests/adapters.py"], passed: false,
    }));
    expect(rows.find((r) => r.key === "scope")?.detail)
      .toEqual(["src/requests/adapters.py"]);
  });

  it("reports a forbidden file as a scope failure", () => {
    const rows = checkRows(check({ forbidden: ["src/requests/sessions.py"], passed: false }));
    expect(rows.find((r) => r.key === "scope")?.tone).toBe("fail");
  });

  it("does not fail scope for a syntax error", () => {
    // Two different claims. Folding one into the other is how "scope check
    // passed" starts being read as "the change is fine".
    const rows = checkRows(check({ unparseable: ["a.py"] }));
    expect(rows.find((r) => r.key === "scope")?.tone).toBe("pass");
    expect(rows.find((r) => r.key === "syntax")?.tone).toBe("fail");
  });

  it("is empty before anything has been checked", () => {
    expect(checkRows(null)).toEqual([]);
  });

  /**
   * The row that says what we did NOT check.
   *
   * `ScopeCheck` compares file paths. A boundary constraint like
   * `cookies.py:get` is symbol-level, and nothing here parses the original file
   * — so the surface must say so rather than let a green path result stand for
   * a check nobody made.
   */
  describe("the protected-symbol row", () => {
    it("is absent when there are no symbol-level constraints", () => {
      const rows = checkRows(check());
      expect(rows.some((r) => r.key === "protected")).toBe(false);
    });

    it("appears when they exist, and never as a pass or a failure", () => {
      const rows = checkRows(check({
        unchecked_symbols: ["src/requests/cookies.py:RequestsCookieJar.get"],
      }));
      const row = rows.find((r) => r.key === "protected");
      expect(row?.tone).toBe("none");
      expect(row?.detail).toEqual([
        "src/requests/cookies.py:RequestsCookieJar.get",
      ]);
    });

    it("does not stop the path check passing", () => {
      // They answer different questions. Folding the unchecked one into
      // `passed` would be failing a learner for something nobody looked at.
      const rows = checkRows(check({ unchecked_symbols: ["a.py:f"] }));
      expect(rows.find((r) => r.key === "scope")?.tone).toBe("pass");
    });

    it("sits before the execution row, which is still last", () => {
      const rows = checkRows(check({ unchecked_symbols: ["a.py:f"] }));
      expect(rows[rows.length - 1].key).toBe("execution");
      expect(rows[rows.length - 2].key).toBe("protected");
    });
  });
});

describe("boundary rows", () => {
  it("reads targets with their reason", () => {
    expect(targetRows(BOUNDARY)).toEqual([
      { file: "src/requests/cookies.py", symbol: "Jar.get_all", reason: "owns lookup" },
    ]);
  });

  it("reads the forbidden list with its own reason key", () => {
    expect(forbiddenRows(BOUNDARY)[0].reason).toBe("unrelated");
  });

  it("suggests the target and test paths, without repeats", () => {
    expect(suggestedPaths(BOUNDARY)).toEqual([
      "src/requests/cookies.py", "tests/test_requests.py",
    ]);
  });

  it("survives a boundary that was never recorded", () => {
    expect(targetRows({})).toEqual([]);
    expect(suggestedPaths({})).toEqual([]);
  });
});

describe("stageIndex", () => {
  it("orders the stages", () => {
    expect(stageIndex("plan")).toBe(0);
    expect(stageIndex("done")).toBe(5);
  });
});

/**
 * WHICH SURFACE OWNS THE CENTRE COLUMN.
 *
 * The regression this describes was found by walking the demo: after pressing
 * *Start implementing*, every stop selected from the route rail still rendered
 * the contribution stage's Locate view. The lesson was unreachable for the rest
 * of the session.
 *
 * The cause was deriving the surface from the SESSION alone. Which surface to
 * show is a navigation fact: selecting a stop is a request to see that stop.
 */
describe("centreSurface", () => {
  function started(stage: ContributionStage = "locate"): Contribution {
    const c = contribution();
    c.state = {
      stage, plan: { steps: [{ title: "t", detail: "d" }] }, patch: [],
      scope_check: null, review: null, pr: null, proceeded_unready: false,
      validation_command: "",
    };
    return c;
  }

  it("is the journey for a session that is not a contribution", () => {
    expect(centreSurface(null, null)).toBe("journey");
    expect(centreSurface(contribution({ available: false }), null)).toBe("journey");
  });

  it("is the journey while the learner is still learning", () => {
    expect(centreSurface(blocked(), null)).toBe("journey");
  });

  it("is the gate once the required set is demonstrated", () => {
    expect(centreSurface(contribution(), null)).toBe("ready");
  });

  it("is the contribution once the stage has begun", () => {
    expect(centreSurface(started(), null)).toBe("contribution");
  });

  // ── the regression ────────────────────────────────────────────────────────

  it("RETURNS TO THE LESSON when a stop is selected mid-implementation", () => {
    // The exact defect: stage begun, learner clicks a stop in the rail.
    expect(centreSurface(started(), "journey")).toBe("journey");
  });

  it("returns to the lesson even from the last stage", () => {
    expect(centreSurface(started("done"), "journey")).toBe("journey");
  });

  it("does not let the gate hijack a stop the learner navigated to", () => {
    // A session at 11/11 that has NOT started implementing still shows the gate
    // by default — but not when the learner has asked for a stop.
    expect(centreSurface(contribution(), null)).toBe("ready");
    expect(centreSurface(contribution(), "journey")).toBe("journey");
  });

  it("goes back to the stage when the learner asks for it", () => {
    expect(centreSurface(started(), "contribution")).toBe("contribution");
  });

  it("never shows the stage for a session that has not begun one", () => {
    // The other half of the invariant: navigating must not ACTIVATE a stage.
    // A request alone cannot conjure one on a session with no contribution.
    expect(centreSurface(contribution({ available: false }), "contribution"))
      .toBe("journey");
  });
});

describe("canResumeContribution", () => {
  function started(): Contribution {
    const c = contribution();
    c.state = {
      stage: "locate", plan: { steps: [] }, patch: [], scope_check: null,
      review: null, pr: null, proceeded_unready: false, validation_command: "",
    };
    return c;
  }

  it("offers the door when a stage exists and is not on screen", () => {
    expect(canResumeContribution(started(), "journey")).toBe(true);
  });

  it("does not offer it while the stage IS on screen", () => {
    expect(canResumeContribution(started(), "contribution")).toBe(false);
  });

  it("does not offer it before the stage has begun", () => {
    expect(canResumeContribution(contribution(), "journey")).toBe(false);
    expect(canResumeContribution(blocked(), "journey")).toBe(false);
  });

  it("does not offer it on a non-contribution session", () => {
    expect(canResumeContribution(null, "journey")).toBe(false);
  });
});

/**
 * THE IMPLEMENTATION PHASE AS THE RAIL DRAWS IT.
 *
 * The route and the stages are two phases of one journey shown in one column, so
 * this model has to answer three things without the rail deciding any of them:
 * which phase the session is in, which stage is on screen, and which rows can
 * actually be opened. A row that looks clickable and is not is the defect this
 * guards — the same class as the stepper's old dead end.
 */
describe("implementationRail", () => {
  const started = (stage: ContributionStage): Contribution => {
    const c = contribution();
    c.state = {
      stage, plan: { steps: [{ title: "t", detail: "d" }] }, patch: [],
      scope_check: null, review: null, pr: null, proceeded_unready: false,
      validation_command: "",
    };
    return c;
  };

  const learning = (): Contribution => contribution({
    ready: { ready: false, required: 11, demonstrated: 4, blockers: [] },
  });

  it("is absent from a session that is not a contribution", () => {
    // The whole section is one optional prop, so `null` here is what keeps an
    // ordinary session's rail exactly what it was.
    expect(implementationRail(null, null)).toBeNull();
    expect(implementationRail(contribution({ available: false }), null)).toBeNull();
  });

  it("is locked, and carries the gate's own counter, while learning", () => {
    const rail = implementationRail(learning(), null)!;
    expect(rail.status).toBe("locked");
    expect([rail.demonstrated, rail.required]).toEqual([4, 11]);
    // Nothing may be entered, and nothing may look like the current position:
    // a highlighted stage in a phase that has not started is a claim it has.
    expect(rail.stages.every((r) => !r.enterable)).toBe(true);
    expect(rail.stages.every((r) => r.state === "ahead")).toBe(true);
  });

  it("is ready — visibly live — before anything is started", () => {
    const rail = implementationRail(contribution(), null)!;
    expect(rail.status).toBe("ready");
    // Live, but still not enterable: the way in is the gate, which is what the
    // ready row opens. Entering a stage from here would step around it.
    expect(rail.stages.every((r) => !r.enterable)).toBe(true);
  });

  it("draws the three-step flow, not the old in-app stages", () => {
    // Plan -> Locate -> Continue in Claude Code. The flow ends at the handoff
    // because CodeOnboard cannot edit, execute or open a pull request; the old
    // steps survive only as a fallback and are not part of the route.
    const rail = implementationRail(started("plan"), null)!;
    expect(rail.stages.map((r) => r.stage)).toEqual(["plan", "locate", "handoff"]);
  });

  it("marks the server's stage current once the work has started", () => {
    const rail = implementationRail(started("locate"), null)!;
    expect(rail.status).toBe("active");
    expect(rail.stages.map((r) => r.state)).toEqual(["done", "current", "ahead"]);
  });

  it("follows the step being VIEWED, not the server's alone", () => {
    // Stepping back to Plan must move the rail's highlight with the stepper's,
    // or the two disagree about what is on screen.
    const rail = implementationRail(started("locate"), "plan")!;
    expect(rail.stages.map((r) => r.state)).toEqual(["current", "done", "ahead"]);
    // ...and everything already reached stays open, so stepping back is not a
    // one-way trip.
    expect(rail.stages.map((r) => r.enterable)).toEqual([true, true, false]);
  });

  it("opens the handoff to a learner who has finished Locate", () => {
    const rail = implementationRail(started("locate"), "handoff")!;
    expect(rail.stages.find((r) => r.stage === "handoff")!.enterable).toBe(true);
    expect(rail.stages.find((r) => r.stage === "handoff")!.state).toBe("current");
  });

  it("puts a session on an old in-app step at the end of the flow", () => {
    // `implement` / `validate` / `review` are the fallback. They are past Locate,
    // so the rail shows the flow complete rather than inventing a fourth row for
    // a step the route no longer has.
    const rail = implementationRail(started("validate"), null)!;
    expect(rail.stages.map((r) => r.stage)).toEqual(["plan", "locate", "handoff"]);
    expect(rail.stages.map((r) => r.state)).toEqual(["done", "done", "current"]);
  });

  it("shows every step complete when the contribution is done", () => {
    const rail = implementationRail(started("done"), null)!;
    expect(rail.stages.every((r) => r.enterable)).toBe(true);
    expect(rail.stages[2].state).toBe("current");
  });

  it("is live for a learner who chose to start unready", () => {
    const c = learning();
    c.state = {
      stage: "plan", plan: { steps: [{ title: "t", detail: "d" }] }, patch: [],
      scope_check: null, review: null, pr: null, proceeded_unready: true,
      validation_command: "",
    };
    const rail = implementationRail(c, null)!;
    expect(rail.status).toBe("active");
    // The counter is still the truth about what they demonstrated. The override
    // unlocks the stage; it never becomes a claim about understanding.
    expect(rail.demonstrated).toBe(4);
  });
});
