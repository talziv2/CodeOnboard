import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { Lesson, RespondResult, SessionGraph } from "@/lib/api";
import { node } from "@/test/factories";
import { t } from "@/lib/strings";

/**
 * M2 — one retry, chosen by the server, and the unit's prompt spent exactly once.
 *
 * ── The rule ─────────────────────────────────────────────────────────────────
 *
 *   A retry question NEVER ships its own answer.
 *
 * `cached_lesson.prompt` always does. Teaching's contract for `reveal` is *"the
 * explanation — now you may answer it"*, and `lessonView` opens it after ANY
 * graded answer — `off-topic` included. A re-teach does not escape it: it
 * regenerates the whole lesson, so its new prompt arrives with a new `reveal`
 * that answers it.
 *
 * ── The back door this closes ────────────────────────────────────────────────
 *
 * `revealed` is `Boolean(result) || attempts.length > 0`, so leaving a graded
 * stop and returning used to hand back the composer with the explanation one tab
 * away. The design forbade the retry in the action row and the walk handed it
 * back to anyone who happened to navigate away and back — a rule that binds the
 * learner who reads the interface and not the one who wanders is not a rule.
 *
 * ── And what replaced four flags ─────────────────────────────────────────────
 *
 * The panel used to work out whether a retry was possible from `canAnswerAgain`,
 * `checkAvailable`, `canRequestWarmUp` and `warmUpDeclined`. It no longer works
 * anything out: `retry` arrives decided from `backend/learning/retry.py`, which
 * can see the budgets and the answered-question history this side cannot.
 */

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/flags", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/flags")>()),
  lessonUi: () => "next",
}));

const api = vi.hoisted(() => ({
  getLesson: vi.fn(),
  respond: vi.fn(),
  requestVerification: vi.fn(),
  requestReassessment: vi.fn(),
  respondToVerification: vi.fn(),
  respondToReassessment: vi.fn(),
  advance: vi.fn(),
  retry: vi.fn(),
  waive: vi.fn(),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  ...api,
}));

const LIVE_PROMPT = {
  available: true, mechanism: "answer" as const, reason: "",
  gap_id: null, reassessments_left: 2,
};
const CAN_REASSESS = {
  available: true, mechanism: "reassess" as const, reason: "",
  gap_id: null, reassessments_left: 2,
};
const CAN_VERIFY = {
  available: true, mechanism: "verify" as const, reason: "",
  gap_id: "g1", reassessments_left: 2,
};
const SPENT = {
  available: false, mechanism: null, reason: "budget_spent",
  gap_id: null, reassessments_left: 0,
};
const PENDING = { ...SPENT, reason: "already_asked", reassessments_left: 1 };

const PROMPT_TEXT = "What does sending through a Session change?";

const lesson = (over: Partial<Lesson> = {}): Lesson => ({
  node_id: "n1",
  lesson: {
    walkthrough: "The walkthrough body.",
    prompt: PROMPT_TEXT,
    prompt_kind: "explain",
    setup: "The setup half.",
    reveal: "The explanation, which answers the prompt above.",
  },
  retry: LIVE_PROMPT,
  ...over,
});

/** A node the learner has already answered once — the revisit shape. */
const ANSWERED = node("n1", {
  title: "Understand the Session",
  objective: "Explain what Session owns.",
  attempts: [
    {
      answer: "An earlier answer.",
      classification: "confused",
      rationale: "Not what the code does.",
      at: new Date().toISOString(),
    },
  ],
});
const FRESH = node("n1", { title: "Understand the Session", objective: "Explain what Session owns." });

const GRADED: RespondResult = {
  classification: "confused",
  rationale: "That is not what the code does.",
  understanding_state: "failed",
  mutation: { kind: "none" },
  adaptation: { kind: "hint", text: "Look at what the Session keeps." },
  current_node_id: "n1",
  gaps: [],
  retry: CAN_REASSESS,
};

const graph = (n = FRESH): SessionGraph => ({
  session_id: "s1",
  repo_url: "https://github.com/psf/requests",
  goal: {},
  current_node_id: "n1",
  nodes: [n],
  edges: [],
  readiness: 0,
  progress: {} as never,
  understanding: {} as never,
});

/**
 * `awaitText` is the thing that proves the panel has settled, and it is a
 * parameter because a restored question REPLACES the unit's prompt on screen —
 * `lessonPhase` reads it as VERIFY, so waiting for the prompt would wait forever
 * in exactly the case those tests are about.
 */
async function renderPanel(n = FRESH, awaitText: string = PROMPT_TEXT) {
  const { default: LessonPanel } = await import("@/components/LessonPanel");
  render(
    <LessonPanel
      sessionId="s1"
      nodeId="n1"
      node={n}
      position={2}
      total={16}
      isPrerequisite={false}
      graph={graph(n)}
      onFileClick={vi.fn()}
      onAdvance={vi.fn()}
      onRespond={vi.fn()}
      finished={false}
      onFinish={vi.fn()}
      onLeave={vi.fn()}
    />
  );
  await screen.findByText(awaitText);
}

const textareas = () => screen.queryAllByPlaceholderText("Write your answer…");

beforeEach(() => {
  vi.clearAllMocks();
  api.getLesson.mockResolvedValue(lesson());
  api.respond.mockResolvedValue(GRADED);
});

// ── the prompt is answerable exactly once ────────────────────────────────────

describe("the unit's own prompt", () => {
  test("is answerable while the server says it is live", async () => {
    await renderPanel();
    expect(textareas()).toHaveLength(1);
  });

  test("is NOT answerable on a revisit once something has been graded", async () => {
    // THE BACK DOOR. Same node, same lesson — the only difference is that the
    // server now reports the prompt spent.
    api.getLesson.mockResolvedValue(lesson({ retry: CAN_REASSESS }));
    await renderPanel(ANSWERED);

    expect(textareas()).toHaveLength(0);
    expect(screen.getByText(t.lesson.promptAnswered)).toBeTruthy();
  });

  test("stays on screen even when it cannot be answered", async () => {
    // Removing it was the other option and it is worse: the explanation above is
    // an explanation OF this question, and a page of answers to something
    // unstated is not an improvement.
    api.getLesson.mockResolvedValue(lesson({ retry: CAN_REASSESS }));
    await renderPanel(ANSWERED);

    expect(screen.getByText(PROMPT_TEXT)).toBeTruthy();
  });

  test("offers the one retry in the composer's place", async () => {
    api.getLesson.mockResolvedValue(lesson({ retry: CAN_REASSESS }));
    await renderPanel(ANSWERED);

    expect(screen.getByRole("button", { name: t.lesson.askAgain })).toBeTruthy();
  });

  test("says why there is no way on when there is none", async () => {
    // A control that is simply absent leaves the learner unable to tell "nothing
    // left to do" from "something is broken".
    api.getLesson.mockResolvedValue(lesson({ retry: SPENT }));
    await renderPanel(ANSWERED);

    expect(screen.queryByRole("button", { name: t.lesson.askAgain })).toBeNull();
    expect(screen.getByText(t.lesson.retryReason.budget_spent)).toBeTruthy();
  });
});

// ── one action, server-chosen mechanism ──────────────────────────────────────

describe("Ask me again", () => {
  async function grade() {
    const user = userEvent.setup();
    await renderPanel();
    await user.type(textareas()[0], "A wrong answer.");
    await user.click(screen.getAllByRole("button", { name: t.lesson.submit })[0]);
    await screen.findByText(GRADED.rationale);
    return user;
  }

  test("runs a re-assessment when the server says reassess", async () => {
    api.requestReassessment.mockResolvedValue({
      node_id: "n1", question: "A FRESH OBJECTIVE QUESTION", retry: PENDING,
    });
    const user = await grade();

    await user.click(screen.getByRole("button", { name: t.lesson.askAgain }));

    await screen.findByText("A FRESH OBJECTIVE QUESTION");
    expect(api.requestReassessment).toHaveBeenCalledWith("s1", "n1");
    expect(api.requestVerification).not.toHaveBeenCalled();
  });

  test("a re-assessment that ships four options renders them, with a way to type instead", async () => {
    // D10 (revised): a retry MAY be a multiple choice. The learner still chooses
    // the input — picking an option and typing both post as a re-assessment.
    const OPTS = ["the full claim", "half of it", "a wrong claim", "another wrong one"];
    api.requestReassessment.mockResolvedValue({
      node_id: "n1", question: "A FRESH OBJECTIVE QUESTION", choices: OPTS, retry: PENDING,
    });
    api.respondToReassessment.mockResolvedValue({ ...GRADED, retry: PENDING });
    const user = await grade();

    await user.click(screen.getByRole("button", { name: t.lesson.askAgain }));
    await screen.findByText("A FRESH OBJECTIVE QUESTION");

    // Four options, plus a toggle down to a textarea.
    expect(screen.getAllByRole("radio")).toHaveLength(4);
    await user.click(screen.getByText(t.lesson.writeOwnAnswer));
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.getByPlaceholderText(t.lesson.answerPlaceholder)).toBeTruthy();

    // Back to options, pick one, and it posts as a re-assessment.
    await user.click(screen.getByText(t.lesson.chooseFromOptions));
    await user.click(screen.getByText(OPTS[0]));
    await user.click(screen.getByRole("button", { name: t.lesson.submit }));
    expect(api.respondToReassessment).toHaveBeenCalledWith("s1", OPTS[0], "n1");
  });

  test("runs a verification when the server says verify, aimed at its gap", async () => {
    api.respond.mockResolvedValue({ ...GRADED, retry: CAN_VERIFY });
    api.requestVerification.mockResolvedValue({
      node_id: "n1", question: "A FRESH GAP QUESTION", targets: ["g1"], gaps: [],
    });
    const user = await grade();

    await user.click(screen.getByRole("button", { name: t.lesson.askAgain }));

    await screen.findByText("A FRESH GAP QUESTION");
    // The gap the SERVER picked, not one the panel chose.
    expect(api.requestVerification).toHaveBeenCalledWith("s1", "n1", "g1");
    expect(api.requestReassessment).not.toHaveBeenCalled();
  });

  test("the learner is never shown which mechanism it was", async () => {
    // One act, one name. Which machinery served it is our bookkeeping.
    api.respond.mockResolvedValue({ ...GRADED, retry: CAN_VERIFY });
    await grade();
    expect(screen.queryByText(/verif/i)).toBeNull();
    expect(screen.queryByText(/re-?assess/i)).toBeNull();
  });

  test("a re-assessment answer posts as a re-assessment, not as the lesson's own", async () => {
    api.requestReassessment.mockResolvedValue({
      node_id: "n1", question: "A FRESH OBJECTIVE QUESTION", retry: PENDING,
    });
    api.respondToReassessment.mockResolvedValue({
      ...GRADED, classification: "understood", rationale: "Yes — that is it.",
      understanding_state: "understood", gaps: [],
      retry: { ...SPENT, reason: "objective_met" },
    });
    const user = await grade();
    await user.click(screen.getByRole("button", { name: t.lesson.askAgain }));
    await screen.findByText("A FRESH OBJECTIVE QUESTION");

    await user.type(textareas()[0], "A better answer.");
    await user.click(screen.getAllByRole("button", { name: t.lesson.submit })[0]);

    await screen.findByText("Yes — that is it.");
    expect(api.respondToReassessment).toHaveBeenCalledWith("s1", "A better answer.", "n1");
    expect(api.respondToVerification).not.toHaveBeenCalled();
  });

  test("is not offered at all when the server offers nothing", async () => {
    api.respond.mockResolvedValue({ ...GRADED, retry: SPENT });
    await grade();
    expect(screen.queryByRole("button", { name: t.lesson.askAgain })).toBeNull();
    expect(screen.getByText(t.lesson.retryReason.budget_spent)).toBeTruthy();
  });
});

// ── the question survives a reload ───────────────────────────────────────────

describe("an outstanding question", () => {
  test("comes back after a reload rather than costing the learner an attempt", async () => {
    // It is charged on ISSUE, so a refresh that dropped it would spend a question
    // the learner never got to answer — and would put the composer back in front
    // of a prompt that is spent.
    api.getLesson.mockResolvedValue(
      lesson({
        retry: PENDING,
        pending: { kind: "reassessment", question: "A FRESH OBJECTIVE QUESTION" },
      })
    );
    await renderPanel(ANSWERED, "A FRESH OBJECTIVE QUESTION");

    expect(textareas()).toHaveLength(1);
  });

  test("a restored check answers to the verification endpoint", async () => {
    api.getLesson.mockResolvedValue(
      lesson({
        retry: PENDING,
        pending: { kind: "verification", question: "A RESTORED CHECK" },
      })
    );
    api.respondToVerification.mockResolvedValue({
      ...GRADED, kind: "verification", classification: null as never,
      resolved: [], unresolved: ["g1"], rationale: "Not yet.",
    });
    const user = userEvent.setup();
    await renderPanel(ANSWERED, "A RESTORED CHECK");

    await user.type(textareas()[0], "My answer.");
    await user.click(screen.getAllByRole("button", { name: t.lesson.submit })[0]);

    await waitFor(() => expect(api.respondToVerification).toHaveBeenCalled());
    expect(api.respondToReassessment).not.toHaveBeenCalled();
  });
});

// ── M3: rewritten material, and finding it ───────────────────────────────────

describe("material a re-teach rewrote", () => {
  const RETAUGHT_AT = "2026-03-01T10:00:00.000Z";
  const GAP = {
    id: "g1", kind: "wrong_model", blocking: true, status: "open",
    claim: "urllib3 applies the Authorization header.",
  };
  /** A node whose answer caused a re-teach, with the gap it was told to correct. */
  const REWRITTEN = node("n1", {
    title: "Understand the Session",
    objective: "Explain what Session owns.",
    gaps: [GAP],
    attempts: [
      {
        answer: "urllib3 adds the header.",
        classification: "confused",
        rationale: "Not what the code does.",
        at: RETAUGHT_AT,
        response: {
          action: "reteach", retaught: true, at: RETAUGHT_AT,
          gaps_addressed: ["g1"],
        },
      },
    ],
  });

  beforeEach(() => window.localStorage.clear());

  // The `Rewritten` notice itself is a SURFACES feature — under one column the
  // consequence line already says it and the material is right there — so what it
  // names is asserted in `surfacesAwareness.test.tsx`.

  test("the notice clears once the material has been looked at", async () => {
    // The old callout was derived from the last attempt's `retaught` flag, so it
    // never cleared — it sat there until the next answer, long after reading.
    api.getLesson.mockResolvedValue(lesson({ retry: CAN_VERIFY }));
    await renderPanel(REWRITTEN);
    await waitFor(() =>
      expect(window.localStorage.getItem("codeonboard:lesson-seen:s1:n1")).toBeTruthy()
    );

    // A later visit, with the mark already in place, is no longer news.
    const seen = window.localStorage.getItem("codeonboard:lesson-seen:s1:n1")!;
    expect(seen > RETAUGHT_AT).toBe(true);
  });

  test("a stop nobody rewrote is never marked as read", async () => {
    // The mark exists to answer "since the rewrite"; writing it where there was
    // no rewrite would be storing an answer to a question nobody asked.
    await renderPanel(FRESH);
    expect(window.localStorage.getItem("codeonboard:lesson-seen:s1:n1")).toBeNull();
  });
});

// ── the learner's own words survive ──────────────────────────────────────────

describe("a check appears in Your answers", () => {
  /**
   * Reported from a real run: a learner cleared two gaps with a careful answer,
   * came back to the stop, and found the gaps marked "RESOLVED — you answered a
   * check on this correctly" with **no trace of what they wrote**. The system
   * kept the verdict and threw away the words that earned it.
   *
   * Checks were filtered out of the list on the mechanical grounds that they
   * carry no `classification` and rendered a blank row. That is a rendering
   * problem, not a reason to hide the one place a learner looks for their own
   * words.
   */
  const CHECKED = node("n1", {
    title: "Understand the Session",
    objective: "Explain what Session owns.",
    attempts: [
      {
        answer: "My first, wrong answer.",
        classification: "confused" as const,
        rationale: "Not what the code does.",
        at: "2026-03-01T10:00:00.000Z",
        question: PROMPT_TEXT,
        question_source: "lesson",
      },
      {
        answer: "My careful answer about connect().",
        classification: "" as never,
        rationale: "That settles it.",
        kind: "verification",
        at: "2026-03-01T10:05:00.000Z",
        question: "A FRESH CHECK QUESTION",
        question_source: "verification",
        response: { action: "none", gaps_resolved: ["g1", "g2"] },
      },
    ],
  });

  test("keeps the words that cleared the gaps", async () => {
    api.getLesson.mockResolvedValue(lesson({ retry: CAN_REASSESS }));
    await renderPanel(CHECKED, "A FRESH CHECK QUESTION");

    expect(screen.getByText("My careful answer about connect().")).toBeTruthy();
  });

  test("labels it a check rather than borrowing a verdict it never had", async () => {
    // A check is graded per gap; whether the stop is demonstrated is decided by
    // the latest ASSESSMENT plus the gap list, never by this answer.
    api.getLesson.mockResolvedValue(lesson({ retry: CAN_REASSESS }));
    await renderPanel(CHECKED, "A FRESH CHECK QUESTION");

    expect(screen.getByText(t.lesson.checkRow)).toBeTruthy();
    expect(screen.getByText(t.lesson.checkRowCleared(2))).toBeTruthy();
  });

  test("counts what it lists, so the row cannot disagree with its contents", async () => {
    api.getLesson.mockResolvedValue(lesson({ retry: CAN_REASSESS }));
    await renderPanel(CHECKED, "A FRESH CHECK QUESTION");

    /**
     * The defect: the block's summary count and the section heading inside it
     * were computed from DIFFERENT lists, so the row said "(1)" while listing
     * two answers. This asserted both labels read `(2)`.
     *
     * There is now only one label. A disclosure names its block, so the block's
     * own eyebrow is suppressed inside one — see `AlreadyNamed` in
     * `ui/SectionLabel.tsx`; two identical headings four pixels apart was its
     * own defect. That removes the way the two counts could disagree rather
     * than checking that they agree, so the gate moves to the thing still worth
     * gating: the count on the row against what the block actually contains.
     *
     * The wrong count is asserted absent as well. `getAllByText(…(2))` passing
     * would not by itself prove the row is not ALSO claiming something else.
     */
    expect(screen.getAllByText(t.lesson.yourAnswers(2))).toHaveLength(1);
    expect(screen.queryByText(t.lesson.yourAnswers(1))).toBeNull();

    // Both answers, which is what "(2)" is counting: the failed assessment and
    // the check that cleared the gaps.
    expect(screen.getByText("My first, wrong answer.")).toBeTruthy();
    expect(screen.getByText("My careful answer about connect().")).toBeTruthy();
  });

  test("and the check still never becomes evidence about the objective", async () => {
    // The whole reason checks were filtered in the first place. Everything that
    // REASONS about understanding still reads the assessments-only list — the
    // stop is not demonstrated, so the retry is still on offer.
    api.getLesson.mockResolvedValue(lesson({ retry: CAN_REASSESS }));
    await renderPanel(CHECKED, "A FRESH CHECK QUESTION");

    expect(screen.getByRole("button", { name: t.lesson.askAgain })).toBeTruthy();
  });
});
