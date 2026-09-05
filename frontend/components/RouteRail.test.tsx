import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import RouteRail from "@/components/RouteRail";
import { buildRoute } from "@/lib/graph-layout";
import { splitJourney } from "@/lib/route-sections";
import { node } from "@/test/factories";
import { t } from "@/lib/strings";
import type { Area, GraphEdge, GraphNode, NodeGap } from "@/lib/api";
import type { ImplementationRail } from "@/lib/contribution";

/**
 * The rail, after the six notes that came out of walking a real session.
 *
 * Only the behavioural ones are asserted here. "Make it wider" and "increase the
 * gap" are numbers in a class string — a test repeating the number proves the
 * number is the number, and would fail on any future re-spacing while catching
 * nothing. What is worth holding is the collapse contract, what a stop is allowed
 * to say, and that the chapter you are reading is distinguishable from the ones
 * you are not.
 */

const AREAS: Area[] = [
  { id: "a1", title: "Session–Adapter contract", why: "Where a request is handed off.", order: 0 },
  { id: "a2", title: "Connection pooling", why: "Where sockets are reused.", order: 1 },
];

const stop = (id: string, title: string, area: string, file: string) =>
  node(id, { title, objective: `Explain ${title}`, area_id: area, file }) as GraphNode;

const NODES = [
  stop("n1", "Explain the Session–adapter handoff", "a1", "requests/sessions.py"),
  stop("n2", "Identify the BaseAdapter contract", "a1", "requests/adapters.py"),
  stop("n3", "Explain pool parameters", "a2", "requests/adapters.py"),
];

/** `n2` is current: mid-chapter, so collapse has something to hide on both sides. */
function rail(currentNodeId: string | null = "n2", openSectionId: string | null = null) {
  const edges: GraphEdge[] = NODES.slice(0, -1).map((n, i) => ({
    from_id: n.id,
    to_id: NODES[i + 1].id,
    kind: "sequence",
  }));
  const journey = splitJourney(buildRoute(NODES, edges), AREAS, currentNodeId);
  const onJump = vi.fn();
  const onOpenSection = vi.fn();
  const utils = render(
    <RouteRail
      sections={journey.sections}
      optional={journey.optional}
      currentNodeId={currentNodeId}
      openSectionId={openSectionId}
      onJump={onJump}
      onOpenSection={onOpenSection}
      onExpand={vi.fn()}
    />
  );
  return { ...utils, onJump, onOpenSection };
}

/** The heading button for a chapter — the one that opens its overview. */
const heading = (title: string) =>
  screen.getByRole("button", { name: t.rail.openSection(title) });

/** The rail with whatever extra props a test needs on top of the defaults. */
function railWith(extra: Record<string, unknown>) {
  const edges: GraphEdge[] = NODES.slice(0, -1).map((n, i) => ({
    from_id: n.id,
    to_id: NODES[i + 1].id,
    kind: "sequence",
  }));
  const journey = splitJourney(buildRoute(NODES, edges), AREAS, "n2");
  return render(
    <RouteRail
      sections={journey.sections}
      optional={journey.optional}
      currentNodeId="n2"
      onJump={vi.fn()}
      onOpenSection={vi.fn()}
      onExpand={vi.fn()}
      {...extra}
    />
  );
}

describe("the briefing sits at the head of the route, and is not part of it", () => {
  test("offered when there is somewhere to send the learner", () => {
    const onBriefing = vi.fn();
    railWith({ onBriefing });
    fireEvent.click(screen.getByRole("button", { name: new RegExp(t.rail.briefing) }));
    expect(onBriefing).toHaveBeenCalled();
  });

  test("absent when there is not — a row that goes nowhere is worse than none", () => {
    rail("n2");
    expect(screen.queryByText(t.rail.briefing)).toBeNull();
  });

  test("it is the FIRST thing in the route list, before any chapter", () => {
    railWith({ onBriefing: vi.fn() });
    const nav = document.querySelector("nav")!;
    const briefing = screen.getByText(t.rail.briefing);
    const firstHeading = screen.getByText("Session–Adapter contract");
    // `compareDocumentPosition` rather than index arithmetic: the claim is document
    // order, not how many wrappers happen to sit between them.
    const order = briefing.compareDocumentPosition(firstHeading);
    expect(nav.contains(briefing)).toBe(true);
    expect(order & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  test("it carries no understanding state, because nothing is demonstrated there", () => {
    const { container } = railWith({ onBriefing: vi.fn() });
    const row = screen.getByText(t.rail.briefing).closest("button")!;
    // A stop is a pin plus a title; a chapter is a heading with a counter. This is
    // neither, so it must not borrow either one's furniture.
    expect(row.querySelector("svg")).toBeNull();
    expect(row.getAttribute("aria-current")).toBeNull();
    expect(container.querySelectorAll('[aria-current="step"]')).toHaveLength(1);
  });

  test("it reads as a different KIND of thing: a bordered box, not tracked caps", () => {
    railWith({ onBriefing: vi.fn() });
    const row = screen.getByText(t.rail.briefing).closest("button")!;
    // The rail's other two idioms are `uppercase tracking-[…]` for chapters and the
    // pin grid for stops. A border is the visual claim that this is neither.
    expect(row.className).toMatch(/border/);
    expect(row.className).not.toMatch(/uppercase/);
    expect(screen.getByText(t.rail.briefingHint)).toBeTruthy();
  });

  test("present in the compact strip too, where there is no room for a box", () => {
    railWith({ onBriefing: vi.fn(), compact: true });
    expect(screen.getByRole("button", { name: t.rail.briefing })).toBeTruthy();
  });
});

describe("collapsed means collapsed (note 5)", () => {
  test("the chapter you are standing in starts open", () => {
    rail("n2");
    expect(screen.getByText("Identify the BaseAdapter contract")).toBeTruthy();
  });

  test("collapsing it hides its stops — including the one you are on", () => {
    // This is the bug the note reported. The rail used to keep the current stop
    // rendered inside a closed section, so the chevron said closed while a row was
    // still sitting there and the control looked broken.
    const { container } = rail("n2");
    fireEvent.click(screen.getByRole("button", { name: /^Collapse Session–Adapter contract/ }));

    expect(screen.queryByText("Identify the BaseAdapter contract")).toBeNull();
    expect(screen.queryByText("Explain the Session–adapter handoff")).toBeNull();
    // And nothing is left claiming to be the current step.
    expect(container.querySelector('[aria-current="step"]')).toBeNull();
  });

  test("re-expanding brings them back", () => {
    rail("n2");
    fireEvent.click(screen.getByRole("button", { name: /^Collapse Session–Adapter contract/ }));
    fireEvent.click(screen.getByRole("button", { name: /^Expand Session–Adapter contract/ }));
    expect(screen.getByText("Identify the BaseAdapter contract")).toBeTruthy();
  });

  test("a chapter you are not in starts collapsed", () => {
    rail("n2");
    expect(screen.queryByText("Explain pool parameters")).toBeNull();
    expect(screen.getByRole("button", { name: /^Expand Connection pooling/ })).toBeTruthy();
  });
});

describe("what a stop is allowed to say (note 1)", () => {
  test("the current stop does not repeat its file path", () => {
    // The path is in the lesson header and in the source pane. Three copies of
    // `requests/adapters.py` on one screen was the note.
    rail("n2");
    expect(screen.queryByText("requests/adapters.py")).toBeNull();
  });

  test("no stop shows a path, current or not", () => {
    rail("n2");
    expect(screen.queryByText("requests/sessions.py")).toBeNull();
  });

  test("the current stop is still identifiable — by state, not by path", () => {
    const { container } = rail("n2");
    const current = container.querySelector('[aria-current="step"]');
    expect(current).toBeTruthy();
    expect(current!.textContent).toContain("Identify the BaseAdapter contract");
  });
});

describe("the chapter heading says whether it is open (note 6)", () => {
  /** The title span inside a heading button carries the tone class. */
  const tone = (title: string) => {
    const span = heading(title).querySelector("span span");
    return (span?.className ?? "")
      .split(" ")
      .filter((c) => /^text-(signal|chalk|graphite)$/.test(c))
      .join(" ");
  };

  test("open, closed and current are three different tones", () => {
    rail("n2");
    // `a1` contains the current stop, so it is open AND current.
    const current = tone("Session–Adapter contract");
    const closed = tone("Connection pooling");
    expect(current).not.toBe(closed);

    // Open it: it is now open but still not the chapter being read.
    fireEvent.click(screen.getByRole("button", { name: /^Expand Connection pooling/ }));
    const opened = tone("Connection pooling");
    expect(opened).not.toBe(closed);
    expect(opened).not.toBe(current);
  });

  test("the current chapter's heading is the loudest", () => {
    rail("n2");
    expect(tone("Session–Adapter contract")).toBe("text-signal");
  });

  test("a collapsed chapter is the quietest", () => {
    rail("n2");
    expect(tone("Connection pooling")).toBe("text-graphite");
  });
});

describe("chapters are actually separated (note 3, second pass)", () => {
  /**
   * The first attempt put `mt-7 … first:mt-0` on the heading row. That row is
   * always the first child of its own section wrapper, so `first:` matched every
   * chapter and zeroed the gap for all of them — measured live at **0px** between
   * collapsed chapters. The stop rows were supplying the only visible spacing,
   * which is why an expanded rail looked fine and hid it.
   *
   * So the claim is not the size. It is that whatever carries the gap has siblings,
   * because a `first:` variant on an only-child cancels itself.
   */
  const gapCarrier = (title: string) => {
    let el: HTMLElement | null = heading(title);
    while (el && !/(^|\s)mt-\d/.test(el.className)) el = el.parentElement;
    return el;
  };

  test("the element carrying the chapter gap is not an only child", () => {
    rail("n2");
    const carrier = gapCarrier("Connection pooling");
    expect(carrier).toBeTruthy();
    // If this is the first child, `first:mt-0` applies and the gap is nothing.
    expect(carrier!.previousElementSibling).toBeTruthy();
  });

  test("the heading row itself carries no top margin", () => {
    rail("n2");
    const row = heading("Connection pooling").parentElement!;
    expect(row.className).not.toMatch(/(^|\s)mt-\d/);
  });

  test("the first chapter has no gap above it, later ones do", () => {
    rail("n2");
    const first = gapCarrier("Session–Adapter contract")!;
    const second = gapCarrier("Connection pooling")!;
    expect(first.previousElementSibling).toBeNull();
    expect(second.className).toMatch(/(^|\s)mt-\d/);
    // Same element type carrying it in both cases — the `first:` variant is what
    // distinguishes them, not two different structures.
    expect(first.className).toBe(second.className);
  });
});

describe("the route scrolls rather than growing past the viewport (note 3)", () => {
  test("the list is its own scroll region inside a fixed-height rail", () => {
    const { container } = rail("n2");
    const aside = container.querySelector("aside");
    const nav = container.querySelector("nav");
    // `h-full min-h-0` on the rail and `overflow-y-auto min-h-0 flex-1` on the
    // list is what makes a fourteen-stop route scroll instead of pushing the
    // optional row and the footer off the bottom.
    expect(aside!.className).toContain("h-full");
    expect(aside!.className).toContain("min-h-0");
    expect(nav!.className).toContain("overflow-y-auto");
    expect(nav!.className).toContain("min-h-0");
  });
});

describe("the hide control belongs to the rail (note 4, second pass)", () => {
  test("the rail carries its own hide control when one is offered", () => {
    const onHide = vi.fn();
    const journey = splitJourney(
      buildRoute(NODES, NODES.slice(0, -1).map((n, i) => ({ from_id: n.id, to_id: NODES[i + 1].id, kind: "sequence" }))),
      AREAS,
      "n2"
    );
    render(
      <RouteRail
        sections={journey.sections}
        optional={journey.optional}
        currentNodeId="n2"
        onJump={vi.fn()}
        onOpenSection={vi.fn()}
        onExpand={vi.fn()}
        onHide={onHide}
      />
    );
    const hide = screen.getByRole("button", { name: t.session.hideRail });
    fireEvent.click(hide);
    expect(onHide).toHaveBeenCalled();
  });

  test("no control when the page offers no way to hide", () => {
    // The prop is optional: a caller that cannot restore the rail must not be
    // given a button that takes it away.
    rail("n2");
    expect(screen.queryByRole("button", { name: t.session.hideRail })).toBeNull();
  });

  test("the glyph is labelled, not left as decoration", () => {
    const journey = splitJourney(
      buildRoute(NODES, NODES.slice(0, -1).map((n, i) => ({ from_id: n.id, to_id: NODES[i + 1].id, kind: "sequence" }))),
      AREAS,
      "n2"
    );
    render(
      <RouteRail
        sections={journey.sections}
        optional={journey.optional}
        currentNodeId="n2"
        onJump={vi.fn()}
        onOpenSection={vi.fn()}
        onExpand={vi.fn()}
        onHide={vi.fn()}
        compact
      />
    );
    // Present in the compact strip too, where there is no header to put it in.
    expect(screen.getByRole("button", { name: t.session.hideRail })).toBeTruthy();
  });
});

describe("the heading and the chevron are two controls, not one", () => {
  test("clicking the heading opens the chapter overview without collapsing it", () => {
    const { onOpenSection } = rail("n2");
    fireEvent.click(heading("Session–Adapter contract"));
    expect(onOpenSection).toHaveBeenCalledWith("a1");
    // Still open: opening an overview is not a collapse.
    expect(screen.getByText("Identify the BaseAdapter contract")).toBeTruthy();
  });

  test("collapsing does not open the overview", () => {
    const { onOpenSection } = rail("n2");
    fireEvent.click(screen.getByRole("button", { name: /^Collapse Session–Adapter contract/ }));
    expect(onOpenSection).not.toHaveBeenCalled();
  });

  test("a stop hands the node back, not an id", () => {
    const { onJump } = rail("n2");
    fireEvent.click(screen.getByText("Explain the Session–adapter handoff"));
    expect(onJump).toHaveBeenCalled();
    expect(onJump.mock.calls[0][0].id).toBe("n1");
  });
});

/**
 * The rail counts OUTSTANDING work. The node wire now also carries settled gaps
 * — that is what lets the lesson show a cleared gap as cleared instead of
 * deleting it — so the rail has to filter, or clearing a gap would leave the
 * stop still reading "2 unresolved" forever.
 */
describe("the rail counts what is still unresolved", () => {
  // `unresolved` is what puts the caption on screen at all — the rail only
  // captions a stop the server has classified that way.
  const withGaps = (gaps: NodeGap[]) =>
    ({ ...stop("n1", "Explain the Session–adapter handoff", "a1", "requests/sessions.py"),
       understanding: "unresolved", gaps }) as GraphNode;

  const railOf = (target: GraphNode) => {
    const nodes = [target, ...NODES.slice(1)];
    const edges: GraphEdge[] = nodes.slice(0, -1).map((n, i) => ({
      from_id: n.id, to_id: nodes[i + 1].id, kind: "sequence",
    }));
    const journey = splitJourney(buildRoute(nodes, edges), AREAS, "n2");
    return render(
      <RouteRail
        sections={journey.sections}
        optional={journey.optional}
        currentNodeId="n2"
        openSectionId={null}
        onJump={vi.fn()}
        onOpenSection={vi.fn()}
        onExpand={vi.fn()}
      />
    );
  };

  const GAP = (id: string, status: string): NodeGap => ({
    id, kind: "wrong_model", claim: `claim ${id}`, blocking: true, status,
  });

  test("a settled gap does not count against the stop", () => {
    railOf(withGaps([GAP("a", "open"), GAP("b", "verified"), GAP("c", "waived")]));
    expect(screen.getByText(t.rail.unresolvedCount(1))).toBeTruthy();
  });

  test("a stop whose gaps were all cleared is not captioned as unresolved work", () => {
    railOf(withGaps([GAP("a", "verified"), GAP("b", "verified")]));
    expect(screen.queryByText(t.rail.unresolvedCount(2))).toBeNull();
    expect(screen.queryByText(t.rail.unresolvedCount(0))).toBeNull();
  });

  test("only outstanding claims are named in the hover", () => {
    railOf(withGaps([GAP("a", "open"), GAP("b", "verified")]));
    const row = screen.getByText("Explain the Session–adapter handoff").closest("[title]");
    expect(row?.getAttribute("title")).toContain("claim a");
    expect(row?.getAttribute("title")).not.toContain("claim b");
  });
});

/**
 * M0 — a stop the learner answered must not read like one they never opened.
 *
 * The caption used to be keyed on `understanding === "unresolved"`, which
 * excluded the two cases it is most needed for. An `off-topic` answer opens no
 * gaps and is excluded from evidence, so the stop classifies `insufficient`: the
 * learner answered it, decided to move on, and the rail said nothing at all.
 */
describe("a stop says whether it was attempted and whether it was set aside", () => {
  const railOf = (over: Partial<GraphNode>) => {
    const target = {
      ...stop("n1", "Explain the Session–adapter handoff", "a1", "requests/sessions.py"),
      ...over,
    } as GraphNode;
    const nodes = [target, ...NODES.slice(1)];
    const edges: GraphEdge[] = nodes.slice(0, -1).map((n, i) => ({
      from_id: n.id, to_id: nodes[i + 1].id, kind: "sequence",
    }));
    const journey = splitJourney(buildRoute(nodes, edges), AREAS, "n2");
    return render(
      <RouteRail
        sections={journey.sections}
        optional={journey.optional}
        currentNodeId="n2"
        openSectionId={null}
        onJump={vi.fn()}
        onOpenSection={vi.fn()}
        onExpand={vi.fn()}
      />
    );
  };

  const rowOf = (title = "Explain the Session–adapter handoff") =>
    screen.getByText(title).closest("[title]");

  test("an untouched stop is captioned with nothing", () => {
    railOf({ understanding: "insufficient", disposition: "active", attempted: false });
    expect(screen.queryByText(t.rail.attempted)).toBeNull();
    expect(screen.queryByText(t.rail.setAside)).toBeNull();
  });

  test("an off-topic answer is captioned as attempted, not as a failure", () => {
    // Not "needs work": an off-topic answer is evidence of neither understanding
    // nor misunderstanding, so the caption reports what happened and claims
    // nothing about what they know.
    railOf({ understanding: "insufficient", disposition: "active", attempted: true });
    expect(screen.getByText(t.rail.attempted)).toBeTruthy();
    expect(rowOf()?.getAttribute("title")).toBeTruthy();
  });

  test("moving on from it is captioned as set aside", () => {
    railOf({ understanding: "insufficient", disposition: "continued", attempted: true });
    expect(screen.getByText(t.rail.setAside)).toBeTruthy();
  });

  test("a set-aside stop with no gaps still says which decision it was", () => {
    // Three ways to settle a stop and they are not the same thing to a learner:
    // "not now", "stop asking me", and "I already know this". Only the second
    // was ever named.
    const { unmount } = railOf({
      understanding: "unresolved", disposition: "continued", attempted: true,
    });
    expect(screen.getByTitle(t.rail.movedOnHint)).toBeTruthy();
    unmount();

    railOf({ understanding: "unresolved", disposition: "asserted", attempted: true });
    expect(screen.getByTitle(t.rail.assertedHint)).toBeTruthy();
  });

  test("named gaps still outrank the standing caption", () => {
    // A count of open misconceptions is the most actionable thing the rail can
    // say, whatever decision was taken around it.
    railOf({
      understanding: "unresolved",
      disposition: "continued",
      attempted: true,
      gaps: [{ id: "a", kind: "wrong_model", claim: "claim a", blocking: true, status: "open" }],
    });
    expect(screen.getByText(t.rail.unresolvedCount(1))).toBeTruthy();
    expect(screen.queryByText(t.rail.setAside)).toBeNull();
  });

  test("a demonstrated stop is never captioned as set aside", () => {
    // The invariant at the rail: a waiver survives a later answer by design, so
    // a recovered stop routinely carries one. Evidence wins.
    railOf({ understanding: "recovered", disposition: "waived", attempted: true });
    expect(screen.queryByText(t.rail.setAside)).toBeNull();
    expect(screen.queryByText(t.rail.attempted)).toBeNull();
  });
});

/**
 * THE IMPLEMENTATION PHASE IN THE RAIL.
 *
 * The learning route and the implementation stages are two phases of one journey
 * in one column — so the section is asserted for the two things a second
 * navigation system would get wrong: a stage that cannot be entered must not
 * offer itself as a control, and the route above it must go on working exactly
 * as it did.
 */
describe("the implementation phase, below the route", () => {
  const railModel = (over: Partial<ImplementationRail> = {}): ImplementationRail => ({
    status: "active",
    demonstrated: 11,
    required: 11,
    stages: [
      { stage: "plan", state: "done", enterable: true },
      { stage: "locate", state: "done", enterable: true },
      { stage: "implement", state: "current", enterable: true },
      { stage: "validate", state: "ahead", enterable: false },
      { stage: "review", state: "ahead", enterable: false },
    ],
    ...over,
  });

  const stageButton = (label: string) =>
    screen.queryByRole("button", { name: new RegExp(`^${label}`) });

  test("is absent entirely from a session that is not a contribution", () => {
    rail();
    expect(screen.queryByText(t.contribution.railTitle)).toBeNull();
  });

  test("is present but says what opens it while the learner is still learning", () => {
    railWith({
      implementation: railModel({
        status: "locked", demonstrated: 4,
        stages: railModel().stages.map((r) => ({ ...r, state: "ahead" as const, enterable: false })),
      }),
      onEnterStage: vi.fn(),
    });
    expect(screen.getByText(t.contribution.railTitle)).toBeTruthy();
    // The destination is on screen from the first stop — that is the point of
    // showing it locked — but the counter has to say why it is not open.
    expect(screen.getByText(t.contribution.railLocked(4, 11))).toBeTruthy();
    expect(screen.getByText(t.contribution.stages.plan)).toBeTruthy();
  });

  test("a stage that cannot be entered is not a control", () => {
    // NOT a disabled button. A disabled control reads as one that failed; a
    // plain row reads as a step not yet reached, which is what it is.
    const onEnterStage = vi.fn();
    railWith({ implementation: railModel(), onEnterStage });

    expect(stageButton(t.contribution.stages.review)).toBeNull();
    expect(stageButton(t.contribution.stages.implement)).toBeTruthy();
  });

  test("nothing is a control at all while it is locked", () => {
    railWith({
      implementation: railModel({
        status: "locked",
        stages: railModel().stages.map((r) => ({ ...r, state: "ahead" as const, enterable: false })),
      }),
      onEnterStage: vi.fn(),
    });
    expect(stageButton(t.contribution.stages.plan)).toBeNull();
  });

  test("clicking a reached stage opens it", () => {
    const onEnterStage = vi.fn();
    railWith({ implementation: railModel(), onEnterStage });

    fireEvent.click(stageButton(t.contribution.stages.locate)!);
    expect(onEnterStage).toHaveBeenCalledWith("locate");
  });

  test("the current stage is marked as the position in this phase", () => {
    railWith({ implementation: railModel(), onEnterStage: vi.fn() });
    expect(stageButton(t.contribution.stages.implement)!.getAttribute("aria-current"))
      .toBe("step");
    expect(stageButton(t.contribution.stages.plan)!.getAttribute("aria-current"))
      .toBeNull();
  });

  test("the middle phase is named, and is a way back to the gate", () => {
    // journey -> READY TO IMPLEMENT -> implementation. Without this row the
    // middle phase exists only on a screen the learner may have left.
    const onOpenGate = vi.fn();
    railWith({
      implementation: railModel({
        status: "ready",
        stages: railModel().stages.map((r) => ({ ...r, state: "ahead" as const, enterable: false })),
      }),
      onOpenGate,
    });
    fireEvent.click(screen.getByRole("button", { name: t.contribution.readyLabel }));
    expect(onOpenGate).toHaveBeenCalled();
  });

  test("the route above it still works", () => {
    // The two phases share a column; they do not compete for it.
    const onJump = vi.fn();
    railWith({ implementation: railModel(), onEnterStage: vi.fn(), onJump });
    fireEvent.click(screen.getByText(NODES[0].title));
    expect(onJump).toHaveBeenCalledWith(expect.objectContaining({ id: "n1" }));
  });

  test("at strip density it becomes one mark rather than five labels", () => {
    railWith({ implementation: railModel(), onEnterStage: vi.fn(), compact: true });
    expect(screen.queryByText(t.contribution.stages.implement)).toBeNull();
    expect(screen.getByRole("button", { name: t.contribution.railCompact })).toBeTruthy();
  });
});
