import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";
import type { Attempt, NodeGap, RespondResult } from "@/lib/api";
import { node } from "@/test/factories";
import AnswerComposer from "@/components/lesson/AnswerComposer";
import AttemptHistory from "@/components/lesson/AttemptHistory";
import FeedbackCard from "@/components/lesson/FeedbackCard";
import GapList from "@/components/lesson/GapList";
import LessonBrief from "@/components/lesson/LessonBrief";
import RevealBlock from "@/components/lesson/RevealBlock";
import SetupProse from "@/components/lesson/SetupProse";
import TracePath from "@/components/lesson/TracePath";
import VerificationBlock from "@/components/lesson/VerificationBlock";
import { t } from "@/lib/strings";

/**
 * Smoke tests for the blocks L2 moved out of `LessonPanel`.
 *
 * Deliberately shallow. These components were moved, not written, and the
 * behaviour that matters about them is already covered where it belongs — the
 * single-composer invariant and the four phases in `LessonPanel.test.tsx`, anchor
 * precision there too. What these check is the thing extraction can break by
 * itself: a block that renders nothing because a prop was renamed on the way out,
 * or a control that lost its handler in the move.
 */

describe("the reading blocks", () => {
  test("the brief names the stop, its title and its location", async () => {
    const onFileClick = vi.fn();
    const n = node("n1", { title: "The Session object", file: "requests/sessions.py" });
    render(
      <LessonBrief node={n} position={3} total={12} isPrerequisite={false} onFileClick={onFileClick} />
    );

    expect(screen.getByText(t.lesson.stopOf(3, 12))).toBeTruthy();
    expect(screen.getByText("The Session object")).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: /requests\/sessions\.py/ }));
    expect(onFileClick).toHaveBeenCalledWith("requests/sessions.py");
  });

  test("a warm-up says so instead of claiming a position on the walk", () => {
    render(
      <LessonBrief
        node={node("n1")}
        position={3}
        total={12}
        isPrerequisite
        onFileClick={vi.fn()}
      />
    );
    expect(screen.getByText(t.lesson.warmUpHeading)).toBeTruthy();
    expect(screen.queryByText(t.lesson.stopOf(3, 12))).toBeNull();
  });

  test("the prose is labelled by whether the lesson withholds anything", () => {
    const { unmount } = render(<SetupProse isSplit body="The setup half." />);
    expect(screen.getByText(t.lesson.setup)).toBeTruthy();
    unmount();

    render(<SetupProse isSplit={false} body="One body, nothing withheld." />);
    expect(screen.getByText(t.lesson.walkthrough)).toBeTruthy();
  });

  test("each trace step carries its OWN file and range", async () => {
    const onFileClick = vi.fn();
    render(
      <TracePath
        onFileClick={onFileClick}
        anchors={[
          { file: "a.py", symbol: "one", line_start: 1, line_end: 9 },
          { file: "b.py", symbol: "two", line_start: 50, line_end: 88 },
        ]}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /Step 2 of 2/ }));
    expect(onFileClick).toHaveBeenCalledWith("b.py", 50, 88);
  });

  test("the reveal shows its two callouts only when they exist", () => {
    const { unmount } = render(<RevealBlock reveal="Because of the adapter." />);
    expect(screen.getByText("Because of the adapter.")).toBeTruthy();
    expect(screen.queryByText(t.lesson.takeaway)).toBeNull();
    unmount();

    render(<RevealBlock reveal="Because." takeaway="Take this." ownership="Own this." />);
    expect(screen.getByText("Take this.")).toBeTruthy();
    expect(screen.getByText("Own this.")).toBeTruthy();
  });
});

describe("the state blocks", () => {
  const GAP: NodeGap = { id: "g1", kind: "wrong_model", claim: "A connected graph cannot fail.", blocking: true };

  test("gaps are named, not counted, and each can be set aside", async () => {
    const onWaive = vi.fn();
    render(<GapList gaps={[GAP]} onWaive={onWaive} />);

    expect(screen.getByText("A connected graph cannot fail.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: t.lesson.waiveOne }));
    expect(onWaive).toHaveBeenCalledWith("g1");
  });

  test("the history counts what it was given and opens to the answer", async () => {
    const attempts: Attempt[] = [
      { answer: "First try.", classification: "confused", rationale: "Not that.", at: new Date().toISOString() },
      { answer: "Second try.", classification: "understood", rationale: "Yes.", at: new Date().toISOString() },
    ];
    render(<AttemptHistory attempts={attempts} />);

    expect(screen.getByText(t.lesson.yourAnswers(2))).toBeTruthy();
    // Collapsed to its verdict; the answer is inside the disclosure.
    expect(screen.getByText("First try.")).toBeTruthy();
    expect(screen.getByText("Second try.")).toBeTruthy();
  });
});

describe("the composers", () => {
  test("the lesson's composer offers exactly one input and one Submit", () => {
    render(
      <AnswerComposer
        prompt="What does Session own?"
        answer=""
        onAnswerChange={vi.fn()}
        onSubmit={vi.fn()}
        onSkip={vi.fn()}
        loading={false}
        error={null}
      />
    );

    // The single-input invariant, at the component level. The panel-level version
    // — that this and VerificationBlock never render together — is in
    // LessonPanel.test.tsx, because only the panel can break it.
    expect(screen.getAllByRole("textbox")).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: t.lesson.submit })).toHaveLength(1);
  });

  test("Submit is dead until something is written", () => {
    const onSubmit = vi.fn();
    render(
      <AnswerComposer
        prompt="?"
        answer="   "
        onAnswerChange={vi.fn()}
        onSubmit={onSubmit}
        onSkip={vi.fn()}
        loading={false}
        error={null}
      />
    );
    expect(screen.getByRole("button", { name: t.lesson.submit })).toHaveProperty("disabled", true);
  });

  test("the verification asks without revealing, and Not now backs out", async () => {
    const onDismiss = vi.fn();
    render(
      <VerificationBlock
        question="What can still fail?"
        answer="something"
        onAnswerChange={vi.fn()}
        onSubmit={vi.fn()}
        onDismiss={onDismiss}
        loading={false}
      />
    );

    expect(screen.getByText("What can still fail?")).toBeTruthy();
    expect(screen.getAllByRole("textbox")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: t.lesson.notNow }));
    expect(onDismiss).toHaveBeenCalled();
  });
});

describe("the feedback card", () => {
  const base = {
    isCheck: false,
    checkOutcome: { label: "", color: "" },
    closed: [],
    checkedAnswer: undefined,
    adaptation: undefined,
    openGaps: [],
    warmUpInserted: false,
    canRequestWarmUp: false,
    canAnswerAgain: false,
    loading: false,
    verifying: false,
    error: null,
    verdictRef: { current: null },
    onAdvanceStop: vi.fn(),
    onCheckUnderstanding: vi.fn(),
    onBuildWarmUp: vi.fn(),
    onAnswerAgain: vi.fn(),
    onStartWarmUp: vi.fn(),
  };

  test("a correct answer offers moving on", () => {
    const result = { classification: "understood", rationale: "That's it." } as RespondResult;
    render(<FeedbackCard {...base} result={result} />);

    expect(screen.getByText(t.lesson.verdict.understood)).toBeTruthy();
    expect(screen.getByText("That's it.")).toBeTruthy();
    expect(screen.getByRole("button", { name: t.lesson.nextStop })).toBeTruthy();
  });

  test("a check reports what closed, and never as a re-grade", () => {
    const result = { classification: null, rationale: "Cleared." } as unknown as RespondResult;
    render(
      <FeedbackCard
        {...base}
        result={result}
        isCheck
        checkOutcome={{ label: t.lesson.checkCleared, color: "var(--color-jade)" }}
        closed={[{ id: "g1", kind: "wrong_model", claim: "The closed one.", blocking: true }]}
        checkedAnswer="What the learner wrote."
      />
    );

    expect(screen.getByText(t.lesson.checkCleared)).toBeTruthy();
    expect(screen.getByText("The closed one.")).toBeTruthy();
    // The learner's own words survive, because a verification answer is kept out
    // of "Your answers" and would otherwise be nowhere.
    expect(screen.getByText("What the learner wrote.")).toBeTruthy();
    // With nothing left open, the primary is moving on — not a warm-up, which is
    // what a null classification used to fall through to.
    expect(screen.getByRole("button", { name: t.lesson.nextStop })).toBeTruthy();
    expect(screen.queryByRole("button", { name: t.lesson.buildWarmUp })).toBeNull();
  });

  test("with a gap open, the second chance is a new question and not Try again", () => {
    const result = { classification: "partial", rationale: "Partly." } as RespondResult;
    render(
      <FeedbackCard
        {...base}
        result={result}
        canAnswerAgain
        openGaps={[{ id: "g1", kind: "wrong_model", claim: "Still open.", blocking: true }]}
      />
    );

    expect(screen.getByRole("button", { name: t.lesson.verifyCta })).toBeTruthy();
    // §18.7: re-asking the question whose answer the reveal just gave away proves
    // only that the page was read.
    expect(screen.queryByRole("button", { name: t.lesson.tryAgain })).toBeNull();
  });

  test("with nothing open, Try again is the second chance", () => {
    const result = { classification: "partial", rationale: "Partly." } as RespondResult;
    render(<FeedbackCard {...base} result={result} canAnswerAgain openGaps={[]} />);

    expect(screen.getByRole("button", { name: t.lesson.tryAgain })).toBeTruthy();
    expect(screen.queryByRole("button", { name: t.lesson.verifyCta })).toBeNull();
  });
});
