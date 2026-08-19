import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { Lesson, RespondResult, SessionGraph, VerificationPrompt } from "@/lib/api";
import { node } from "@/test/factories";

/**
 * The single-composer invariant.
 *
 * Requesting a verification clears `result` and sets `verification`, and both the
 * lesson's own question block and the verification block bind the SAME `answer`
 * state. Rendered together they put two textareas on screen that mirrored each
 * other's text, beneath two buttons both labelled "Submit" that did different
 * things. That is the defect this file exists to keep fixed — and the invariant
 * the phase model in L4 has to preserve.
 */

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const LESSON: Lesson = {
  node_id: "n1",
  lesson: {
    walkthrough: "The walkthrough body.",
    prompt: "What does sending through a Session change?",
    prompt_kind: "explain",
    setup: "The setup half, without the answer.",
    reveal: "The explanation, withheld until an answer exists.",
  },
};

const GAP = { id: "g1", kind: "wrong_model", claim: "A connected graph cannot return None.", blocking: true };

const CONFUSED: RespondResult = {
  classification: "confused",
  rationale: "That is not what the code does.",
  understanding_state: "failed",
  mutation: { kind: "none" },
  // hint makes `canAnswerAgain` true, which is what offers the verification CTA
  adaptation: { kind: "hint", text: "Look at what h() returns." },
  current_node_id: "n1",
  gaps: [GAP],
};

const PROMPT: VerificationPrompt = {
  node_id: "n1",
  question: "You set up a routing problem on a connected network. What can still fail?",
  targets: ["g1"],
  gaps: [GAP],
};

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

const graph = (): SessionGraph => ({
  session_id: "s1",
  repo_url: "https://github.com/psf/requests",
  goal: {},
  current_node_id: "n1",
  nodes: [node("n1", { gaps: [GAP] })],
  edges: [],
  readiness: 0,
  progress: {} as never,
  understanding: {} as never,
});

async function renderPanel() {
  const { default: LessonPanel } = await import("@/components/LessonPanel");
  const g = graph();
  render(
    <LessonPanel
      sessionId="s1"
      nodeId="n1"
      node={g.nodes[0]}
      position={1}
      total={1}
      isPrerequisite={false}
      graph={g}
      onFileClick={vi.fn()}
      onAdvance={vi.fn()}
      onRespond={vi.fn()}
      onFinish={vi.fn()}
    />
  );
  await screen.findByText(LESSON.lesson.prompt);
}

const textareas = () => screen.queryAllByPlaceholderText("Write your answer…");
const submits = () => screen.queryAllByRole("button", { name: "Submit" });

beforeEach(() => {
  vi.clearAllMocks();
  api.getLesson.mockResolvedValue(LESSON);
  api.respond.mockResolvedValue(CONFUSED);
  api.requestVerification.mockResolvedValue(PROMPT);
});

describe("the lesson's own question", () => {
  test("renders one composer and one Submit before an answer", async () => {
    await renderPanel();

    expect(textareas()).toHaveLength(1);
    expect(submits()).toHaveLength(1);
  });

  test("the reveal is withheld until an answer exists", async () => {
    await renderPanel();

    expect(screen.queryByText(LESSON.lesson.reveal!)).toBeNull();
  });
});

describe("requesting a verification", () => {
  async function reachVerification() {
    const user = userEvent.setup();
    await renderPanel();

    await user.type(textareas()[0], "A wrong answer.");
    await user.click(submits()[0]);
    await screen.findByRole("button", { name: "Check my understanding" });

    await user.click(screen.getByRole("button", { name: "Check my understanding" }));
    await screen.findByText(PROMPT.question);
    return user;
  }

  test("leaves exactly one composer and one Submit on screen", async () => {
    await reachVerification();

    // The regression: this was 2 and 2.
    expect(textareas()).toHaveLength(1);
    expect(submits()).toHaveLength(1);
  });

  test("replaces the lesson's own question rather than sitting beside it", async () => {
    await reachVerification();

    expect(screen.getByText(PROMPT.question)).toBeTruthy();
    expect(screen.queryByText(LESSON.lesson.prompt)).toBeNull();
  });

  test("'Not now' brings the lesson's own question back, still with one composer", async () => {
    const user = await reachVerification();

    await user.click(screen.getByRole("button", { name: "Not now" }));

    await waitFor(() => expect(screen.getByText(LESSON.lesson.prompt)).toBeTruthy());
    expect(screen.queryByText(PROMPT.question)).toBeNull();
    expect(textareas()).toHaveLength(1);
    expect(submits()).toHaveLength(1);
  });

  test("the verification answer submits to the verification endpoint, not the lesson's", async () => {
    const user = await reachVerification();
    api.respondToVerification.mockResolvedValue({ ...CONFUSED, kind: "verification" });

    await user.type(textareas()[0], "A better answer.");
    await user.click(submits()[0]);

    await waitFor(() => expect(api.respondToVerification).toHaveBeenCalledTimes(1));
    // One call only — from the first submit, before the verification existed.
    expect(api.respond).toHaveBeenCalledTimes(1);
  });
});
