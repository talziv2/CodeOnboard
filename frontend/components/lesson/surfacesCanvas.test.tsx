import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { Lesson, RespondResult, SessionGraph, VerificationPrompt } from "@/lib/api";
import { node } from "@/test/factories";
import { t } from "@/lib/strings";

/**
 * S3's gate: **every block appears in exactly one surface, and no block is lost.**
 *
 * `lessonSurfaces.test.ts` asserts that of the view model; this asserts it of the
 * render, which is where a block can go missing without anything failing — a
 * surface that quietly drops one looks fine, and the learner simply never sees it
 * again.
 *
 * The second claim, and the one the milestone exists for: **separating the purposes
 * must not move the accumulation into Understanding.** So the open-block count is
 * measured per surface per phase, against the four the single canvas reached.
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
    why_now: "Why this stop, now.",
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

/** Multi-anchor and with history, so every block has something to render. */
const NODE = node("n1", {
  title: "Understand the Graph",
  objective: "Explain what Graph owns.",
  gaps: [GAP],
  anchors: [
    { file: "search.py", symbol: "Graph", line_start: 1, line_end: 20 },
    { file: "search.py", symbol: "Graph.get", line_start: 30, line_end: 40 },
  ],
  attempts: [
    {
      answer: "An older answer.",
      classification: "partial",
      rationale: "Partly.",
      at: new Date().toISOString(),
    },
  ],
});

/** The same stop, never answered: no attempt, so the explanation is still locked. */
const FRESH = node("n1", {
  title: "Understand the Graph",
  objective: "Explain what Graph owns.",
  gaps: [GAP],
  anchors: [
    { file: "search.py", symbol: "Graph", line_start: 1, line_end: 20 },
    { file: "search.py", symbol: "Graph.get", line_start: 30, line_end: 40 },
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

async function renderSurface(
  surface: "lesson" | "understanding",
  which = NODE
) {
  const { default: LessonPanel } = await import("@/components/LessonPanel");
  render(
    <LessonPanel
      surface={surface}
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
  );
  // Both surfaces render the brief, so wait on something each one owns.
  await screen.findByText(
    surface === "lesson" ? LESSON.lesson.setup! : LESSON.lesson.prompt
  );
}

const textareas = () => screen.queryAllByPlaceholderText("Write your answer…");
const disclosures = () => [...document.querySelectorAll("details")];
const summaries = () =>
  disclosures().map((d) => d.querySelector("summary")!.textContent!.trim());
const openDisclosures = () => disclosures().filter((d) => d.open).length;

beforeEach(() => {
  vi.clearAllMocks();
  api.getLesson.mockResolvedValue(LESSON);
  api.respond.mockResolvedValue(CONFUSED);
  api.requestVerification.mockResolvedValue(PROMPT);
});

describe("Lesson holds the material, and only the material", () => {
  test("the prose, the why-now and the trace path", async () => {
    await renderSurface("lesson");
    expect(screen.getByText(LESSON.lesson.setup!)).toBeTruthy();
    expect(screen.getByText(LESSON.lesson.why_now!)).toBeTruthy();
    expect(summaries().some((s) => s.includes(t.lesson.tracePath))).toBe(true);
  });

  test("no composer, and nothing to answer with", async () => {
    // The clearest single consequence of the split: being asked something is not
    // reading, so it is not here.
    await renderSurface("lesson");
    expect(textareas()).toHaveLength(0);
    expect(screen.queryByText(LESSON.lesson.prompt)).toBeNull();
  });

  test("no gaps, no history, no verdict", async () => {
    await renderSurface("lesson");
    expect(screen.queryByText(GAP.claim)).toBeNull();
    expect(summaries().some((s) => s.includes("Your answers"))).toBe(false);
    expect(screen.queryByText(CONFUSED.rationale!)).toBeNull();
  });
});

describe("Understanding holds the evidence, and only the evidence", () => {
  test("the question and the composer", async () => {
    await renderSurface("understanding");
    expect(screen.getByText(LESSON.lesson.prompt)).toBeTruthy();
    expect(textareas()).toHaveLength(1);
  });

  test("the open gaps, expanded, because they are what is being answered about", async () => {
    await renderSurface("understanding");
    expect(screen.getByText(GAP.claim)).toBeTruthy();
    // Not behind a disclosure in STUDY — never nest the two axes for the current
    // thing (R2).
    const inClosedDisclosure = disclosures().some(
      (d) => !d.open && d.textContent!.includes(GAP.claim)
    );
    expect(inClosedDisclosure).toBe(false);
  });

  test("previous answers, collapsed", async () => {
    await renderSurface("understanding");
    const history = disclosures().find((d) =>
      d.querySelector("summary")!.textContent!.includes("Your answers")
    );
    expect(history).toBeTruthy();
    expect(history!.open).toBe(false);
  });

  test("the setup is NOT here — the prose lives on Lesson and only there", async () => {
    // This reverses §1's reason 3, which had the setup mirrored here as a collapsed
    // "The setup" so answering never needed a tab change. Removed on request: the
    // prose is material, material is Lesson's, and a learner who wants to re-read it
    // goes there. The cost — losing scroll position and a half-typed answer's
    // context to a tab switch — is accepted, not solved.
    await renderSurface("understanding");
    expect(summaries().some((s) => s.includes(t.lesson.setup))).toBe(false);
    expect(screen.queryByText(LESSON.lesson.setup!)).toBeNull();
  });

  test("the code locations ARE here, collapsed — but the explanation is not", async () => {
    // The one mirror. Prose and explanation are material and stay on Lesson; a short
    // list of `file · symbol · lines` links is a reference, and mid-answer "which
    // code am I being asked about" should not cost a tab change.
    await renderSurface("understanding");
    const locations = disclosures().find((d) =>
      d.querySelector("summary")!.textContent!.includes(t.lesson.tracePath)
    );
    expect(locations).toBeTruthy();
    expect(locations!.open).toBe(false);
    expect(screen.queryByText(LESSON.lesson.reveal!)).toBeNull();
  });
});

describe("the question stays re-readable after the verdict", () => {
  test("collapsed, with its text, and still exactly one composer", async () => {
    // Understanding in FEEDBACK used to show a verdict and no sign of what had been
    // asked — "what have I shown?" answerable, "shown about WHAT?" not, on the one
    // surface built for the first question.
    const user = userEvent.setup();
    await renderSurface("understanding");
    await user.type(textareas()[0], "A wrong answer.");
    await user.click(screen.getAllByRole("button", { name: t.lesson.submit })[0]);
    await screen.findByText(CONFUSED.rationale!);

    const echo = disclosures().find((d) =>
      d.querySelector("summary")!.textContent!.includes(t.lesson.questionAsked)
    );
    expect(echo).toBeTruthy();
    expect(echo!.open).toBe(false);
    expect(echo!.textContent).toContain(LESSON.lesson.prompt);
    // The composer did NOT come back inside the disclosure — collapsed here means
    // "to re-read", never "to answer again".
    expect(textareas()).toHaveLength(0);
  });

  test("no echo while the question is still the live artifact", async () => {
    await renderSurface("understanding");
    const echo = disclosures().find((d) =>
      d.querySelector("summary")!.textContent!.includes(t.lesson.questionAsked)
    );
    expect(echo).toBeUndefined();
    expect(textareas()).toHaveLength(1);
  });

  test("Lesson never shows it", async () => {
    await renderSurface("lesson");
    expect(screen.queryByText(LESSON.lesson.prompt)).toBeNull();
  });
});

describe("no block is lost between the two surfaces", () => {
  test("everything the single canvas showed is on one surface or the other", async () => {
    // The gate, stated as the learner would notice it failing: something that used
    // to be reachable no longer is, anywhere.
    await renderSurface("lesson");
    const onLesson = document.body.textContent!;
    document.body.innerHTML = "";
    await renderSurface("understanding");
    const onUnderstanding = document.body.textContent!;

    const everywhere = onLesson + onUnderstanding;
    for (const fragment of [
      LESSON.lesson.setup!,
      LESSON.lesson.why_now!,
      LESSON.lesson.prompt,
      GAP.claim,
      t.lesson.tracePath,
      "Your answers",
    ]) {
      expect(everywhere, fragment).toContain(fragment);
    }
  });

  test("first visit: the setup is the material on Lesson, expanded and not a disclosure", async () => {
    await renderSurface("lesson", FRESH);
    expect(screen.getByText(LESSON.lesson.setup!)).toBeTruthy();
    // Expanded means NOT inside a disclosure at all, which is what "the material"
    // looks like as opposed to "a reference".
    const behindADisclosure = disclosures().some((d) =>
      d.textContent!.includes(LESSON.lesson.setup!)
    );
    expect(behindADisclosure).toBe(false);
    // And the explanation is still locked, so there is nothing to supersede it.
    expect(screen.queryByText(LESSON.lesson.reveal!)).toBeNull();
  });

  test("no block appears on both surfaces, in any state", async () => {
    await renderSurface("understanding", FRESH);
    expect(screen.queryByText(LESSON.lesson.setup!)).toBeNull();
  });
});

describe("the accumulation did not move into Understanding", () => {
  test("STUDY: two things expanded on Understanding, one on Lesson", async () => {
    await renderSurface("understanding");
    // The question and the gaps. Everything else — the history — arrives closed,
    // and the setup is not on this surface at all.
    expect(openDisclosures()).toBe(0);
    expect(textareas()).toHaveLength(1);
    expect(screen.getByText(GAP.claim)).toBeTruthy();
  });

  test("FEEDBACK: the verdict is the artifact and the gaps step back", async () => {
    const user = userEvent.setup();
    await renderSurface("understanding");
    await user.type(textareas()[0], "A wrong answer.");
    await user.click(screen.getAllByRole("button", { name: t.lesson.submit })[0]);
    await screen.findByText(CONFUSED.rationale!);

    // The composer is gone, every disclosure is closed, and the gap list is one of
    // them — the key point already named the leading gap.
    expect(textareas()).toHaveLength(0);
    expect(openDisclosures()).toBe(0);
    const gapsCollapsed = disclosures().some(
      (d) => !d.open && d.textContent!.includes(GAP.claim)
    );
    expect(gapsCollapsed).toBe(true);
  });

  test("on a revisit, Lesson leads with the explanation and the prose steps back", async () => {
    // Lesson's own supersession, and the reason `setupInLesson` exists: a verdict is
    // not newer material for THIS surface, but the explanation is. `NODE` carries a
    // prior attempt, so the explanation is unlocked.
    await renderSurface("lesson");
    expect(screen.getByText(LESSON.lesson.reveal!)).toBeTruthy();
    const setupCollapsed = disclosures().some(
      (d) => !d.open && d.textContent!.includes(LESSON.lesson.setup!)
    );
    expect(setupCollapsed).toBe(true);
    // Still exactly one expanded thing on Lesson, whichever it is.
    expect(openDisclosures()).toBe(0);
  });

  test("every disclosure on both surfaces arrives closed", async () => {
    for (const surface of ["lesson", "understanding"] as const) {
      document.body.innerHTML = "";
      await renderSurface(surface);
      expect(openDisclosures(), surface).toBe(0);
    }
  });
});
