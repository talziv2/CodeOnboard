import { describe, expect, test } from "vitest";
import { node, prereq, seq } from "@/test/factories";
import { buildRoute } from "@/lib/graph-layout";
import { arrivalNotice } from "@/lib/arrival";
import type { Arrival, GraphNode } from "@/lib/api";

const jumped = (to: string, from: string | null): Arrival => ({
  node_id: to,
  kind: "jumped",
  from_node_id: from,
  at: "2026-08-21T10:00:00+00:00",
});

/** A stop the learner has answered — right or wrong, which is the same thing here. */
const answered = (id: string): GraphNode =>
  node(id, { attempts: [{ classification: "understood" }] as never });

/** Five stations, a→e, none of them dealt with. */
const chain = () => {
  const nodes = ["a", "b", "c", "d", "e"].map((id) => node(id));
  return buildRoute(nodes, [seq("a", "b"), seq("b", "c"), seq("c", "d"), seq("d", "e")]);
};

describe("arrivalNotice — when there is nothing to say", () => {
  test("no arrival record", () => {
    expect(arrivalNotice(null, "a", chain())).toBeNull();
    expect(arrivalNotice(undefined, "a", chain())).toBeNull();
  });

  test("a record that does not name the current stop is STALE and is dropped", () => {
    // The server clears the record on /advance, but a client holding a graph
    // fetched either side of that must not be the thing that decides to trust it
    // — otherwise the notice claims the learner is off-route from a stop they
    // have already walked on from.
    expect(arrivalNotice(jumped("d", "a"), "e", chain())).toBeNull();
  });

  test("a kind this client does not know is dropped rather than guessed at", () => {
    const unknown = { ...jumped("d", "a"), kind: "teleported" };
    expect(arrivalNotice(unknown, "d", chain())).toBeNull();
  });

  test("a stop no longer in the graph", () => {
    expect(arrivalNotice(jumped("gone", "a"), "gone", chain())).toBeNull();
  });

  test("jumping to the stop the route was sending them to anyway is NOT a departure", () => {
    // Nothing is finished, so the route's next stop is `a`. Landing on it is an
    // ordinary next step, and "you jumped ahead, passing 0 stops" about that would
    // be noise on a page that has none to spare.
    expect(arrivalNotice(jumped("a", "c"), "a", chain())).toBeNull();
  });
});

describe("what the jump is measured from", () => {
  test("the route's next stop, NOT the stop they were sitting on", () => {
    // THE CASE THAT DECIDED THIS. The learner answered stop 4 and jumped to 7.
    // Stop 4 is finished — the route was going to send them to 5 — so the notice
    // is about leaving 5 behind, and passes only stop 6.
    const nodes = [
      answered("s1"), answered("s2"), answered("s3"), answered("s4"),
      node("s5"), node("s6"), node("s7"),
    ];
    const stops = buildRoute(nodes, [
      seq("s1", "s2"), seq("s2", "s3"), seq("s3", "s4"),
      seq("s4", "s5"), seq("s5", "s6"), seq("s6", "s7"),
    ]);

    const notice = arrivalNotice(jumped("s7", "s4"), "s7", stops);

    expect(notice!.direction).toBe("ahead");
    expect(notice!.position).toBe(7);
    // Measured from stop 5, so exactly one stop (6) was passed. From `s4` it
    // would have wrongly been two.
    expect(notice!.passed).toBe(1);
    expect(notice!.returnTo).toEqual({ nodeId: "s5", title: "Stop s5", position: 5 });
  });

  test("a WRONG answer finishes a stop as much as a right one", () => {
    // The reference is about where the route would go next, not about how well
    // the learner did — so a failed stop is still behind them.
    const nodes = [
      node("s1", { attempts: [{ classification: "confused" }] as never }),
      node("s2"),
      node("s3"),
    ];
    const stops = buildRoute(nodes, [seq("s1", "s2"), seq("s2", "s3")]);

    const notice = arrivalNotice(jumped("s3", "s1"), "s3", stops);
    expect(notice!.returnTo!.nodeId).toBe("s2");
    expect(notice!.passed).toBe(0);
  });

  test("a stop merely walked past counts as finished", () => {
    // `/advance` marks visited without grading, and that is still "dealt with".
    const nodes = [node("s1", { visited: true }), node("s2"), node("s3")];
    const stops = buildRoute(nodes, [seq("s1", "s2"), seq("s2", "s3")]);

    expect(arrivalNotice(jumped("s3", "s1"), "s3", stops)!.returnTo!.nodeId).toBe("s2");
  });

  test("progress with a hole in it still points at the earliest unfinished stop", () => {
    // 1–2 and 5 answered, from an earlier jump. "Last finished + 1" would name 6,
    // a stop nobody has reached; the route's next stop is 3.
    const nodes = [
      answered("s1"), answered("s2"), node("s3"), node("s4"), answered("s5"), node("s6"),
    ];
    const stops = buildRoute(nodes, [
      seq("s1", "s2"), seq("s2", "s3"), seq("s3", "s4"), seq("s4", "s5"), seq("s5", "s6"),
    ]);

    const notice = arrivalNotice(jumped("s6", "s5"), "s6", stops);
    expect(notice!.returnTo!.nodeId).toBe("s3");
    expect(notice!.passed).toBe(2);
  });

  test("an unfinished WARM-UP is where the route is, and no number is quoted for it", () => {
    // FOUND IN THE BROWSER, not by a test. A session whose only outstanding stop
    // was a spliced warm-up fell through to the fallback and offered the stop the
    // learner had been sitting on. `resume_point()` puts unfinished remediation
    // first precisely because that is where they left off; the rail merely does
    // not NUMBER it, which is a separate question — handled by `passed`.
    const nodes = [answered("a"), node("w"), answered("b"), answered("c")];
    const stops = buildRoute(nodes, [
      seq("a", "w"), prereq("w", "b"), seq("b", "c"),
    ]);

    const notice = arrivalNotice(jumped("c", "b"), "c", stops);
    expect(notice!.returnTo!.nodeId).toBe("w");
    // Not a station, so no distance is claimed from it.
    expect(notice!.passed).toBe(0);
  });

  test("an OPTIONAL unit is never where the route is", () => {
    // Depth off the default walk — `/advance` steps over it, so the route would
    // never have sent them there.
    const nodes = [
      answered("a"), node("opt", { priority: "optional" }), node("b"), node("c"),
    ];
    const stops = buildRoute(nodes, [
      seq("a", "opt"), seq("opt", "b"), seq("b", "c"),
    ]);

    const notice = arrivalNotice(jumped("c", "a"), "c", stops);
    expect(notice!.returnTo!.nodeId).toBe("b");
  });
});

describe("arrivalNotice — direction", () => {
  test("jumping ahead reports the stop landed on and the walk length", () => {
    const notice = arrivalNotice(jumped("d", "a"), "d", chain());

    expect(notice!.direction).toBe("ahead");
    expect(notice!.position).toBe(4);
    expect(notice!.total).toBe(5);
    // Route is at `a`; b and c are passed.
    expect(notice!.passed).toBe(2);
    expect(notice!.isStation).toBe(true);
  });

  test("coming back to a finished stop says it was already taken", () => {
    const nodes = [answered("a"), answered("b"), node("c")];
    const stops = buildRoute(nodes, [seq("a", "b"), seq("b", "c")]);

    // Route is at `c`; jumping to `a` is going backwards.
    const notice = arrivalNotice(jumped("a", "c"), "a", stops);
    expect(notice!.direction).toBe("back");
    expect(notice!.revisited).toBe(true);
    expect(notice!.passed).toBe(1);
    expect(notice!.returnTo!.nodeId).toBe("c");
  });

  test("an UNFINISHED stop behind them is not called already taken", () => {
    // Reachable: a scope change or a warm-up can leave an unfinished stop behind
    // the learner's position, and "already taken" would simply be false.
    const nodes = [node("a"), answered("b"), answered("c"), node("d")];
    const stops = buildRoute(nodes, [seq("a", "b"), seq("b", "c"), seq("c", "d")]);

    // Route is at `a` — so a jump to `a` is no notice at all; jump to `d` instead
    // and then back to the unfinished `a` is what a learner actually does.
    const notice = arrivalNotice(jumped("d", "c"), "d", stops);
    expect(notice!.direction).toBe("ahead");
    expect(notice!.revisited).toBe(false);
  });
});

describe("arrivalNotice — stops that consume no number", () => {
  test("an optional unit reports isStation false, so no number is claimed for it", () => {
    // The rail collapses optional units and does not count them, so quoting
    // "stop 3 of 4" for one would promise a position the rail never shows.
    const nodes = [answered("a"), node("b"), node("opt", { priority: "optional" }), node("c")];
    const stops = buildRoute(nodes, [seq("a", "b"), seq("b", "opt"), seq("opt", "c")]);

    const notice = arrivalNotice(jumped("opt", "a"), "opt", stops);
    expect(notice!.isStation).toBe(false);
    expect(notice!.total).toBe(3);
    expect(notice!.direction).toBe("ahead");
    // And no distance is claimed: `opt` carries the position of the station after
    // it, so subtracting positions would count a gap that is not there.
    expect(notice!.passed).toBe(0);
  });

  test("a spliced warm-up landed on reports isStation false too", () => {
    // `a` is unfinished, so IT is where the route is — which makes arriving at the
    // warm-up a real departure rather than the route's own next step. (Jumping to
    // a warm-up that IS the route's next stop yields no notice at all, which the
    // route-reference tests above cover.)
    const nodes = [node("a"), node("w"), answered("b")];
    const stops = buildRoute(nodes, [seq("a", "w"), prereq("w", "b")]);

    const notice = arrivalNotice(jumped("w", "b"), "w", stops);
    expect(notice!.isStation).toBe(false);
    expect(notice!.returnTo!.nodeId).toBe("a");
  });
});

describe("arrivalNotice — a journey with nothing left unfinished", () => {
  test("falls back to the stop actually left behind", () => {
    // The only reference a completed journey has. `from_node_id` is still
    // recorded for exactly this, and for the session log.
    const nodes = [answered("a"), answered("b"), answered("c")];
    const stops = buildRoute(nodes, [seq("a", "b"), seq("b", "c")]);

    const notice = arrivalNotice(jumped("a", "c"), "a", stops);
    expect(notice!.direction).toBe("back");
    expect(notice!.returnTo!.nodeId).toBe("c");
    expect(notice!.revisited).toBe(true);
  });

  test("and reports position with no direction when even that stop is gone", () => {
    const nodes = [answered("a"), answered("b"), answered("c")];
    const stops = buildRoute(nodes, [seq("a", "b"), seq("b", "c")]);

    const notice = arrivalNotice(jumped("b", "vanished"), "b", stops);
    expect(notice!.direction).toBeNull();
    expect(notice!.returnTo).toBeNull();
    expect(notice!.position).toBe(2);
    expect(notice!.passed).toBe(0);
  });
});

describe("answering a question is not navigation", () => {
  /**
   * THE FALSE POSITIVE, from a real session. Reported as: "Off the route
   * appeared after normal successful progression — I had not intentionally
   * navigated away."
   *
   * The learner picks the route's next stop off the rail, which records an
   * arrival and is correctly silent. Then they answer it. Before the fix that
   * answer moved the reference forward, the arrival landed BEHIND it, and the
   * banner appeared as a consequence of getting the question right.
   */
  const AT = "2026-08-21T10:00:00+00:00";
  const attempt = (at: string) =>
    [{ classification: "understood", at }] as never;

  /** a is done; b is the route's next stop; the learner jumps straight to b. */
  const routeNextStop = (bAttempts: GraphNode["attempts"]) =>
    buildRoute(
      [
        node("a", { attempts: attempt("2026-08-21T09:00:00+00:00") }),
        node("b", { attempts: bAttempts }),
        node("c"),
      ],
      [seq("a", "b"), seq("b", "c")]
    );

  test("silent on arrival at the stop the route was sending them to", () => {
    expect(arrivalNotice(jumped("b", "a"), "b", routeNextStop([]))).toBeNull();
  });

  test("STILL silent once they answer it", () => {
    // The attempt is stamped after the arrival, so it cannot move the reference:
    // "was this a departure" is a question about the moment they arrived.
    const stops = routeNextStop(attempt("2026-08-21T10:04:00+00:00"));
    expect(arrivalNotice(jumped("b", "a"), "b", stops)).toBeNull();
  });

  test("silent even when the answer lands in the same second as the jump", () => {
    const stops = routeNextStop(attempt(AT));
    expect(arrivalNotice(jumped("b", "a"), "b", stops)).toBeNull();
  });

  test("a genuine departure is NOT silenced by answering", () => {
    // The other half of the guarantee: this must still fire. The learner skips
    // past b to c and answers there — they are off the route either way, and the
    // fix must not have turned the notice off wholesale.
    const stops = buildRoute(
      [
        node("a", { attempts: attempt("2026-08-21T09:00:00+00:00") }),
        node("b"),
        node("c", { attempts: attempt("2026-08-21T10:04:00+00:00") }),
      ],
      [seq("a", "b"), seq("b", "c")]
    );

    const notice = arrivalNotice(jumped("c", "a"), "c", stops);
    expect(notice!.direction).toBe("ahead");
    expect(notice!.returnTo!.nodeId).toBe("b");
  });

  test("`already taken` describes what they walked into, not what they then did", () => {
    // `revisited` is read as-of the arrival for the same reason the reference is:
    // answering a stop must not retroactively make arriving at it a return.
    const stops = buildRoute(
      [
        node("a", { attempts: attempt("2026-08-21T09:00:00+00:00") }),
        node("b", { attempts: attempt("2026-08-21T09:30:00+00:00") }),
        node("c"),
        // Never reached, and jumped to from b.
        node("d", { attempts: attempt("2026-08-21T10:04:00+00:00") }),
      ],
      [seq("a", "b"), seq("b", "c"), seq("c", "d")]
    );

    const notice = arrivalNotice(jumped("d", "b"), "d", stops);
    expect(notice!.direction).toBe("ahead");
    expect(notice!.revisited).toBe(false);
  });
});
