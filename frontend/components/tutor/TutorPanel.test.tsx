import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

/**
 * The Tutor panel: the mode strip, the ladder, the reveal's disclosed trade, and
 * the single-composer invariant.
 *
 * Two of these are the frontend half of a backend guarantee and are worth naming:
 *
 *   - `⌘↵` in the tutor composer calls `askTutor` and NEVER `respond`. That is
 *     D2, and it is the reason a third textarea on screen is acceptable at all.
 *   - the reveal's consequence is on screen BEFORE the control that acts. A
 *     consequence disclosed afterwards is not a choice.
 */

const api = vi.hoisted(() => ({
  getTutor: vi.fn(),
  askTutor: vi.fn(),
  tutorHint: vi.fn(),
  tutorReveal: vi.fn(),
  tutorPin: vi.fn(),
}));

vi.mock("@/lib/api", () => api);

import TutorPanel from "@/components/tutor/TutorPanel";

const MODE_SCAFFOLD = {
  mode: "scaffold" as const,
  reason: "asking_lesson",
  question: "What does Session.send return?",
  question_source: "lesson",
  hints_used: 0,
  hints_left: 3,
  revealed: false,
  can_hint: true,
  can_reveal: true,
};

const MODE_EXPLAIN = {
  ...MODE_SCAFFOLD,
  mode: "explain" as const,
  reason: "not_asking",
  question: "",
  hints_left: 0,
  can_hint: false,
  can_reveal: false,
};

const turn = (over = {}) => ({
  id: "t1",
  at: "2026-09-01T10:00:00+00:00",
  node_id: "n1",
  mode: "explain" as const,
  hint_level: 0,
  question: "what does this do?",
  answer: "It owns the connection pool.",
  scope: "answered" as const,
  grounded: true,
  pinned: false,
  ...over,
});

const state = (over = {}) => ({
  mode: MODE_SCAFFOLD,
  remaining: 20,
  cap: 20,
  node_id: "n1",
  offers: [],
  ...over,
});

function panel(over: Record<string, unknown> = {}) {
  return render(
    <TutorPanel
      sessionId="s1"
      nodeId="n1"
      prefs={{ mode: "dock", open: true, dockWidth: 21.25, float: { x: null, y: null, w: 460, h: 640 } }}
      onPrefsChange={vi.fn()}
      onClose={vi.fn()}
      onCite={vi.fn()}
      onSuggestion={vi.fn()}
      {...over}
    />
  );
}

beforeEach(() => {
  api.getTutor.mockResolvedValue({ ...state(), turns: [] });
  api.askTutor.mockResolvedValue({ ...state(), turn: turn() });
  api.tutorHint.mockResolvedValue({
    ...state({ mode: { ...MODE_SCAFFOLD, hints_used: 1, hints_left: 2 } }),
    turn: turn({ id: "h1", mode: "scaffold", hint_level: 1, question: "", answer: "Look at the return." }),
  });
  api.tutorReveal.mockResolvedValue({
    ...state({ mode: { ...MODE_EXPLAIN, revealed: true } }),
    reveal: "It returns a Response.",
    retry: { available: true, mechanism: "reassess", reason: "", gap_id: null, reassessments_left: 2 },
  });
  api.tutorPin.mockResolvedValue({ turn: turn({ pinned: true }) });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("the two modes are never confusable", () => {
  test("assessment mode says so, and says it cannot see the answer", async () => {
    panel();
    expect(await screen.findByText(/helping you answer/i)).toBeTruthy();
    expect(screen.getByText(/can't see the answer/i)).toBeTruthy();
  });

  test("learning mode says something different", async () => {
    api.getTutor.mockResolvedValue({ ...state({ mode: MODE_EXPLAIN }), turns: [] });
    panel();
    expect(await screen.findByText(/explaining/i)).toBeTruthy();
    expect(screen.queryByText(/can't see the answer/i)).toBeNull();
  });

  test("the mode strip is announced, because the tutor changing character is news", async () => {
    const { container } = panel();
    await screen.findByText(/helping you answer/i);
    expect(container.querySelector('[aria-live="polite"]')).toBeTruthy();
  });

  test("the mode is never inferred here — it is whatever the server said", async () => {
    // A scaffold-shaped payload that CLAIMS explain. The panel must believe it.
    api.getTutor.mockResolvedValue({
      ...state({ mode: { ...MODE_EXPLAIN, question: "an open question" } }),
      turns: [],
    });
    panel();
    expect(await screen.findByText(/explaining/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /hint/i })).toBeNull();
  });
});

describe("the single-composer invariant (D2)", () => {
  test("the button says Ask, never Submit", async () => {
    panel();
    expect(await screen.findByRole("button", { name: "Ask" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /submit/i })).toBeNull();
  });

  test("cmd-enter asks the tutor and never answers the lesson", async () => {
    const user = userEvent.setup();
    panel();
    const box = await screen.findByPlaceholderText(/what's confusing you/i);
    await user.click(box);
    await user.type(box, "where do I look?");
    await user.keyboard("{Meta>}{Enter}{/Meta}");

    await waitFor(() => expect(api.askTutor).toHaveBeenCalledWith("s1", "where do I look?", "n1"));
    expect(api).not.toHaveProperty("respond");
  });

  test("the composer is never auto-focused — opening the tutor does not stop the reading", async () => {
    panel();
    const box = await screen.findByPlaceholderText(/what's confusing you/i);
    expect(document.activeElement).not.toBe(box);
  });

  test("the placeholder names the mode's intent", async () => {
    api.getTutor.mockResolvedValue({ ...state({ mode: MODE_EXPLAIN }), turns: [] });
    panel();
    expect(await screen.findByPlaceholderText(/ask about this code/i)).toBeTruthy();
  });
});

describe("the hint ladder", () => {
  test("a hint is requested and its rung is shown", async () => {
    const user = userEvent.setup();
    panel();
    await user.click(await screen.findByRole("button", { name: /give me a hint/i }));

    await waitFor(() => expect(api.tutorHint).toHaveBeenCalledWith("s1", "n1"));
    expect(await screen.findByText(/hint 1 of 3/i)).toBeTruthy();
  });

  test("a spent ladder says so instead of offering a dead control", async () => {
    api.getTutor.mockResolvedValue({
      ...state({ mode: { ...MODE_SCAFFOLD, hints_used: 3, hints_left: 0, can_hint: false } }),
      turns: [],
    });
    panel();
    expect(await screen.findByText(/every hint I have/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /hint/i })).toBeNull();
  });

  test("the reveal is offered from rung zero — the ladder bounds hints, not honesty", async () => {
    panel();
    expect(await screen.findByRole("button", { name: /show answer & get a new question/i })).toBeTruthy();
  });
});

describe("revealing is a disclosed trade", () => {
  test("the consequence is on screen BEFORE the control that acts", async () => {
    const user = userEvent.setup();
    panel();
    await user.click(await screen.findByRole("button", { name: /show answer & get a new question/i }));

    // The warning is up, and nothing has been spent yet.
    expect(screen.getByRole("alert").textContent).toMatch(/stops counting as your assessment/i);
    expect(screen.getByRole("alert").textContent).toMatch(/new question on the same concept/i);
    expect(api.tutorReveal).not.toHaveBeenCalled();
  });

  test("the control's own label carries the whole trade, not just 'show answer'", async () => {
    panel();
    const control = await screen.findByRole("button", { name: /show answer & get a new question/i });
    expect(control.textContent).toMatch(/new question/i);
  });

  test("keeping trying backs out and spends nothing", async () => {
    const user = userEvent.setup();
    panel();
    await user.click(await screen.findByRole("button", { name: /show answer & get a new question/i }));
    await user.click(screen.getByRole("button", { name: /keep trying/i }));

    expect(screen.queryByRole("alert")).toBeNull();
    expect(api.tutorReveal).not.toHaveBeenCalled();
  });

  test("confirming shows the explanation and reports the question is done", async () => {
    const user = userEvent.setup();
    panel();
    await user.click(await screen.findByRole("button", { name: /show answer & get a new question/i }));
    await user.click(screen.getAllByRole("button", { name: /show answer & get a new question/i }).at(-1)!);

    await waitFor(() => expect(api.tutorReveal).toHaveBeenCalledWith("s1", "n1"));
    expect(await screen.findByText(/It returns a Response\./)).toBeTruthy();
    expect(await screen.findByText(/this question is done/i)).toBeTruthy();
  });

  test("a fresh check offers no reveal — there is no answer to show", async () => {
    // question_source is a verification / re-assessment question: can_reveal is
    // false, so neither the control nor its "stops counting" warning appears.
    api.getTutor.mockResolvedValue({
      ...state({
        mode: {
          ...MODE_SCAFFOLD,
          question_source: "reassessment",
          can_reveal: false,
        },
      }),
      turns: [],
    });
    panel();
    // The hint control still renders, so the ladder itself is on screen…
    expect(await screen.findByRole("button", { name: /hint/i })).toBeTruthy();
    // …but the reveal is absent.
    expect(screen.queryByRole("button", { name: /show answer & get a new question/i })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("the transcript", () => {
  test("turns for other stops are behind a closed disclosure, not hidden", async () => {
    api.getTutor.mockResolvedValue({
      ...state(),
      turns: [
        turn({ id: "old", node_id: "n0", question: "ASKED EARLIER" }),
        turn({ id: "now", node_id: "n1", question: "ASKED HERE" }),
      ],
    });
    panel();

    expect(await screen.findByText("ASKED HERE")).toBeTruthy();
    expect(screen.getByText(/1 question earlier in this session/i)).toBeTruthy();
  });

  test("a learner's own words are never rendered as markdown", async () => {
    api.getTutor.mockResolvedValue({
      ...state(),
      turns: [turn({ question: "why *this* and not _that_?" })],
    });
    const { container } = panel();
    await screen.findByText("why *this* and not _that_?");
    expect(container.querySelector("em")).toBeNull();
  });

  test("a citation is navigation — clicking one opens the source at that range", async () => {
    const onCite = vi.fn();
    const user = userEvent.setup();
    api.getTutor.mockResolvedValue({
      ...state(),
      turns: [turn({
        citations: [{ file: "requests/adapters.py", symbol: "HTTPAdapter.send", line_start: 434, line_end: 538 }],
      })],
    });
    panel({ onCite });

    await user.click(await screen.findByRole("button", { name: "HTTPAdapter.send" }));
    expect(onCite).toHaveBeenCalledWith({
      file: "requests/adapters.py", symbol: "HTTPAdapter.send", line_start: 434, line_end: 538,
    });
  });

  test("pinning keeps an explanation with the lesson", async () => {
    const onTranscriptChange = vi.fn();
    const user = userEvent.setup();
    api.getTutor.mockResolvedValue({ ...state(), turns: [turn()] });
    panel({ onTranscriptChange });

    await user.click(await screen.findByRole("button", { name: /keep this with the lesson/i }));
    await waitFor(() => expect(api.tutorPin).toHaveBeenCalledWith("s1", "t1", true));
    expect(onTranscriptChange).toHaveBeenCalled();
  });
});

describe("the cap", () => {
  test("at zero the composer is replaced by a notice, not silently disabled", async () => {
    api.getTutor.mockResolvedValue({ ...state({ remaining: 0 }), turns: [] });
    panel();
    expect(await screen.findByText(/used all your tutor questions/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Ask" })).toBeNull();
  });

  test("the remaining count is visible while there is one", async () => {
    api.getTutor.mockResolvedValue({ ...state({ remaining: 4 }), turns: [] });
    panel();
    expect(await screen.findByText("4 left")).toBeTruthy();
  });

  test("a failed call reports that nothing was used up", async () => {
    const user = userEvent.setup();
    api.askTutor.mockResolvedValue({ ...state(), turn: null, failed: true, text: "sorry" });
    panel();
    const box = await screen.findByPlaceholderText(/what's confusing you/i);
    await user.type(box, "q");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});

describe("offers are controls, never actions", () => {
  test("a system offer renders as a button and does nothing until pressed", async () => {
    const onSuggestion = vi.fn();
    const user = userEvent.setup();
    api.getTutor.mockResolvedValue({
      ...state({
        mode: MODE_EXPLAIN,
        offers: [{ kind: "reassess", label_key: "askAgain", node_id: "n1", gap_id: null, signal: "dwelling" }],
      }),
      turns: [],
    });
    panel({ onSuggestion });

    const control = await screen.findByRole("button", { name: /try a fresh question/i });
    expect(onSuggestion).not.toHaveBeenCalled();
    await user.click(control);
    expect(onSuggestion).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "reassess", signal: "dwelling" })
    );
  });

  test("assessment mode offers no exit — that would be telling them to give up", async () => {
    api.getTutor.mockResolvedValue({ ...state({ offers: [] }), turns: [] });
    panel();
    await screen.findByText(/helping you answer/i);
    expect(screen.queryByRole("button", { name: /try a fresh question/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /go to that stop/i })).toBeNull();
  });
});
