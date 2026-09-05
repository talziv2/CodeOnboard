import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import type { Area, GraphEdge, SessionGraph } from "@/lib/api";
import { node } from "@/test/factories";
import { t } from "@/lib/strings";

/**
 * Where a click on the route actually lands.
 *
 * The route offers two kinds of destination that sit one row apart: a chapter,
 * which opens its overview, and a stop inside it, which opens that stop's
 * lesson. This asserts they stay distinct — including for the FIRST stop of a
 * chapter, which is the one case every guard on the chapter introduction lets
 * through: nothing behind it, nothing settled, and a chapter the learner has not
 * been shown yet.
 *
 * Rendering the page rather than a harness, deliberately. The bug this pins was
 * not in the rail (its buttons were always two separate controls) and not in the
 * section projection — it was the page's own arrival effect firing on a graph the
 * learner had just navigated themselves, and only the composition shows that.
 */

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "s1" }),
  useRouter: () => ({ push: vi.fn() }),
}));

// Not under test, and it queries the DOM on a timer to place its spotlight.
vi.mock("@/components/tour/SessionTour", () => ({ default: () => null }));

const api = vi.hoisted(() => ({
  getSession: vi.fn(),
  getLesson: vi.fn(),
  jump: vi.fn(),
  advance: vi.fn(),
  setScope: vi.fn(),
  resetSession: vi.fn(),
  sessionStart: vi.fn(),
  getContribution: vi.fn(),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  ...api,
}));

import SessionPage from "@/app/session/[id]/page";

const UNINFORMED = "Uninformed search algorithms";
const INFORMED = "Informed search algorithms";

const AREAS: Area[] = [
  { id: "uninformed", title: UNINFORMED, why: "Where the frontier is expanded blindly.", order: 0 },
  { id: "informed", title: INFORMED, why: "Where a heuristic steers the frontier.", order: 1 },
];

/** Two chapters: the learner is mid-way through the first, and has never opened the second. */
const IDS = ["u1", "u2", "i1", "i2", "i3"] as const;
const AREA_OF: Record<string, string> = {
  u1: "uninformed", u2: "uninformed", i1: "informed", i2: "informed", i3: "informed",
};
const TITLE_OF: Record<string, string> = {
  u1: "Walk the breadth-first frontier",
  u2: "Explain depth-first backtracking",
  i1: "Explain what a heuristic buys you",
  i2: "Trace greedy best-first",
  i3: "Explain A* admissibility",
};

const EDGES: GraphEdge[] = IDS.slice(0, -1).map((id, i) => ({
  from_id: id,
  to_id: IDS[i + 1],
  kind: "sequence",
}));

function graph(currentId: string, jumped: boolean): SessionGraph {
  return {
    session_id: "s1",
    repo_url: "https://github.com/psf/requests",
    goal: { primary_goal: "understand search", depth: "moderate" },
    current_node_id: currentId,
    has_plan: true,
    nodes: IDS.map((id) =>
      node(id, {
        title: TITLE_OF[id],
        objective: `Explain ${TITLE_OF[id]}`,
        area_id: AREA_OF[id],
        // Only the first chapter has anything behind it. The second is untouched,
        // which is exactly the state that used to introduce itself over a lesson.
        visited: id === "u1",
      })
    ),
    edges: EDGES,
    areas: AREAS,
    readiness: 0.2,
    progress: {
      goal_readiness: 0.2, core_total: 5, core_demonstrated: 1, core_in_progress: 0,
      core_unassessed: 4, journey_progress: 0.2, stops_settled: 1, stops_total: 5,
      assessed_coverage: 0.2, assessed: 1, detours: [], skipped: 0,
      optional_total: 0, optional_completed: 0,
      ready_to_implement: {
        ready: false, required: 0, demonstrated: 0, blockers: [],
      },
    },
    understanding: {
      patterns: [], gap_patterns: [],
      totals: { strength: 0, recovered: 0, unresolved: 0, insufficient: 5 },
      assessed: 0, total: 5, by_area: {}, by_kind: {},
      needs_work: [], set_aside: [], recovered: [], nodes: [],
    },
    journey_events: [],
    arrival: jumped
      ? { node_id: currentId, kind: "jumped", from_node_id: "u2", at: "2026-08-31T10:00:00" }
      : null,
  };
}

/** The graph the next `getSession` will answer with. */
let current = "u2";
let jumped = false;

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  // Wide band: the compact strip drops chapter headings, and headings are half
  // the claim here.
  window.innerWidth = 1600;
  current = "u2";
  jumped = false;
  api.getSession.mockImplementation(async () => graph(current, jumped));
  api.getLesson.mockImplementation(async () => ({
    node_id: current,
    lesson: {
      walkthrough: `Walkthrough for ${current}`,
      prompt: `Question about ${current}`,
      prompt_kind: "explain",
    },
  }));
  api.jump.mockImplementation(async (_id: string, nodeId: string) => {
    current = nodeId;
    jumped = true;
    return { current_node_id: nodeId, arrival: null };
  });
  // Not a contribution by default: every test above this line predates the
  // contribution journey and must stay unaffected by it.
  api.getContribution.mockResolvedValue({
    available: false, task: "", boundary: {},
    ready: { ready: false, required: 0, demonstrated: 0, blockers: [] },
    state: null, validation_command: "",
  });
});

/** The h2 the lesson column is showing — a node title, or a chapter title. */
async function heading(): Promise<string> {
  const h = await screen.findByRole("heading", { level: 2 });
  return h.textContent ?? "";
}

async function openSession() {
  render(<SessionPage />);
  // Mid-chapter in the first section, on its lesson.
  await waitFor(() => expect(screen.getByText(TITLE_OF.u2)).toBeTruthy());
  await waitFor(async () => expect(await heading()).toBe(TITLE_OF.u2));
}

/** Expand a collapsed chapter in the rail. Must navigate nowhere by itself. */
async function expand(title: string) {
  await userEvent.click(
    screen.getByRole("button", { name: t.rail.expandSection(title) })
  );
}

/** Click a stop by its title, from the rail. */
async function clickStop(id: string) {
  const rail = document.querySelector('[data-tour="rail"]') as HTMLElement;
  const row = [...rail.querySelectorAll("button")].find((b) =>
    b.textContent?.includes(TITLE_OF[id])
  );
  await userEvent.click(row!);
}

describe("a click on the route resolves to the destination that was clicked", () => {
  test("the chapter heading opens the chapter overview", async () => {
    await openSession();
    await expand(INFORMED);

    await userEvent.click(
      screen.getByRole("button", { name: t.rail.openSection(INFORMED) })
    );

    expect(await heading()).toBe(INFORMED);
    expect(screen.getByText(t.section.label)).toBeTruthy();
    // Opening a chapter is not moving: the session pointer stays where it was.
    expect(api.jump).not.toHaveBeenCalled();
  });

  test("THE FIRST stop of a freshly expanded chapter opens ITS lesson, not the chapter", async () => {
    await openSession();
    await expand(INFORMED);

    await clickStop("i1");

    await waitFor(() => expect(api.jump).toHaveBeenCalledWith("s1", "i1"));
    expect(await heading()).toBe(TITLE_OF.i1);
    expect(screen.queryByText(t.section.label)).toBeNull();
  });

  test("a later stop of the same chapter opens its own lesson too", async () => {
    await openSession();
    await expand(INFORMED);

    await clickStop("i2");

    await waitFor(() => expect(api.jump).toHaveBeenCalledWith("s1", "i2"));
    expect(await heading()).toBe(TITLE_OF.i2);
    expect(screen.queryByText(t.section.label)).toBeNull();
  });

  test("a lesson picked FROM the chapter overview replaces it, and does not reopen it", async () => {
    await openSession();
    await expand(INFORMED);
    await userEvent.click(
      screen.getByRole("button", { name: t.rail.openSection(INFORMED) })
    );
    expect(await heading()).toBe(INFORMED);

    // The overview's own lesson list — its whole purpose is being a way in.
    await userEvent.click(screen.getByText(t.section.startHere(TITLE_OF.i1)));

    await waitFor(() => expect(api.jump).toHaveBeenCalledWith("s1", "i1"));
    expect(await heading()).toBe(TITLE_OF.i1);
    expect(screen.queryByText(t.section.label)).toBeNull();
  });

  test("expanding a chapter navigates nowhere at all", async () => {
    await openSession();
    await expand(INFORMED);

    expect(api.jump).not.toHaveBeenCalled();
    expect(await heading()).toBe(TITLE_OF.u2);
    expect(screen.queryByText(t.section.label)).toBeNull();
  });
});

/**
 * The Tutor's CHAT control is on the page WITHOUT any environment set.
 *
 * THE DEFECT THIS PINS, and why it belongs in the page test rather than beside
 * `tutorUi`. The flag defaulting off was invisible in exactly this composition:
 * every Tutor unit test passed, `TutorPanel.test.tsx` passed, the five routes were
 * covered — and a fresh clone still rendered a lesson with no way into any of it,
 * because the one line that mattered was a `&&` in this file reading an unset
 * `NEXT_PUBLIC_*`. Asserting `tutorUi()` alone would not have caught it; asserting
 * the rendered control does.
 *
 * `delete` rather than assignment for the default case, because Next inlines
 * `NEXT_PUBLIC_*` at build time and an absent variable is the case that ships.
 */
describe("the Tutor's way in", () => {
  const setTutor = (value: string | undefined) => {
    if (value === undefined) delete process.env.NEXT_PUBLIC_CODEONBOARD_TUTOR;
    else process.env.NEXT_PUBLIC_CODEONBOARD_TUTOR = value;
  };

  afterEach(() => setTutor(undefined));

  test("a lesson offers Chat with nothing configured at all", async () => {
    setTutor(undefined);
    await openSession();
    expect(screen.getByRole("button", { name: t.session.showChat })).toBeTruthy();
  });

  test("it sits beside `Show source`, as its peer", async () => {
    setTutor(undefined);
    await openSession();
    // Same variant, same size, same place — a different prominence would say the
    // two are different kinds of thing.
    expect(screen.getByRole("button", { name: t.session.showSource })).toBeTruthy();
    expect(screen.getByRole("button", { name: t.session.showChat })).toBeTruthy();
  });

  test("an explicit `0` removes it — the escape hatch still works", async () => {
    setTutor("0");
    await openSession();
    expect(screen.queryByRole("button", { name: t.session.showChat })).toBeNull();
    // And it takes only the Tutor with it.
    expect(screen.getByRole("button", { name: t.session.showSource })).toBeTruthy();
  });
});


/**
 * THE PHASE BOUNDARY between the journey and the implementation stage.
 *
 * Found by walking the demo: after pressing *Start implementing*, every stop
 * selected from the route rail still rendered the contribution stage's Locate
 * view. The lesson was unreachable for the rest of the session.
 *
 * The cause was in the page's composition, which is why this is a page test and
 * not a `lib/` one: `centreSurface` decides correctly given a request, but
 * `handleJump` changed the current node and never made the request. The pure
 * function was fine; the wiring was the bug.
 *
 * The invariant, both ways round:
 *
 *   selecting a stop            -> the lesson, ALWAYS, whatever the stage is
 *   the stage, when not asked   -> only as the default for someone who has not
 *                                  navigated
 */
describe("the journey and the implementation stage do not fight over the centre", () => {
  const CONTRIBUTION = {
    available: true,
    task: "Add Jar.get_all(name) and cover its boundary cases with tests.",
    boundary: {
      target: [{ file: "src/app/jar.py", symbol: "Jar", why_here: "it belongs here" }],
      must_not_change: [],
      existing_tests: [],
      edge_cases: [],
      conventions: [],
    },
    ready: { ready: true, required: 2, demonstrated: 2, blockers: [] },
    state: {
      stage: "locate" as const,
      plan: { steps: [{ title: "Add the method", detail: "d" }] },
      patch: [],
      scope_check: null,
      review: null,
      pr: null,
      proceeded_unready: false,
      validation_command: "pytest -q",
    },
    validation_command: "pytest -q",
  };

  beforeEach(() => {
    api.getContribution.mockResolvedValue(CONTRIBUTION);
  });

  test("the stage owns the centre for a learner who has not navigated", async () => {
    render(<SessionPage />);
    await waitFor(() =>
      expect(screen.getByText(t.contribution.locateHeading)).toBeTruthy()
    );
  });

  test("SELECTING A STOP SHOWS ITS LESSON, not the implementation stage", async () => {
    // The regression, exactly as it was hit: mid-stage, click a stop in the rail.
    render(<SessionPage />);
    await waitFor(() =>
      expect(screen.getByText(t.contribution.locateHeading)).toBeTruthy()
    );

    await clickStop("u1");

    await waitFor(() => expect(api.jump).toHaveBeenCalledWith("s1", "u1"));
    expect(await heading()).toBe(TITLE_OF.u1);
    expect(screen.queryByText(t.contribution.locateHeading)).toBeNull();
  });

  test("and the way back to the stage is offered once it is off screen", async () => {
    render(<SessionPage />);
    await waitFor(() =>
      expect(screen.getByText(t.contribution.locateHeading)).toBeTruthy()
    );
    // Not offered while the stage IS the centre — it would point at itself.
    expect(screen.queryByRole("button", { name: t.contribution.resume })).toBeNull();

    await clickStop("u1");

    await waitFor(() =>
      expect(screen.getByRole("button", { name: t.contribution.resume })).toBeTruthy()
    );
  });

  test("that way back returns to the stage the learner left", async () => {
    render(<SessionPage />);
    await waitFor(() =>
      expect(screen.getByText(t.contribution.locateHeading)).toBeTruthy()
    );
    await clickStop("u1");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: t.contribution.resume })).toBeTruthy()
    );

    await userEvent.click(
      screen.getByRole("button", { name: t.contribution.resume })
    );

    await waitFor(() =>
      expect(screen.getByText(t.contribution.locateHeading)).toBeTruthy()
    );
  });

  test("a session with no contribution is untouched by any of it", async () => {
    api.getContribution.mockResolvedValue({
      ...CONTRIBUTION, available: false, state: null,
    });
    await openSession();

    await clickStop("u1");

    expect(await heading()).toBe(TITLE_OF.u1);
    expect(screen.queryByRole("button", { name: t.contribution.resume })).toBeNull();
  });
});

/**
 * ONE COLUMN, TWO PHASES.
 *
 * The learning route and the implementation stages live in the same rail, and
 * the reason they can is that neither owns the centre: `centreSurface` decides
 * that from what the learner last asked for. These assert the composition, which
 * is where the previous version of this went wrong — `implementationRail` and
 * `centreSurface` were both correct on their own while the page wired one of
 * them to nothing.
 */
describe("the implementation phase sits in the route rail", () => {
  const READY = { ready: true, required: 11, demonstrated: 11, blockers: [] };
  const CONTRIBUTION = {
    available: true,
    task: "Add Jar.get_all(name) and cover its boundary cases with tests.",
    boundary: {
      target: [{ file: "src/app/jar.py", symbol: "Jar", why_here: "it belongs here" }],
      must_not_change: [], existing_tests: [], edge_cases: [], conventions: [],
    },
    ready: READY,
    state: {
      stage: "locate" as const,
      plan: { steps: [{ title: "Add the method", detail: "d" }] },
      patch: [], scope_check: null, review: null, pr: null,
      proceeded_unready: false, validation_command: "pytest -q",
    },
    validation_command: "pytest -q",
  };

  /** A stage row IN THE RAIL — the stepper carries the same five labels. */
  const railStage = (label: string) => {
    const rail = document.querySelector('[data-tour="rail"]') as HTMLElement;
    return within(rail).queryByRole("button", { name: new RegExp(`^${label}`) });
  };

  test("is visible, locked, and inert while the learner is still learning", async () => {
    api.getContribution.mockResolvedValue({
      ...CONTRIBUTION,
      ready: { ready: false, required: 11, demonstrated: 4, blockers: [] },
      state: null,
    });
    await openSession();

    // The destination is on screen from the first stop — that is what makes the
    // two read as one journey rather than two products.
    const rail = document.querySelector('[data-tour="rail"]') as HTMLElement;
    expect(within(rail).getByText(t.contribution.railTitle)).toBeTruthy();
    expect(within(rail).getByText(t.contribution.railLocked(4, 11))).toBeTruthy();
    // Nothing may be entered from here, and nothing may look as if it could be.
    expect(railStage(t.contribution.stages.plan)).toBeNull();
    // And the lesson is untouched by any of it.
    expect(await heading()).toBe(TITLE_OF.u2);
  });

  test("a rail stage opens the implementation surface at that stage", async () => {
    api.getContribution.mockResolvedValue(CONTRIBUTION);
    render(<SessionPage />);
    await waitFor(() =>
      expect(screen.getByText(t.contribution.locateHeading)).toBeTruthy()
    );
    // Go and read a lesson first, so the centre is genuinely on the journey.
    await clickStop("u1");
    expect(await heading()).toBe(TITLE_OF.u1);

    await userEvent.click(railStage(t.contribution.stages.plan)!);

    await waitFor(() =>
      expect(screen.getByText(t.contribution.planHeading)).toBeTruthy()
    );
  });

  test("the route stays live once implementation has begun", async () => {
    // Both phases in one column, neither disabling the other.
    api.getContribution.mockResolvedValue(CONTRIBUTION);
    render(<SessionPage />);
    await waitFor(() =>
      expect(screen.getByText(t.contribution.locateHeading)).toBeTruthy()
    );

    await clickStop("u1");

    expect(await heading()).toBe(TITLE_OF.u1);
    // The implementation section did not go away when the lesson took the centre.
    const rail = document.querySelector('[data-tour="rail"]') as HTMLElement;
    expect(within(rail).getByText(t.contribution.railTitle)).toBeTruthy();
    expect(railStage(t.contribution.stages.locate)).toBeTruthy();
  });

  test("the rail and the stepper never point at different stages", async () => {
    // They are two renderings of one piece of state. When `viewing` was local to
    // the stage, the rail would have gone on marking the server's stage.
    api.getContribution.mockResolvedValue(CONTRIBUTION);
    render(<SessionPage />);
    await waitFor(() =>
      expect(screen.getByText(t.contribution.locateHeading)).toBeTruthy()
    );
    expect(railStage(t.contribution.stages.locate)!.getAttribute("aria-current"))
      .toBe("step");

    // Step back through the phase's own header — the stepper that used to sit
    // inside the panel is gone, because two navigations for one phase is the
    // thing this whole boundary exists to remove.
    const bar = screen.getByRole("group", { name: t.contribution.railTitle });
    await userEvent.click(
      within(bar).getByRole("button", { name: t.contribution.stages.plan })
    );

    await waitFor(() =>
      expect(railStage(t.contribution.stages.plan)!.getAttribute("aria-current"))
        .toBe("step")
    );
    expect(railStage(t.contribution.stages.locate)!.getAttribute("aria-current"))
      .toBeNull();
  });

  test("the way back returns to the stage the learner was actually on", async () => {
    // Not the server's stage: they stepped back to Plan, read a lesson, and came
    // back — landing on Locate would lose their place.
    api.getContribution.mockResolvedValue(CONTRIBUTION);
    render(<SessionPage />);
    await waitFor(() =>
      expect(screen.getByText(t.contribution.locateHeading)).toBeTruthy()
    );
    await userEvent.click(railStage(t.contribution.stages.plan)!);
    await waitFor(() =>
      expect(screen.getByText(t.contribution.planHeading)).toBeTruthy()
    );

    await clickStop("u1");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: t.contribution.resume })).toBeTruthy()
    );
    await userEvent.click(
      screen.getByRole("button", { name: t.contribution.resume })
    );

    await waitFor(() =>
      expect(screen.getByText(t.contribution.planHeading)).toBeTruthy()
    );
    expect(screen.queryByText(t.contribution.locateHeading)).toBeNull();
  });

  test("an ordinary session's rail is exactly what it was", async () => {
    await openSession();
    expect(screen.queryByText(t.contribution.railTitle)).toBeNull();
  });
});

/**
 * THE PHASE BOUNDARY, IN THE CHROME.
 *
 * `Learn / Route` and `Lesson / Understanding` choose which view of a STOP you
 * are reading. During Plan -> Locate -> Continue in Claude there is no stop on
 * screen, so they name views that do not exist — and pressing `Understanding`
 * there rendered the understanding surface of whichever node happened to be
 * current, which is the learning phase appearing under implementation chrome.
 *
 * These are page tests because the defect is in the COMPOSITION: both bars are
 * correct components, and the question is only which one the page mounts. The
 * fix must not be CSS — a hidden tab is still focusable, still in the
 * accessibility tree, and still a control that does the wrong thing.
 */
describe("each phase has its own chrome", () => {
  const READY = { ready: true, required: 2, demonstrated: 2, blockers: [] };
  const mid = (stage: "plan" | "locate") => ({
    available: true,
    task: "Add Jar.get_all(name).",
    boundary: {
      target: [{ file: "src/app/jar.py", symbol: "Jar", why_here: "here" }],
      must_not_change: [], existing_tests: [], edge_cases: [], conventions: [],
    },
    ready: READY,
    state: {
      stage, plan: { steps: [{ title: "Add it", detail: "d" }] }, patch: [],
      scope_check: null, review: null, pr: null, proceeded_unready: false,
      validation_command: "pytest -q",
    },
    validation_command: "pytest -q",
  });

  const learningTabs = () => [
    screen.queryByRole("button", { name: t.session.mode.learn }),
    screen.queryByRole("button", { name: t.session.tab.lesson }),
    screen.queryByRole("button", { name: t.session.tab.understanding }),
  ];

  test("the learning phase keeps its tabs", async () => {
    await openSession();
    for (const control of learningTabs()) expect(control).toBeTruthy();
    expect(screen.queryByRole("group", { name: t.contribution.railTitle })).toBeNull();
  });

  test("the implementation phase shows implementation navigation ONLY", async () => {
    api.getContribution.mockResolvedValue(mid("locate"));
    render(<SessionPage />);
    await waitFor(() =>
      expect(screen.getByText(t.contribution.locateHeading)).toBeTruthy()
    );

    // Not hidden — not mounted. A hidden tab is still focusable and still does
    // the wrong thing when it is pressed.
    for (const control of learningTabs()) expect(control).toBeNull();

    const bar = screen.getByRole("group", { name: t.contribution.railTitle });
    expect(within(bar).getByRole("button", { name: t.contribution.stages.plan })).toBeTruthy();
    expect(within(bar).getByRole("button", { name: t.contribution.stages.locate })).toBeTruthy();
    expect(within(bar).getByRole("button", { name: t.contribution.stages.handoff })).toBeTruthy();
  });

  test("the header marks the step that is actually on screen", async () => {
    api.getContribution.mockResolvedValue(mid("locate"));
    render(<SessionPage />);
    await waitFor(() =>
      expect(screen.getByText(t.contribution.locateHeading)).toBeTruthy()
    );
    const bar = screen.getByRole("group", { name: t.contribution.railTitle });
    expect(
      within(bar).getByRole("button", { name: t.contribution.stages.locate })
        .getAttribute("aria-current")
    ).toBe("step");

    await userEvent.click(
      within(bar).getByRole("button", { name: t.contribution.stages.plan })
    );

    await waitFor(() =>
      expect(screen.getByText(t.contribution.planHeading)).toBeTruthy()
    );
    expect(
      within(bar).getByRole("button", { name: t.contribution.stages.plan })
        .getAttribute("aria-current")
    ).toBe("step");
  });

  test("a step that cannot be entered yet is not a working control", async () => {
    api.getContribution.mockResolvedValue(mid("plan"));
    render(<SessionPage />);
    await waitFor(() =>
      expect(screen.getByText(t.contribution.planHeading)).toBeTruthy()
    );
    const bar = screen.getByRole("group", { name: t.contribution.railTitle });
    const ahead = within(bar).getByRole("button", { name: t.contribution.stages.handoff });
    expect(ahead.getAttribute("aria-disabled")).toBe("true");

    await userEvent.click(ahead);

    // Still on Plan: pressing it did nothing rather than half-navigating.
    expect(screen.getByText(t.contribution.planHeading)).toBeTruthy();
  });

  test("opening a learning stop restores the learning chrome, with a way back", async () => {
    api.getContribution.mockResolvedValue(mid("locate"));
    render(<SessionPage />);
    await waitFor(() =>
      expect(screen.getByText(t.contribution.locateHeading)).toBeTruthy()
    );

    await clickStop("u1");

    expect(await heading()).toBe(TITLE_OF.u1);
    for (const control of learningTabs()) expect(control).toBeTruthy();
    expect(screen.queryByRole("group", { name: t.contribution.railTitle })).toBeNull();
    // And the door back is offered, or the learner is stranded in the other
    // direction — the same defect pointing the other way.
    expect(screen.getByRole("button", { name: t.contribution.resume })).toBeTruthy();
  });

  test("the way back out of the implementation phase is labelled", async () => {
    api.getContribution.mockResolvedValue(mid("locate"));
    render(<SessionPage />);
    await waitFor(() =>
      expect(screen.getByText(t.contribution.locateHeading)).toBeTruthy()
    );

    await userEvent.click(
      screen.getByRole("button", { name: t.contribution.backToJourney })
    );

    expect(await heading()).toBe(TITLE_OF.u2);
    for (const control of learningTabs()) expect(control).toBeTruthy();
  });
});
