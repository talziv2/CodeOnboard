import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";
import type { Attempt, NodeGap, RespondResult } from "@/lib/api";
import { node } from "@/test/factories";
import AnswerComposer from "@/components/lesson/AnswerComposer";
import AttemptHistory from "@/components/lesson/AttemptHistory";
import GapList from "@/components/lesson/GapList";
import LessonBrief from "@/components/lesson/LessonBrief";
import RevealBlock from "@/components/lesson/RevealBlock";
import SetupProse from "@/components/lesson/SetupProse";
import TracePath from "@/components/lesson/TracePath";
import VerificationBlock from "@/components/lesson/VerificationBlock";
import { LESSON_ICON } from "@/lib/lessonIcons";
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

  test("one place is not a path: no step prefix, and a label that fits", async () => {
    // This block used to be `absent` for anything but a multi-anchor unit, so on
    // the units most graphs are — one anchor, or none and only the display
    // projection — "where does this live in the code" never rendered at all. It
    // renders now, which means the multi-place wording has to stop being assumed.
    const onFileClick = vi.fn();
    render(
      <TracePath
        onFileClick={onFileClick}
        anchors={[{ file: "adapters.py", symbol: "BaseAdapter", line_start: 128, line_end: 151 }]}
      />
    );

    expect(screen.getByText(t.lesson.codeLocation)).toBeTruthy();
    expect(screen.queryByText(t.lesson.tracePath)).toBeNull();
    expect(screen.queryByText(/Step 1 of 1/)).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: /BaseAdapter/ }));
    expect(onFileClick).toHaveBeenCalledWith("adapters.py", 128, 151);
  });

  test("several places keep the path wording", () => {
    render(
      <TracePath
        onFileClick={vi.fn()}
        anchors={[
          { file: "a.py", symbol: "one", line_start: 1, line_end: 9 },
          { file: "b.py", symbol: "two", line_start: 50, line_end: 88 },
        ]}
      />
    );
    expect(screen.getByText(t.lesson.tracePath)).toBeTruthy();
    expect(screen.queryByText(t.lesson.codeLocation)).toBeNull();
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

  test("gaps are named, not counted, and each can be cleared or set aside", async () => {
    const onWaive = vi.fn();
    const onSolve = vi.fn();
    render(<GapList gaps={[GAP]} onSolve={onSolve} onWaive={onWaive} />);

    expect(screen.getByText("A connected graph cannot fail.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: t.lesson.gapSolve }));
    expect(onSolve).toHaveBeenCalledWith("g1");
    await userEvent.click(screen.getByRole("button", { name: t.lesson.waiveOne }));
    expect(onWaive).toHaveBeenCalledWith("g1");
  });

  // The defect the ledger exists to fix: a resolved gap used to leave the wire,
  // so the one act the learner can perform on a gap made its row disappear.
  test("a resolved gap keeps its row, marked, and loses the give-up verb", () => {
    const resolved: NodeGap = { ...GAP, id: "g2", claim: "Retries are free.", status: "verified" };
    render(<GapList gaps={[GAP, resolved]} onSolve={vi.fn()} onWaive={vi.fn()} />);

    expect(screen.getByText("Retries are free.")).toBeTruthy();
    expect(screen.getByText(t.lesson.gapStatusVerified)).toBeTruthy();
    expect(screen.getByText(t.lesson.gapsTally(1, 2))).toBeTruthy();
    // One open gap, so exactly one of each verb — the resolved row offers neither.
    expect(screen.getAllByRole("button", { name: t.lesson.waiveOne })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: t.lesson.gapSolve })).toHaveLength(1);
  });

  // Waiving is a choice, never evidence, so it must stay reversible.
  test("a waived gap can still be cleared", () => {
    const waived: NodeGap = { ...GAP, status: "waived" };
    render(<GapList gaps={[waived]} onSolve={vi.fn()} onWaive={vi.fn()} />);

    expect(screen.getByText(t.lesson.gapStatusWaived)).toBeTruthy();
    expect(screen.getByText(t.lesson.gapsTally(0, 1))).toBeTruthy();
    expect(screen.getByRole("button", { name: t.lesson.gapSolve })).toBeTruthy();
    expect(screen.queryByRole("button", { name: t.lesson.waiveOne })).toBeNull();
  });

  /**
   * The glyph channel must not contradict the other three.
   *
   * `Settled` covers `verified` AND `waived`, so it carried a ✅ over a section
   * that can hold nothing but ignored gaps: `✅ Settled` above a tally reading
   * "0 of 1 resolved" and a row reading "Still unresolved — you chose not to work
   * on it now". The tick is the fastest-read thing in that stack and it said the
   * opposite of the two channels under it — and it made a learner DECISION look
   * like a change in status, which waiving must never do.
   *
   * So the section heading carries no marker and the ROWS carry theirs, which is
   * the level at which the distinction is actually true. Asserted by the absence
   * of the resolved glyph anywhere in a ledger that has resolved nothing.
   */
  test("an ignored-only ledger shows no resolved marker anywhere", () => {
    const waived: NodeGap = { ...GAP, status: "waived" };
    const { container } = render(
      <GapList gaps={[waived]} onSolve={vi.fn()} onWaive={vi.fn()} />
    );

    expect(screen.getByText(t.lesson.gapSettledHeading)).toBeTruthy();
    expect(screen.getByText(t.lesson.gapsTally(0, 1))).toBeTruthy();
    expect(container.textContent).not.toContain(LESSON_ICON.gapResolved);
    expect(container.textContent).toContain(LESSON_ICON.gapWaived);
  });

  test("a resolved gap does get the resolved marker, on its own row", () => {
    const resolved: NodeGap = { ...GAP, id: "g2", claim: "Retries are free.", status: "verified" };
    const { container } = render(
      <GapList gaps={[resolved]} onSolve={vi.fn()} onWaive={vi.fn()} />
    );

    expect(container.textContent).toContain(LESSON_ICON.gapResolved);
    expect(container.textContent).not.toContain(LESSON_ICON.gapWaived);
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

// The legacy `FeedbackCard` had a describe block here. The component is gone (L5)
// and so are its tests — every claim they made (the verdict word renders, the
// rationale renders, the actions offered per verdict) is asserted against
// `FeedbackCardNext` in `nextCanvas.test.tsx`, plus the 320-case sweep over the
// action table that the legacy card never had. Deleting them removes duplication,
// not coverage.

describe("the brief when it is pinned", () => {
  const RICH = node("n1", {
    title: "Understand the Graph",
    objective: "Explain what Graph owns and why a missing edge is silent.",
    concept_tags: ["graph", "adjacency-dict"],
    anchors: [
      { file: "search.py", symbol: "Graph", line_start: 1006, line_end: 1058 },
      { file: "search.py", symbol: "Graph.get", line_start: 1100, line_end: 1110 },
    ],
  });

  const renderBrief = (collapsed: boolean) =>
    render(
      <LessonBrief
        node={RICH}
        position={2}
        total={16}
        isPrerequisite={false}
        onFileClick={vi.fn()}
        openGapCount={1}
        attemptCount={2}
        onShowGaps={vi.fn()}
        onShowAttempts={vi.fn()}
        collapsed={collapsed}
      />
    );

  test("expanded, it carries everything", () => {
    renderBrief(false);

    expect(screen.getByText(t.lesson.stopOf(2, 16))).toBeTruthy();
    expect(screen.getByText("Understand the Graph")).toBeTruthy();
    expect(screen.getByText(/Explain what Graph owns/)).toBeTruthy();
    expect(screen.getByText("Graph.get")).toBeTruthy();
    expect(screen.getByText("graph")).toBeTruthy();
  });

  test("collapsed, position title and counters stay — the read-once rows go", () => {
    renderBrief(true);

    // Orientation and navigation survive.
    expect(screen.getByText(t.lesson.stopOf(2, 16))).toBeTruthy();
    expect(screen.getByText("Understand the Graph")).toBeTruthy();
    expect(screen.getByText(/unresolved/)).toBeTruthy();
    expect(screen.getByText(/answers/)).toBeTruthy();

    // The rest is collapsed away and hidden from assistive tech, not merely
    // clipped: a screen reader must not read a region the sighted user cannot
    // see. It stays in the DOM so the transition has something to animate.
    const region = document.querySelector('[aria-hidden="true"].grid');
    expect(region).toBeTruthy();
    expect(region!.textContent).toMatch(/Explain what Graph owns/);
  });

  test("the collapsing region is not hidden while expanded", () => {
    renderBrief(false);
    const region = document.querySelector(".grid");
    expect(region?.getAttribute("aria-hidden")).toBe("false");
  });

  test("the counters are controls, not text", async () => {
    renderBrief(false);

    // Both are real buttons with the chrome treatment, which is what makes the
    // affordance obvious — they read as bare text before.
    const gaps = screen.getByRole("button", { name: /unresolved/ });
    const answers = screen.getByRole("button", { name: /answers/ });
    expect(gaps.className).toMatch(/border/);
    expect(answers.className).toMatch(/border/);
    expect(gaps.tagName).toBe("BUTTON");
    expect(answers.tagName).toBe("BUTTON");
  });

  test("a counter with nothing to report is absent, not zero", () => {
    render(
      <LessonBrief
        node={RICH}
        position={1}
        total={1}
        isPrerequisite={false}
        onFileClick={vi.fn()}
        openGapCount={0}
        attemptCount={0}
        collapsed={false}
      />
    );
    expect(screen.queryByRole("button", { name: /unresolved/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /answer/ })).toBeNull();
  });
});
