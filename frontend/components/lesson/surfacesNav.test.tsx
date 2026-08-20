import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useCallback, useEffect, useState } from "react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { Lesson, RespondResult, SessionGraph, VerificationPrompt } from "@/lib/api";
import { node } from "@/test/factories";
import SurfaceTabs from "@/components/lesson/SurfaceTabs";
import { nextTab, tabsFor, type SessionTab, type TabEvent } from "@/lib/surfaceTabs";
import { t } from "@/lib/strings";

/**
 * R5, behaviourally: **no phase transition ever moves the tab.**
 *
 * The reducer tests prove a phase cannot reach the decision. This proves the
 * composition — the bar and the panel on screen together, driven through the real
 * transitions the design names: submitting an answer, receiving feedback, opening a
 * gap, generating a verification, and a re-teach. If a future edit gave the panel a
 * callback that selected a tab, or added an effect keyed on `result`, this is what
 * would fail.
 *
 * The harness holds tab state exactly as the session page does: one writer, and it
 * only accepts `TabEvent`. Reproducing that here rather than rendering the page is
 * deliberate — the page needs a router, params, a graph fetch and three responsive
 * hooks, none of which have anything to do with the claim.
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

const LESSON: Lesson = {
  node_id: "n1",
  lesson: {
    walkthrough: "The walkthrough body.",
    prompt: "What does sending through a Session change?",
    prompt_kind: "explain",
    setup: "The setup half.",
    reveal: "The explanation, withheld until an answer exists.",
    takeaway: "The takeaway.",
  },
};

const GAP = { id: "g1", kind: "wrong_model", claim: "A connected graph cannot fail.", blocking: true };

/** A wrong answer that opens a gap and earns a re-teach. */
const RETAUGHT: RespondResult = {
  classification: "confused",
  rationale: "That is not what the code does.",
  understanding_state: "failed",
  mutation: { kind: "none" },
  adaptation: { kind: "reteach", retaught: true },
  current_node_id: "n1",
  gaps: [GAP],
};

const PROMPT: VerificationPrompt = {
  node_id: "n1",
  question: "You set up a routing problem. What can still fail?",
  targets: ["g1"],
  gaps: [GAP],
};

const NODE = node("n1", {
  title: "Understand the Graph",
  objective: "Explain what Graph owns.",
  gaps: [GAP],
  anchors: [{ file: "search.py", symbol: "Graph", line_start: 1, line_end: 20 }],
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

// Hoisted, not built per render. `tabsFor` returns a fresh array each call, so an
// inline `tabs` would give `dispatchTab` a new identity every render, re-firing the
// arrival effect below and resetting the tab continuously — which is what this
// harness did on the first attempt, and is exactly the failure the page's `useMemo`
// exists to prevent.
const TABS = tabsFor("surfaces");

/** The session page's tab wiring, and nothing else from it. */
function Harness({
  Panel,
  nodeId = "n1",
}: {
  Panel: typeof import("@/components/LessonPanel").default;
  nodeId?: string;
}) {
  const [tab, setTab] = useState<SessionTab>("lesson");
  const dispatchTab = useCallback(
    (event: TabEvent) => setTab((c) => nextTab(c, event, TABS)),
    []
  );

  // The page keys arrival on the current node rather than dispatching from each
  // handler, so that no way of arriving can be forgotten. Mirrored here, because
  // that is the contract this test is about.
  useEffect(() => {
    dispatchTab({ kind: "arrivedAtStop" });
  }, [nodeId, dispatchTab]);

  return (
    <>
      <SurfaceTabs
        tabs={TABS}
        active={tab}
        onPick={(picked) => dispatchTab({ kind: "picked", tab: picked })}
      />
      <Panel
        sessionId="s1"
        nodeId={nodeId}
        node={NODE}
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

/** Imported after the flag mock is in place, matching the other suites. */
async function panel() {
  return (await import("@/components/LessonPanel")).default;
}

const activeTab = () =>
  screen.getAllByRole("button").find((b) => b.getAttribute("aria-current") === "page")
    ?.textContent;

const textareas = () => screen.queryAllByPlaceholderText("Write your answer…");
const submit = () => screen.getAllByRole("button", { name: t.lesson.submit })[0];

beforeEach(() => {
  vi.clearAllMocks();
  api.getLesson.mockResolvedValue(LESSON);
  api.respond.mockResolvedValue(RETAUGHT);
  api.requestVerification.mockResolvedValue(PROMPT);
});

describe("R5 · phase transitions never move the tab", () => {
  test("submitting an answer, and the verdict that follows, leave it alone", async () => {
    const user = userEvent.setup();
    render(<Harness Panel={await panel()} />);
    await screen.findByText(LESSON.lesson.prompt);
    expect(activeTab()).toBe("Lesson");

    await user.type(textareas()[0], "A wrong answer.");
    await user.click(submit());

    // STUDY → FEEDBACK. A gap opened and the stop was re-taught, which are two more
    // of the transitions the rule names.
    await screen.findByText(RETAUGHT.rationale!);
    expect(activeTab()).toBe("Lesson");
  });

  test("generating a verification leaves it alone", async () => {
    const user = userEvent.setup();
    render(<Harness Panel={await panel()} />);
    await screen.findByText(LESSON.lesson.prompt);
    await user.type(textareas()[0], "A wrong answer.");
    await user.click(submit());
    await screen.findByText(RETAUGHT.rationale!);

    await user.click(await screen.findByRole("button", { name: "Check my understanding" }));
    await screen.findByText(PROMPT.question);

    // FEEDBACK → VERIFY.
    expect(activeTab()).toBe("Lesson");
  });

  test("a verdict arriving while Understanding is attended leaves it there", async () => {
    // The other direction, which matters just as much: the learner deliberately
    // chose Understanding, and the phase must not send them back to Lesson.
    const user = userEvent.setup();
    render(<Harness Panel={await panel()} />);
    await screen.findByText(LESSON.lesson.prompt);
    await user.click(screen.getByRole("button", { name: "Understanding" }));
    expect(activeTab()).toBe("Understanding");

    await user.type(textareas()[0], "A wrong answer.");
    await user.click(submit());
    await screen.findByText(RETAUGHT.rationale!);

    expect(activeTab()).toBe("Understanding");
  });

  test("the whole sequence, from the Map tab, never moves it", async () => {
    // The strongest version: the learner is looking at the map while a full
    // study → feedback → verify sequence happens underneath.
    const user = userEvent.setup();
    render(<Harness Panel={await panel()} />);
    await screen.findByText(LESSON.lesson.prompt);
    await user.click(screen.getByRole("button", { name: "Map" }));
    expect(activeTab()).toBe("Map");

    await user.type(textareas()[0], "A wrong answer.");
    await user.click(submit());
    await screen.findByText(RETAUGHT.rationale!);
    await user.click(await screen.findByRole("button", { name: "Check my understanding" }));
    await screen.findByText(PROMPT.question);

    expect(activeTab()).toBe("Map");
  });
});

describe("the learner's own moves still work", () => {
  test("picking a tab selects it", async () => {
    const user = userEvent.setup();
    render(<Harness Panel={await panel()} />);
    await screen.findByText(LESSON.lesson.prompt);

    await user.click(screen.getByRole("button", { name: "Understanding" }));
    expect(activeTab()).toBe("Understanding");
    await user.click(screen.getByRole("button", { name: "Map" }));
    expect(activeTab()).toBe("Map");
    await user.click(screen.getByRole("button", { name: "Lesson" }));
    expect(activeTab()).toBe("Lesson");
  });

  test("arriving at a different stop returns to Lesson", async () => {
    const user = userEvent.setup();
    const Panel = await panel();
    const { rerender } = render(<Harness Panel={Panel} nodeId="n1" />);
    await screen.findByText(LESSON.lesson.prompt);
    await user.click(screen.getByRole("button", { name: "Understanding" }));
    expect(activeTab()).toBe("Understanding");

    // The page dispatches `arrivedAtStop` from its jump/advance handlers; here the
    // harness stands in for that by re-rendering with a new id and dispatching the
    // same event, which is the contract those handlers have to honour.
    rerender(<Harness Panel={Panel} nodeId="n2" />);
    await waitFor(() => expect(activeTab()).toBe("Lesson"));
  });
});
