import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { Lesson, RespondResult, SessionGraph, VerificationPrompt } from "@/lib/api";
import { node } from "@/test/factories";
import { t } from "@/lib/strings";

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
// PINNED TO `next`, the single-column arrangement.
//
// These are the D-track tests, written when `legacy` was the default and every
// block sat in one column. L5 deleted `legacy` and made `surfaces` the default, so
// unpinned they would render one surface at a time and half the assertions would be
// looking at the other tab. Pinning keeps them testing what they were written to
// test — the composer/Submit/reveal invariants within a single column — and the
// surface-split versions of the same claims live in `surfacesCanvas.test.tsx`,
// which asserts them per surface.
vi.mock("@/lib/flags", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/flags")>()),
  lessonUi: () => "next",
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
    setup: "The setup half, without the answer.",
    reveal: "The explanation, withheld until an answer exists.",
  },
  retry: LIVE_PROMPT,
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
  retry: CAN_VERIFY,
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
      finished={false}
      onFinish={vi.fn()}
      onLeave={vi.fn()}
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
    await screen.findByRole("button", { name: t.lesson.askAgain });

    await user.click(screen.getByRole("button", { name: t.lesson.askAgain }));
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

  /**
   * The reply to a check carries `classification: null` on purpose — it is
   * evidence about named beliefs, not a re-grade of the objective. Every action
   * and label in the panel keyed off `classification`, so a learner who answered
   * correctly got a card with an EMPTY headline, no statement that anything had
   * closed, their own answer gone, and "Build me a warm-up" as the only button —
   * offered because `null !== "understood"` happened to be true.
   */
  describe("after answering a check", () => {
    const checkReply = (over: Partial<RespondResult> = {}): RespondResult => ({
      kind: "verification",
      classification: null as never,
      rationale: "That settles the heuristic question.",
      understanding_state: "understood",
      mutation: { kind: "none" },
      adaptation: { kind: "none" },
      current_node_id: "n1",
      resolved: ["g1"],
      unresolved: [],
      gaps: [],
      // Cleared: the server reports nothing left to ask here.
      retry: NOTHING_LEFT,
      ...over,
    });

    async function answerCheck(reply: RespondResult) {
      const user = await reachVerification();
      api.respondToVerification.mockResolvedValue(reply);
      await user.type(textareas()[0], "My careful answer about np.inf.");
      await user.click(submits()[0]);
      await screen.findByText(reply.rationale);
      return user;
    }

    test("says it cleared, and names what closed", async () => {
      await answerCheck(checkReply());

      expect(screen.getByText("Cleared")).toBeTruthy();
      expect(screen.getByText(GAP.claim)).toBeTruthy();
    });

    test("keeps the learner's own answer on screen", async () => {
      await answerCheck(checkReply());

      // It is excluded from "Your answers" by design, so the card is the only
      // place it can survive.
      expect(screen.getByText("My careful answer about np.inf.")).toBeTruthy();
    });

    test("offers moving on — not a warm-up — when nothing is left open", async () => {
      await answerCheck(checkReply());

      expect(screen.getByRole("button", { name: /Next stop/ })).toBeTruthy();
      expect(screen.queryByRole("button", { name: "Build me a warm-up" })).toBeNull();
    });

    test("offers another go while a gap is still open", async () => {
      await answerCheck(
        checkReply({
          resolved: [], unresolved: ["g1"], gaps: [GAP],
          understanding_state: "failed", retry: CAN_VERIFY,
        })
      );

      expect(screen.getByText("Still open")).toBeTruthy();
      // ONE retry, whatever the mechanism. "Check another" was a second name for
      // the same act, and which act it is now belongs to the server.
      expect(screen.getByRole("button", { name: t.lesson.askAgain })).toBeTruthy();
    });

    test("distinguishes a partial close from a complete one", async () => {
      const second = { ...GAP, id: "g2", claim: "Another false belief." };
      api.requestVerification.mockResolvedValue({ ...PROMPT, targets: ["g1", "g2"], gaps: [GAP, second] });

      await answerCheck(checkReply({ resolved: ["g1"], unresolved: ["g2"], gaps: [second] }));

      const card = document.querySelector('div[tabindex="-1"]')!;
      expect(screen.getByText("Partly cleared")).toBeTruthy();
      // The card names only what CLOSED; what is still open stays in the gap
      // list above rather than being printed twice.
      expect(card.textContent).toContain(GAP.claim);
      expect(card.textContent).not.toContain(second.claim);
    });

    test("never shows an empty verdict headline", async () => {
      await answerCheck(checkReply());

      const card = document.querySelector('div[tabindex="-1"]')!;
      const headline = card.querySelector("p")!;
      // The regression: this was "".
      expect(headline.textContent?.trim()).not.toBe("");
    });
  });
});

describe("citations open the source at the right place", () => {
  /**
   * The anchor-precision guard. A unit whose flow crosses three files is anchored
   * on all three, and each `Step n of m` has to open ITS file at ITS lines. The
   * failure this pins is subtle and was real: opening the right file at the
   * node's own display range, so step 2 of a flow landed in the correct file at
   * the wrong lines. `viewingRange` exists for exactly this, and it is only ever
   * set from the range the citation carries.
   */
  const MULTI = node("n1", {
    file: "requests/sessions.py",
    line_start: 1,
    line_end: 20,
    anchors: [
      { file: "requests/api.py", symbol: "request", line_start: 14, line_end: 60 },
      { file: "requests/sessions.py", symbol: "Session.request", line_start: 502, line_end: 590 },
      { file: "requests/adapters.py", symbol: "HTTPAdapter.send", line_start: 434, line_end: 538 },
    ],
  });

  const renderMulti = async (onFileClick: ReturnType<typeof vi.fn>) => {
    const { default: LessonPanel } = await import("@/components/LessonPanel");
    const g = { ...graph(), nodes: [MULTI] };
    api.getLesson.mockResolvedValue(LESSON);
    render(
      <LessonPanel
        sessionId="s1"
        nodeId="n1"
        node={MULTI}
        position={1}
        total={1}
        isPrerequisite={false}
        graph={g}
        onFileClick={onFileClick}
        onAdvance={vi.fn()}
        onRespond={vi.fn()}
        finished={false}
        onFinish={vi.fn()}
        onLeave={vi.fn()}
      />
    );
    await screen.findByText(LESSON.lesson.prompt);
  };

  test("each step opens its own file at its own lines", async () => {
    const onFileClick = vi.fn();
    await renderMulti(onFileClick);

    const steps = screen.getAllByRole("button", { name: /Step \d of 3/ });
    expect(steps).toHaveLength(3);

    await userEvent.click(steps[1]);
    expect(onFileClick).toHaveBeenCalledWith("requests/sessions.py", 502, 590);

    await userEvent.click(steps[2]);
    expect(onFileClick).toHaveBeenCalledWith("requests/adapters.py", 434, 538);

    await userEvent.click(steps[0]);
    expect(onFileClick).toHaveBeenCalledWith("requests/api.py", 14, 60);
  });

  test("a step never falls back to the node's own display range", async () => {
    const onFileClick = vi.fn();
    await renderMulti(onFileClick);

    const steps = screen.getAllByRole("button", { name: /Step \d of 3/ });
    await userEvent.click(steps[1]);

    // The node's own range is 1–20; the anchor's is 502–590. Handing over the
    // node's range here is the exact bug `viewingRange` was added to prevent.
    const [, start, end] = onFileClick.mock.calls[0];
    expect([start, end]).not.toEqual([MULTI.line_start, MULTI.line_end]);
  });

  test("clicking the same step twice asks twice, so the pane can re-scroll", async () => {
    const onFileClick = vi.fn();
    await renderMulti(onFileClick);

    const steps = screen.getAllByRole("button", { name: /Step \d of 3/ });
    await userEvent.click(steps[0]);
    await userEvent.click(steps[0]);

    // Asking for a location the pane already shows still has to move it there —
    // which is what `focusKey` is counting on the page side.
    expect(onFileClick).toHaveBeenCalledTimes(2);
  });
});

describe("the derived phase agrees with what is on screen", () => {
  /**
   * The other half of L1's gate. `lib/lessonPhase.test.ts` checks the branch
   * table against the function; this checks the function against the UI that
   * already exists, which is the only way the claim "these thirteen situations
   * are four states" means anything. The phase is read off the invisible
   * `data-lesson-phase` attribute rather than recomputed, so a drift between the
   * derivation and the render fails here rather than passing twice.
   */
  const phaseOnScreen = () =>
    document.querySelector("[data-lesson-phase]")?.getAttribute("data-lesson-phase");

  test("STUDY: a fresh arrival is asking, with the reveal withheld", async () => {
    await renderPanel();

    expect(phaseOnScreen()).toBe("STUDY");
    // Asking: exactly one composer, and no verdict.
    expect(textareas()).toHaveLength(1);
    expect(screen.queryByText(CONFUSED.rationale!)).toBeNull();
    expect(screen.queryByText(LESSON.lesson.reveal!)).toBeNull();
  });

  test("FEEDBACK: a graded verdict is on screen and the reveal has opened", async () => {
    const user = userEvent.setup();
    await renderPanel();

    await user.type(textareas()[0], "A wrong answer.");
    await user.click(submits()[0]);
    await screen.findByText(CONFUSED.rationale!);

    expect(phaseOnScreen()).toBe("FEEDBACK");
    // Reporting, not asking: the verdict is present and the lesson's own
    // composer is gone.
    expect(textareas()).toHaveLength(0);
    expect(screen.getByText(LESSON.lesson.reveal!)).toBeTruthy();
  });

  test("VERIFY: an outstanding question replaces the verdict, not joins it", async () => {
    const user = userEvent.setup();
    await renderPanel();

    await user.type(textareas()[0], "A wrong answer.");
    await user.click(submits()[0]);
    await user.click(await screen.findByRole("button", { name: t.lesson.askAgain }));
    await screen.findByText(PROMPT.question);

    expect(phaseOnScreen()).toBe("VERIFY");
    // Asking again — and still exactly one composer, which is the invariant this
    // file exists to protect.
    expect(textareas()).toHaveLength(1);
    expect(submits()).toHaveLength(1);
    expect(screen.queryByText(CONFUSED.rationale!)).toBeNull();
  });

  test("RESOLVED: a check reports, and is not mistaken for a re-grade", async () => {
    const user = userEvent.setup();
    api.respondToVerification.mockResolvedValue({
      ...CONFUSED,
      kind: "verification",
      classification: null,
      resolved: ["g1"],
      unresolved: [],
    });
    await renderPanel();

    await user.type(textareas()[0], "A wrong answer.");
    await user.click(submits()[0]);
    await user.click(await screen.findByRole("button", { name: t.lesson.askAgain }));
    await screen.findByText(PROMPT.question);
    await user.type(textareas()[0], "The right answer.");
    await user.click(submits()[0]);
    await waitFor(() => expect(api.respondToVerification).toHaveBeenCalled());

    await waitFor(() => expect(phaseOnScreen()).toBe("RESOLVED"));
    // The distinction that matters: a check arrives as `result`, so a phase model
    // that only asked "is there a result" would call this FEEDBACK and render a
    // verdict branch that is silent because `classification` is null. That was
    // D2b.
    expect(phaseOnScreen()).not.toBe("FEEDBACK");
  });

  test("every phase the panel can reach is one of the four", async () => {
    await renderPanel();
    const seen = phaseOnScreen();
    expect(["STUDY", "FEEDBACK", "VERIFY", "RESOLVED"]).toContain(seen);
  });
});

describe("the brief survives every phase", () => {
  /**
   * L3's gate. The brief is pinned, so it is the one part of the lesson that must
   * be right in all four phases — its whole purpose is to still be there when the
   * canvas has scrolled past everything else. The objective matters most: it is the
   * standard the answer is marked against, and it used to scroll away first.
   */
  const RICH = node("n1", {
    title: "Understand the Graph",
    objective: "Explain what Graph owns and why a missing edge is silent.",
    file: "search.py",
    line_start: 1006,
    line_end: 1058,
    gaps: [GAP],
    anchors: [
      { file: "search.py", symbol: "Graph", line_start: 1006, line_end: 1058 },
      { file: "search.py", symbol: "Graph.get", line_start: 1100, line_end: 1110 },
    ],
  });

  const renderRich = async () => {
    const g = { ...graph(), nodes: [RICH] };
    api.getLesson.mockResolvedValue(LESSON);
    const { default: LessonPanel } = await import("@/components/LessonPanel");
    render(
      <LessonPanel
        sessionId="s1"
        nodeId="n1"
        node={RICH}
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
  };

  const briefHas = () => {
    const brief = document.querySelector("[data-lesson-brief]")!;
    return {
      position: brief.textContent!.includes(t.lesson.stopOf(2, 16)),
      title: brief.textContent!.includes("Understand the Graph"),
      objective: brief.textContent!.includes("Explain what Graph owns"),
      anchors: brief.textContent!.includes("search.py"),
      extraAnchor: brief.textContent!.includes("Graph.get"),
    };
  };

  test("STUDY: all five parts are in the brief", async () => {
    await renderRich();

    expect(document.querySelector("[data-lesson-brief]")).toBeTruthy();
    expect(briefHas()).toEqual({
      position: true,
      title: true,
      objective: true,
      anchors: true,
      extraAnchor: true,
    });
  });

  test("FEEDBACK: the brief is still there once a verdict lands", async () => {
    const user = userEvent.setup();
    await renderRich();

    await user.type(textareas()[0], "A wrong answer.");
    await user.click(submits()[0]);
    await screen.findByText(CONFUSED.rationale!);

    expect(briefHas()).toEqual({
      position: true,
      title: true,
      objective: true,
      anchors: true,
      extraAnchor: true,
    });
  });

  test("VERIFY: and while a check is outstanding", async () => {
    const user = userEvent.setup();
    await renderRich();

    await user.type(textareas()[0], "A wrong answer.");
    await user.click(submits()[0]);
    await user.click(await screen.findByRole("button", { name: t.lesson.askAgain }));
    await screen.findByText(PROMPT.question);

    expect(briefHas().objective).toBe(true);
    expect(briefHas().title).toBe(true);
  });

  test("the counters report what is open, and lead to the inline blocks", async () => {
    const user = userEvent.setup();
    await renderRich();

    await user.type(textareas()[0], "A wrong answer.");
    await user.click(submits()[0]);
    await screen.findByText(CONFUSED.rationale!);

    const brief = document.querySelector("[data-lesson-brief]")!;
    const counter = [...brief.querySelectorAll("button")].find((b) =>
      b.textContent!.includes("unresolved")
    );
    expect(counter).toBeTruthy();
    // The counter is a trigger, not a replacement: the block it points at is
    // still rendered inline, which is what makes L3 safe to be wrong about.
    expect(document.getElementById("lesson-gaps")).toBeTruthy();
    expect(screen.getByText(GAP.claim)).toBeTruthy();
  });

  test("nothing is counted when nothing is open", async () => {
    const clean = node("n1", { title: "Clean", objective: "Say the thing.", gaps: [] });
    const g = { ...graph(), nodes: [clean] };
    api.getLesson.mockResolvedValue(LESSON);
    const { default: LessonPanel } = await import("@/components/LessonPanel");
    render(
      <LessonPanel
        sessionId="s1"
        nodeId="n1"
        node={clean}
        position={1}
        total={1}
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

    const brief = document.querySelector("[data-lesson-brief]")!;
    expect(brief.textContent).not.toMatch(/unresolved/);
    expect(document.getElementById("lesson-gaps")).toBeNull();
  });
});
