import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { NodeGap } from "@/lib/api";
import Disclosure from "@/components/ui/Disclosure";
import SectionLabel from "@/components/ui/SectionLabel";
import AttemptHistory from "@/components/lesson/AttemptHistory";
import GapList from "@/components/lesson/GapList";
import SetupProse from "@/components/lesson/SetupProse";
import TracePath from "@/components/lesson/TracePath";
import { BLOCK_ICON } from "@/lib/lessonIcons";
import { t } from "@/lib/strings";

/**
 * A BLOCK IS NAMED ONCE.
 *
 * A disclosure's summary row exists to say what is inside it. Every block that
 * `LessonCanvas` collapses also carries its own eyebrow, so opening one showed the
 * name twice, four pixels apart — `THIS PATH CROSSES SEVERAL PLACES` above
 * `THIS PATH CROSSES SEVERAL PLACES`, `YOUR ANSWERS (1)` above `YOUR ANSWERS (1)`.
 *
 * The gate is `getAllByText(…).toHaveLength(1)` rather than `getByText`, because
 * `getByText` THROWS on a duplicate and so does catch this — but it reads as a
 * query that failed to find the element, which is how the defect survived a suite
 * that already queried these labels. The count says what is being asserted.
 *
 * The negative half matters as much: `GapList`'s `Settled` is a real sub-heading
 * that no summary row has named, and suppressing every label inside a disclosure
 * would silently merge the ledger's two halves.
 */

const anchors = [
  { file: "search.py", symbol: "breadth_first_tree_search", line_start: 178, line_end: 194 },
  { file: "search.py", symbol: "breadth_first_graph_search", line_start: 238, line_end: 257 },
];

const GAP: NodeGap = {
  id: "g1",
  kind: "wrong_model",
  claim: "Mounting an adapter does prefix matching.",
  blocking: true,
};

describe("a block rendered bare keeps its own title", () => {
  test("the code path", () => {
    render(<TracePath anchors={anchors} onFileClick={vi.fn()} />);
    expect(screen.getAllByText(t.lesson.tracePath)).toHaveLength(1);
  });

  test("the setup", () => {
    render(<SetupProse isSplit body="The setup half." />);
    expect(screen.getAllByText(t.lesson.setup)).toHaveLength(1);
  });
});

describe("a block inside a disclosure is named once, by the summary", () => {
  test("the code path", () => {
    render(
      <Disclosure label={t.lesson.tracePath} icon={BLOCK_ICON.tracePath} initiallyOpen>
        <TracePath anchors={anchors} onFileClick={vi.fn()} />
      </Disclosure>
    );
    expect(screen.getAllByText(t.lesson.tracePath)).toHaveLength(1);
    // The block itself still rendered — this is a suppressed heading, not a
    // suppressed block.
    expect(screen.getByText("breadth_first_tree_search")).toBeTruthy();
  });

  test("the setup", () => {
    render(
      <Disclosure label={t.lesson.setup} icon={BLOCK_ICON.setup} initiallyOpen>
        <SetupProse isSplit body="The setup half." />
      </Disclosure>
    );
    expect(screen.getAllByText(t.lesson.setup)).toHaveLength(1);
    expect(screen.getByText("The setup half.")).toBeTruthy();
  });

  test("the answer log", () => {
    const label = t.lesson.yourAnswers(1);
    render(
      <Disclosure label={label} icon={BLOCK_ICON.attempts} initiallyOpen>
        <AttemptHistory
          attempts={[
            {
              at: new Date().toISOString(),
              answer: "It owns the pool.",
              classification: "partial",
            },
          ]}
        />
      </Disclosure>
    );
    expect(screen.getAllByText(label)).toHaveLength(1);
    expect(screen.getByText(t.lesson.verdict.partial)).toBeTruthy();
  });

  test("the gap ledger — and its Settled sub-heading survives", () => {
    render(
      <Disclosure label={t.lesson.gapsHeading} icon={BLOCK_ICON.gaps} initiallyOpen>
        <GapList
          gaps={[GAP, { ...GAP, id: "g2", claim: "Adapters are per-request.", status: "waived" }]}
          onSolve={vi.fn()}
          onWaive={vi.fn()}
          disabled={false}
          solvingGapId={null}
          accent={null}
          note={null}
        />
      </Disclosure>
    );
    expect(screen.getAllByText(t.lesson.gapsHeading)).toHaveLength(1);
    // Nothing has named this one, so it must still be there.
    expect(screen.getAllByText(t.lesson.gapSettledHeading)).toHaveLength(1);
    expect(screen.getByText("Adapters are per-request.")).toBeTruthy();
  });
});

test("a section label outside a disclosure is untouched", () => {
  // Every use outside the lesson — the map, the rail, the welcome page — goes
  // through plain `SectionLabel` and must not be affected by any of this.
  render(<SectionLabel as="h3">{t.map.journeyTitle}</SectionLabel>);
  expect(screen.getAllByText(t.map.journeyTitle)).toHaveLength(1);
});
