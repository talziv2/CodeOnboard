import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useCallback, useEffect, useState } from "react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { Lesson, RespondResult, SessionGraph, VerificationPrompt } from "@/lib/api";
import { node } from "@/test/factories";
import SurfaceTabs from "@/components/lesson/SurfaceTabs";
import {
  nextTab, surfaceForTab, tabsFor, type SessionTab, type TabEvent,
} from "@/lib/surfaceTabs";
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
        surface={surfaceForTab(tab)}
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

/**
 * A note on what these can and cannot say, now that S3 has split the surfaces.
 *
 * The composer lives in Understanding. So "submit an answer from the Lesson tab" is
 * no longer a thing a learner can do, and a test that did it would be testing a
 * state the product does not have. What remains — and is the real risk — is the
 * other direction: a transition triggered in Understanding must not throw the
 * learner into Lesson when new material lands there.
 */

/** Go to a tab and answer, which is the only place an answer can be given. */
async function answerFrom(user: ReturnType<typeof userEvent.setup>, tab: string) {
  await user.click(screen.getByRole("button", { name: tab }));
  await user.type(textareas()[0], "A wrong answer.");
  await user.click(submit());
  await screen.findByText(RETAUGHT.rationale!);
}

describe("R5 · phase transitions never move the tab", () => {
  test("a verdict arriving where the learner is answering leaves them there", async () => {
    // STUDY → FEEDBACK, plus a gap opening and the stop being re-taught: three of
    // the transitions the rule names, in one submit. The re-teach is the tempting
    // one — new material just landed in Lesson, and nothing may go there for it.
    const user = userEvent.setup();
    render(<Harness Panel={await panel()} />);
    await screen.findByText(LESSON.lesson.setup!);

    await answerFrom(user, "Understanding");
    expect(activeTab()).toBe("Understanding");
  });

  test("generating a verification leaves it alone", async () => {
    const user = userEvent.setup();
    render(<Harness Panel={await panel()} />);
    await screen.findByText(LESSON.lesson.setup!);
    await answerFrom(user, "Understanding");

    await user.click(await screen.findByRole("button", { name: "Check my understanding" }));
    await screen.findByText(PROMPT.question);

    // FEEDBACK → VERIFY.
    expect(activeTab()).toBe("Understanding");
  });

  test("reading the explanation in Lesson does not get undone by the phase", async () => {
    // The learner answered, then deliberately went to read. FEEDBACK is still the
    // phase, and Lesson is where they chose to be; nothing may pull them back to
    // the verdict they have already seen.
    const user = userEvent.setup();
    render(<Harness Panel={await panel()} />);
    await screen.findByText(LESSON.lesson.setup!);
    await answerFrom(user, "Understanding");

    await user.click(screen.getByRole("button", { name: "Lesson" }));
    expect(activeTab()).toBe("Lesson");
    // The explanation is here, and it is what they came for.
    expect(await screen.findByText(LESSON.lesson.reveal!)).toBeTruthy();
    expect(activeTab()).toBe("Lesson");
  });

  test("going back and forth changes the tab only when clicked", async () => {
    const user = userEvent.setup();
    render(<Harness Panel={await panel()} />);
    await screen.findByText(LESSON.lesson.setup!);
    await answerFrom(user, "Understanding");

    await user.click(screen.getByRole("button", { name: "Lesson" }));
    expect(activeTab()).toBe("Lesson");
    await user.click(screen.getByRole("button", { name: "Map" }));
    expect(activeTab()).toBe("Map");
    await user.click(screen.getByRole("button", { name: "Understanding" }));
    expect(activeTab()).toBe("Understanding");
    // And the verdict survived the round trip, because the tab never owned it.
    expect(screen.getByText(RETAUGHT.rationale!)).toBeTruthy();
  });
});

describe("the learner's own moves still work", () => {
  test("picking a tab selects it", async () => {
    const user = userEvent.setup();
    render(<Harness Panel={await panel()} />);
    await screen.findByText(LESSON.lesson.setup!);

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
    await screen.findByText(LESSON.lesson.setup!);
    await user.click(screen.getByRole("button", { name: "Understanding" }));
    expect(activeTab()).toBe("Understanding");

    rerender(<Harness Panel={Panel} nodeId="n2" />);
    await waitFor(() => expect(activeTab()).toBe("Lesson"));
  });
});
