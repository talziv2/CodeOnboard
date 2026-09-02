import { render, screen, waitFor } from "@testing-library/react";
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
