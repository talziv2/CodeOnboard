import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { Lesson, RespondResult, SessionGraph, VerificationPrompt } from "@/lib/api";
import { node } from "@/test/factories";
import { t } from "@/lib/strings";

/**
 * The `next` canvas — §3a's answer, asserted through the render.
 *
 * `lessonView.test.ts` pins the decision; this pins that the decision reaches the
 * screen. The claims worth checking are all about WHAT IS OPEN AT ONCE: that the
 * blocks a phase has superseded really are disclosures, that they are closed when
 * they arrive, that exactly one composer exists, and that the verdict comes before
 * the explanation rather than after it — because a primary action below a long read
 * is the stranded-primary problem the whole inline-action model exists to avoid.
 */

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
// The flag is read at build time in production; mocked here so both paths are
// testable in one suite.
vi.mock("@/lib/flags", () => ({ lessonUi: () => "next" }));

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
    setup: "The setup half, which is the longest thing on the page.",
    reveal: "The explanation, withheld until an answer exists.",
    takeaway: "The takeaway.",
  },
};

const GAP = { id: "g1", kind: "wrong_model", claim: "A connected graph cannot fail.", blocking: true };

const CONFUSED: RespondResult = {
  classification: "confused",
  rationale: "That is not what the code does.",
  understanding_state: "failed",
  mutation: { kind: "none" },
  adaptation: { kind: "hint", text: "Look at what h() returns." },
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
  anchors: [
    { file: "search.py", symbol: "Graph", line_start: 1, line_end: 20 },
    { file: "search.py", symbol: "Graph.get", line_start: 30, line_end: 40 },
  ],
  attempts: [
    { answer: "An older answer.", classification: "partial", rationale: "Partly.", at: new Date().toISOString() },
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

async function renderNext() {
  const { default: LessonPanel } = await import("@/components/LessonPanel");
  const g = graph();
  render(
    <LessonPanel
      sessionId="s1"
      nodeId="n1"
      node={NODE}
      position={2}
      total={16}
      isPrerequisite={false}
      graph={g}
      onFileClick={vi.fn()}
      onAdvance={vi.fn()}
      onRespond={vi.fn()}
      finished={false}
      onFinish={vi.fn()}
      onLeave={vi.fn()}
    />
  );
  await screen.findByText(LESSON.lesson.prompt);
}

const textareas = () => screen.queryAllByPlaceholderText("Write your answer…");
const disclosures = () => [...document.querySelectorAll("details")];
const canvasText = () => document.querySelector("[data-lesson-phase]")!.textContent!;

beforeEach(() => {
  vi.clearAllMocks();
  api.getLesson.mockResolvedValue(LESSON);
  api.respond.mockResolvedValue(CONFUSED);
  api.requestVerification.mockResolvedValue(PROMPT);
});

describe("STUDY: reading and answering", () => {
  test("the setup is open, the trace path and history are disclosures", async () => {
    await renderNext();

    // Open: the prose is the thing being read.
    expect(screen.getByText(LESSON.lesson.setup!)).toBeTruthy();
    // The disclosures that exist here: trace path and history. Both closed.
    const labels = disclosures().map((d) => d.querySelector("summary")!.textContent);
    expect(labels.some((l) => l!.includes(t.lesson.tracePath))).toBe(true);
    expect(labels.some((l) => l!.includes("Your answers"))).toBe(true);
    expect(disclosures().every((d) => !d.open)).toBe(true);
  });

  test("the gaps are open here, because they are what is being answered about", async () => {
    await renderNext();
    expect(screen.getByText(GAP.claim)).toBeTruthy();
  });

  test("one composer", async () => {
    await renderNext();
    expect(textareas()).toHaveLength(1);
  });
});

describe("FEEDBACK: the verdict, and everything it superseded stepped back", () => {
  const answerOnce = async () => {
    const user = userEvent.setup();
    await renderNext();
    await user.type(textareas()[0], "A wrong answer.");
    await user.click(screen.getAllByRole("button", { name: t.lesson.submit })[0]);
    await screen.findByText(CONFUSED.rationale!);
  };

  test("the setup prose collapses into a disclosure", async () => {
    await answerOnce();

    const setupDisclosure = disclosures().find((d) =>
      d.querySelector("summary")!.textContent!.includes(t.lesson.setup)
    );
    expect(setupDisclosure).toBeTruthy();
    expect(setupDisclosure!.open).toBe(false);
    // Still reachable — superseded is not gone.
    expect(setupDisclosure!.textContent).toContain(LESSON.lesson.setup);
  });

  test("the gap list collapses too, because the key point already named it", async () => {
    await answerOnce();

    const gapDisclosure = disclosures().find((d) =>
      d.querySelector("summary")!.textContent!.includes(t.lesson.gapsHeading)
    );
    expect(gapDisclosure).toBeTruthy();
    expect(gapDisclosure!.open).toBe(false);
  });

  test("the composer is gone, and the verdict is the artifact", async () => {
    await answerOnce();

    expect(textareas()).toHaveLength(0);
    expect(screen.getByText(CONFUSED.rationale!)).toBeTruthy();
  });

  test("every disclosure arrives closed", async () => {
    await answerOnce();
    expect(disclosures().length).toBeGreaterThan(2);
    expect(disclosures().every((d) => !d.open)).toBe(true);
  });

  test("the verdict comes BEFORE the explanation, never after it", async () => {
    await answerOnce();

    const text = canvasText();
    const verdictAt = text.indexOf(CONFUSED.rationale!);
    const revealAt = text.indexOf(LESSON.lesson.reveal!);
    expect(verdictAt).toBeGreaterThan(-1);
    expect(revealAt).toBeGreaterThan(-1);
    // The stranded-primary rule: the actions live in the verdict card, so the
    // card must precede the long read rather than follow it.
    expect(verdictAt).toBeLessThan(revealAt);
  });
});

describe("VERIFY and RESOLVED", () => {
  test("VERIFY asks again with one composer and no verdict", async () => {
    const user = userEvent.setup();
    await renderNext();
    await user.type(textareas()[0], "A wrong answer.");
    await user.click(screen.getAllByRole("button", { name: t.lesson.submit })[0]);
    await user.click(await screen.findByRole("button", { name: "Check my understanding" }));
    await screen.findByText(PROMPT.question);

    expect(textareas()).toHaveLength(1);
    expect(screen.queryByText(CONFUSED.rationale!)).toBeNull();
    // The setup does not re-open: being re-asked is not being re-taught.
    const setupDisclosure = disclosures().find((d) =>
      d.querySelector("summary")!.textContent!.includes(t.lesson.setup)
    );
    expect(setupDisclosure?.open).toBe(false);
  });

  test("RESOLVED reports without a composer", async () => {
    const user = userEvent.setup();
    api.respondToVerification.mockResolvedValue({
      ...CONFUSED,
      kind: "verification",
      classification: null,
      resolved: ["g1"],
      unresolved: [],
    });
    await renderNext();
    await user.type(textareas()[0], "A wrong answer.");
    await user.click(screen.getAllByRole("button", { name: t.lesson.submit })[0]);
    await user.click(await screen.findByRole("button", { name: "Check my understanding" }));
    await screen.findByText(PROMPT.question);
    await user.type(textareas()[0], "The right answer.");
    await user.click(screen.getAllByRole("button", { name: t.lesson.submit })[0]);
    await waitFor(() => expect(api.respondToVerification).toHaveBeenCalled());

    await waitFor(() => expect(textareas()).toHaveLength(0));
    expect(
      document.querySelector("[data-lesson-phase]")!.getAttribute("data-lesson-phase")
    ).toBe("RESOLVED");
  });
});

describe("the reveal is still earned", () => {
  test("withheld before any answer", async () => {
    const fresh = node("n1", { title: "Fresh", attempts: [], gaps: [] });
    const { default: LessonPanel } = await import("@/components/LessonPanel");
    render(
      <LessonPanel
        sessionId="s1"
        nodeId="n1"
        node={fresh}
        position={1}
        total={1}
        isPrerequisite={false}
        graph={{ ...graph(), nodes: [fresh] }}
        onFileClick={vi.fn()}
        onAdvance={vi.fn()}
        onRespond={vi.fn()}
        finished={false}
        onFinish={vi.fn()}
        onLeave={vi.fn()}
      />
    );
    await screen.findByText(LESSON.lesson.prompt);

    expect(screen.queryByText(LESSON.lesson.reveal!)).toBeNull();
  });

  test("open on a revisit, where the learner is reading rather than being tested", async () => {
    await renderNext();
    // NODE has an attempt, so `revealed` is true with no result on screen.
    expect(screen.getByText(LESSON.lesson.reveal!)).toBeTruthy();
    expect(textareas()).toHaveLength(1);
  });
});
