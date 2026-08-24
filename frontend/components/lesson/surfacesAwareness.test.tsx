import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useCallback, useEffect, useState } from "react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { Lesson, RespondResult, SessionGraph } from "@/lib/api";
import { node } from "@/test/factories";
import SurfaceTabs from "@/components/lesson/SurfaceTabs";
import {
  activeTab as tabOf, INITIAL_TABS, reduceTabs, surfaceForTab, tabsFor,
  type TabEvent, type TabState,
} from "@/lib/surfaceTabs";
import type { Surface } from "@/lib/lessonSurfaces";
import { t } from "@/lib/strings";

/**
 * S4's gate, and R1: **a change in the unattended surface is announced in the
 * attended one.**
 *
 * R1 is §13's surviving objection to tabs, and it is a real failure mode rather
 * than a theoretical one — adaptation that happens where nobody is looking is the
 * "adaptation is invisible" problem in a new costume. The mitigation is three
 * deliberately redundant signals, and the redundancy is the design: the dot is
 * small, and a learner who never opens the verdict never sees the consequence line.
 *
 * What is asserted here is the pair that S4 wires: the dot appears on the tab that
 * changed and not on the one being watched, and the consequence line offers the one
 * click. The brief's counters are the third and were already true — they render in
 * both surfaces, unchanged since L3.
 */

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/flags", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/flags")>()),
  lessonUi: () => "surfaces",
}));

const api = vi.hoisted(() => ({
  getLesson: vi.fn(),
  respond: vi.fn(),
  requestVerification: vi.fn(),
  advance: vi.fn(),
  retry: vi.fn(),
  respondToVerification: vi.fn(),
  waive: vi.fn(),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  ...api,
}));

/**
 * The server's retry offer, which M2 made the single source of "what now".
 *
 * `answer` while the unit's own prompt is still live — before any graded answer,
 * which is the only time it may be answered — and `verify`/`reassess` afterwards.
 * Supplied on the fixtures because the panel no longer derives any of this: the
 * budgets and the answered-question history it depends on are server-side.
 */
const LIVE_PROMPT = {
  available: true,
  mechanism: "answer" as const,
  reason: "",
  gap_id: null,
  reassessments_left: 2,
};
const CAN_VERIFY = {
  available: true,
  mechanism: "verify" as const,
  reason: "",
  gap_id: "g1",
  reassessments_left: 2,
};
const CAN_REASSESS = {
  available: true,
  mechanism: "reassess" as const,
  reason: "",
  gap_id: null,
  reassessments_left: 2,
};
const NOTHING_LEFT = {
  available: false,
  mechanism: null,
  reason: "objective_met",
  gap_id: null,
  reassessments_left: 2,
};

const LESSON: Lesson = {
  node_id: "n1",
  lesson: {
    walkthrough: "The walkthrough body.",
    prompt: "What does sending through a Session change?",
    prompt_kind: "explain",
    setup: "The setup half.",
    reveal: "The explanation.",
    takeaway: "The takeaway.",
  },
  retry: LIVE_PROMPT,
};

const GAP = { id: "g1", kind: "wrong_model", claim: "A connected graph cannot fail.", blocking: true };

/** A wrong answer that rewrote the stop: the case R1 exists for. */
const RETAUGHT: RespondResult = {
  classification: "confused",
  rationale: "That is not what the code does.",
  understanding_state: "failed",
  mutation: { kind: "none" },
  adaptation: { kind: "reteach", retaught: true },
  current_node_id: "n1",
  gaps: [GAP],
  retry: CAN_VERIFY,
};

/** A wrong answer that changed nothing in Lesson. */
const HINTED: RespondResult = {
  ...RETAUGHT,
  adaptation: { kind: "hint", text: "Look at what h() returns." },
  retry: CAN_REASSESS,
};

const NODE = node("n1", {
  title: "Understand the Graph",
  objective: "Explain what Graph owns.",
  gaps: [GAP],
  anchors: [{ file: "search.py", symbol: "Graph", line_start: 1, line_end: 20 }],
});

/**
 * Already answered once, so the explanation is unlocked.
 *
 * Needed because on a FIRST answer, even a hint changes Lesson — the explanation
 * appears there, which is material the learner cannot see from Understanding. That
 * is a real change and is reported. To test the "nothing changed" case at all, the
 * reveal has to be unlocked already.
 */
const ANSWERED = node("n1", {
  title: "Understand the Graph",
  objective: "Explain what Graph owns.",
  gaps: [GAP],
  anchors: [{ file: "search.py", symbol: "Graph", line_start: 1, line_end: 20 }],
  attempts: [
    {
      answer: "An older answer.",
      classification: "partial",
      rationale: "Partly.",
      at: "2026-08-20T09:00:00+00:00",
    },
  ],
});

const graph = (): SessionGraph => ({
  session_id: "s1",
  repo_url: "https://github.com/psf/requests",
  goal: {},
  current_node_id: "n1",
  nodes: [NODE],
  edges: [],
  readiness: 0,
  progress: {} as never,
  understanding: {} as never,
});

const TABS = tabsFor("surfaces");

/** The session page's tab and awareness wiring, and nothing else from it. */
function Harness({
  Panel,
  which = NODE,
}: {
  Panel: typeof import("@/components/LessonPanel").default;
  which?: typeof NODE;
}) {
  const [tabState, setTabState] = useState<TabState>(INITIAL_TABS);
  const [unseen, setUnseen] = useState<Surface[]>([]);
  const dispatchTab = useCallback(
    (event: TabEvent) => setTabState((c) => reduceTabs(c, event, TABS)),
    []
  );
  const tab = tabOf(tabState, TABS);
  useEffect(() => {
    setUnseen((current) =>
      current.includes(tab as Surface) ? current.filter((x) => x !== tab) : current
    );
  }, [tab]);

  return (
    <>
      <SurfaceTabs
        tabs={TABS}
        active={tab}
        changed={unseen}
        onPick={(picked) => dispatchTab({ kind: "picked", tab: picked })}
        onSwitchMode={(picked) => dispatchTab({ kind: "switchedMode", mode: picked })}
      />
      <Panel
        surface={surfaceForTab(tab)}
        onSurfaceChanged={(changed) => {
          if (changed === tab) return;
          setUnseen((current) => (current.includes(changed) ? current : [...current, changed]));
        }}
        onGoToSurface={(target) => dispatchTab({ kind: "picked", tab: target })}
        sessionId="s1"
        nodeId="n1"
        node={which}
        position={2}
        total={16}
        isPrerequisite={false}
        graph={graph()}
        onFileClick={vi.fn()}
        onAdvance={vi.fn()}
        onRespond={vi.fn()}
        finished={false}
        onFinish={vi.fn()}
        onLeave={vi.fn()}
      />
    </>
  );
}

async function panel() {
  return (await import("@/components/LessonPanel")).default;
}

const activeTab = () =>
  screen.getAllByRole("button").find((b) => b.getAttribute("aria-current") === "page")
    ?.textContent;
const textareas = () => screen.queryAllByPlaceholderText("Write your answer…");
const dotOn = (tab: "lesson" | "understanding" | "map") =>
  screen.queryByText(t.session.tabChanged(t.session.tab[tab])) !== null;

beforeEach(() => {
  vi.clearAllMocks();
  api.getLesson.mockResolvedValue(LESSON);
  api.respond.mockResolvedValue(RETAUGHT);
});

describe("R1 · a change where nobody is looking is announced where they are", () => {
  test("answering marks Lesson when the rewrite happens elsewhere", async () => {
    // The learner answers in Understanding. The stop is re-taught, which is a change
    // to LESSON — the one surface they cannot see.
    const user = userEvent.setup();
    render(<Harness Panel={await panel()} />);
    await screen.findByText(LESSON.lesson.setup!);

    await user.click(screen.getByRole("button", { name: "Understanding" }));
    expect(dotOn("lesson")).toBe(false);

    await user.type(textareas()[0], "A wrong answer.");
    await user.click(screen.getAllByRole("button", { name: t.lesson.submit })[0]);
    await screen.findByText(RETAUGHT.rationale!);

    await waitFor(() => expect(dotOn("lesson")).toBe(true));
    // And the tab did not move to show them — R5 still holds while R1 is satisfied,
    // which is the whole point of announcing rather than navigating.
    expect(activeTab()).toBe("Understanding");
  });

  test("an answer that changed nothing in Lesson marks nothing", async () => {
    // A hint is help inside the verdict, and on an ALREADY-ANSWERED stop the
    // explanation is already there — so Lesson genuinely did not change. Marking it
    // anyway would train the learner to ignore the dot, which is the only way to
    // break a signal that cannot be turned off.
    api.respond.mockResolvedValue(HINTED);
    const user = userEvent.setup();
    render(<Harness Panel={await panel()} which={ANSWERED} />);
    await screen.findByText(LESSON.lesson.setup!);

    await user.click(screen.getByRole("button", { name: "Understanding" }));
    await user.type(textareas()[0], "A wrong answer.");
    await user.click(screen.getAllByRole("button", { name: t.lesson.submit })[0]);
    await screen.findByText(HINTED.rationale!);

    expect(dotOn("lesson")).toBe(false);
  });

  test("visiting the marked tab clears it", async () => {
    const user = userEvent.setup();
    render(<Harness Panel={await panel()} />);
    await screen.findByText(LESSON.lesson.setup!);
    await user.click(screen.getByRole("button", { name: "Understanding" }));
    await user.type(textareas()[0], "A wrong answer.");
    await user.click(screen.getAllByRole("button", { name: t.lesson.submit })[0]);
    await screen.findByText(RETAUGHT.rationale!);
    await waitFor(() => expect(dotOn("lesson")).toBe(true));

    await user.click(screen.getByRole("button", { name: "Lesson" }));
    // Looking at it is what makes "you have not seen this" false.
    expect(dotOn("lesson")).toBe(false);
  });

  test("the tab being watched is never marked", async () => {
    // A dot on the tab you are already looking at reports a change to the person
    // watching it happen.
    const user = userEvent.setup();
    render(<Harness Panel={await panel()} />);
    await screen.findByText(LESSON.lesson.setup!);
    await user.click(screen.getByRole("button", { name: "Understanding" }));
    await user.type(textareas()[0], "A wrong answer.");
    await user.click(screen.getAllByRole("button", { name: t.lesson.submit })[0]);
    await screen.findByText(RETAUGHT.rationale!);

    expect(dotOn("understanding")).toBe(false);
  });
});

describe("the second signal: the consequence line offers the click", () => {
  test("`Read it` appears on a rewrite and takes the learner there", async () => {
    const user = userEvent.setup();
    render(<Harness Panel={await panel()} />);
    await screen.findByText(LESSON.lesson.setup!);
    await user.click(screen.getByRole("button", { name: "Understanding" }));
    await user.type(textareas()[0], "A wrong answer.");
    await user.click(screen.getAllByRole("button", { name: t.lesson.submit })[0]);
    await screen.findByText(RETAUGHT.rationale!);

    const readIt = await screen.findByRole("button", { name: t.lesson.readIt });
    await user.click(readIt);

    // A learner click, so the tab moves — and it moves through the same reducer
    // everything else goes through.
    expect(activeTab()).toBe("Lesson");
    expect(await screen.findByText(LESSON.lesson.setup!)).toBeTruthy();
  });

  test("no `Read it` when nothing in Lesson changed", async () => {
    // Sending the learner to look at nothing is worse than not offering.
    api.respond.mockResolvedValue(HINTED);
    const user = userEvent.setup();
    render(<Harness Panel={await panel()} which={ANSWERED} />);
    await screen.findByText(LESSON.lesson.setup!);
    await user.click(screen.getByRole("button", { name: "Understanding" }));
    await user.type(textareas()[0], "A wrong answer.");
    await user.click(screen.getAllByRole("button", { name: t.lesson.submit })[0]);
    await screen.findByText(HINTED.rationale!);

    expect(screen.queryByRole("button", { name: t.lesson.readIt })).toBeNull();
  });

  test("a first answer marks Lesson even for a hint, because the explanation arrives", async () => {
    // The other side of the same rule, asserted so the exclusion above is not
    // mistaken for "hints never matter". Unlocking the explanation IS a change to
    // Lesson, and it is one the learner cannot see from Understanding.
    api.respond.mockResolvedValue(HINTED);
    const user = userEvent.setup();
    render(<Harness Panel={await panel()} />);
    await screen.findByText(LESSON.lesson.setup!);
    await user.click(screen.getByRole("button", { name: "Understanding" }));
    await user.type(textareas()[0], "A wrong answer.");
    await user.click(screen.getAllByRole("button", { name: t.lesson.submit })[0]);
    await screen.findByText(HINTED.rationale!);

    await waitFor(() => expect(dotOn("lesson")).toBe(true));
  });
});

// ── M3: what changed, not only that something did ────────────────────────────

describe("the rewritten material names what it answers", () => {
  const RETAUGHT_AT = "2026-03-01T10:00:00.000Z";
  const CLAIM = "urllib3 applies the Authorization header.";
  const REWRITTEN_NODE = {
    ...NODE,
    gaps: [{ id: "g1", kind: "wrong_model", claim: CLAIM, blocking: true, status: "open" }],
    attempts: [
      {
        answer: "urllib3 adds the header.",
        classification: "confused" as const,
        rationale: "Not what the code does.",
        at: RETAUGHT_AT,
        response: {
          action: "reteach", retaught: true, at: RETAUGHT_AT,
          gaps_addressed: ["g1"],
        },
      },
    ],
  };

  beforeEach(() => window.localStorage.clear());

  test("the notice says WHICH misconception the rewrite corrects", async () => {
    // A badge solves navigation and not comprehension: a learner returning to a
    // rewritten lesson still has to work out which part is new. A re-teach
    // regenerates every field, so there is no diff to highlight — what changed is
    // honestly answered by what it was written to correct, which the backend
    // already recorded (`gaps_addressed`) and nothing had joined up.
    render(<Harness Panel={await panel()} which={REWRITTEN_NODE} />);
    await screen.findByText(t.lesson.newMaterialLabel);

    expect(screen.getByText(t.lesson.rewriteAnswers)).toBeTruthy();
    expect(screen.getByText(CLAIM)).toBeTruthy();
  });

  test("reading it marks the material seen, so the notice can stop", async () => {
    // The old callout never cleared: it was derived from the last attempt's
    // `retaught` flag and sat there until the next answer, long after reading.
    render(<Harness Panel={await panel()} which={REWRITTEN_NODE} />);
    await screen.findByText(t.lesson.newMaterialLabel);

    await waitFor(() => {
      const seen = window.localStorage.getItem("codeonboard:lesson-seen:s1:n1");
      expect(seen && seen > RETAUGHT_AT).toBe(true);
    });
  });

  test("shows even when a LATER answer came after the rewrite", async () => {
    // Found by running the real UI. The notice used to key on `materialIsNew` —
    // "did the LAST answer rewrite this" — so a learner who was re-taught, never
    // looked, and then answered again from the other tab was never told at all.
    // That is exactly the miss this milestone exists to prevent.
    const answeredSince = {
      ...REWRITTEN_NODE,
      attempts: [
        ...REWRITTEN_NODE.attempts,
        {
          answer: "A later answer.",
          classification: "partial" as const,
          rationale: "Closer.",
          at: "2026-03-02T10:00:00.000Z",
          response: { action: "none", at: "2026-03-02T10:00:00.000Z" },
        },
      ],
    };
    render(<Harness Panel={await panel()} which={answeredSince} />);

    expect(await screen.findByText(t.lesson.newMaterialLabel)).toBeTruthy();
    expect(screen.getByText(CLAIM)).toBeTruthy();
  });

  test("does NOT show again once it has been read", async () => {
    // The other half, and the bug the old callout had: it never cleared, sitting
    // there until the next answer long after being read.
    window.localStorage.setItem(
      "codeonboard:lesson-seen:s1:n1",
      "2026-03-05T00:00:00.000Z"
    );
    render(<Harness Panel={await panel()} which={REWRITTEN_NODE} />);
    // `setup` is a section label and appears more than once; wait on the lesson
    // body itself, which is unique and only present once the panel has settled.
    await screen.findByText(LESSON.lesson.setup!);

    expect(screen.queryByText(t.lesson.newMaterialLabel)).toBeNull();
  });
});
