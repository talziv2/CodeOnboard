import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import RouteRail from "@/components/RouteRail";
import { buildRoute } from "@/lib/graph-layout";
import { splitJourney } from "@/lib/route-sections";
import { node } from "@/test/factories";
import { t } from "@/lib/strings";
import type { Area, GraphEdge, GraphNode } from "@/lib/api";

/**
 * The rail, after the six notes that came out of walking a real session.
 *
 * Only the behavioural ones are asserted here. "Make it wider" and "increase the
 * gap" are numbers in a class string — a test repeating the number proves the
 * number is the number, and would fail on any future re-spacing while catching
 * nothing. What is worth holding is the collapse contract, what a stop is allowed
 * to say, and that the chapter you are reading is distinguishable from the ones
 * you are not.
 */

const AREAS: Area[] = [
  { id: "a1", title: "Session–Adapter contract", why: "Where a request is handed off.", order: 0 },
  { id: "a2", title: "Connection pooling", why: "Where sockets are reused.", order: 1 },
];

const stop = (id: string, title: string, area: string, file: string) =>
  node(id, { title, objective: `Explain ${title}`, area_id: area, file }) as GraphNode;

const NODES = [
  stop("n1", "Explain the Session–adapter handoff", "a1", "requests/sessions.py"),
  stop("n2", "Identify the BaseAdapter contract", "a1", "requests/adapters.py"),
  stop("n3", "Explain pool parameters", "a2", "requests/adapters.py"),
];

/** `n2` is current: mid-chapter, so collapse has something to hide on both sides. */
function rail(currentNodeId: string | null = "n2", openSectionId: string | null = null) {
  const edges: GraphEdge[] = NODES.slice(0, -1).map((n, i) => ({
    from_id: n.id,
    to_id: NODES[i + 1].id,
    kind: "sequence",
  }));
  const journey = splitJourney(buildRoute(NODES, edges), AREAS, currentNodeId);
  const onJump = vi.fn();
  const onOpenSection = vi.fn();
  const utils = render(
    <RouteRail
      sections={journey.sections}
      optional={journey.optional}
      currentNodeId={currentNodeId}
      openSectionId={openSectionId}
      onJump={onJump}
      onOpenSection={onOpenSection}
      onExpand={vi.fn()}
    />
  );
  return { ...utils, onJump, onOpenSection };
}

/** The heading button for a chapter — the one that opens its overview. */
const heading = (title: string) =>
  screen.getByRole("button", { name: t.rail.openSection(title) });

describe("collapsed means collapsed (note 5)", () => {
  test("the chapter you are standing in starts open", () => {
    rail("n2");
    expect(screen.getByText("Identify the BaseAdapter contract")).toBeTruthy();
  });

  test("collapsing it hides its stops — including the one you are on", () => {
    // This is the bug the note reported. The rail used to keep the current stop
    // rendered inside a closed section, so the chevron said closed while a row was
    // still sitting there and the control looked broken.
    const { container } = rail("n2");
    fireEvent.click(screen.getByRole("button", { name: /^Collapse Session–Adapter contract/ }));

    expect(screen.queryByText("Identify the BaseAdapter contract")).toBeNull();
    expect(screen.queryByText("Explain the Session–adapter handoff")).toBeNull();
    // And nothing is left claiming to be the current step.
    expect(container.querySelector('[aria-current="step"]')).toBeNull();
  });

  test("re-expanding brings them back", () => {
    rail("n2");
    fireEvent.click(screen.getByRole("button", { name: /^Collapse Session–Adapter contract/ }));
    fireEvent.click(screen.getByRole("button", { name: /^Expand Session–Adapter contract/ }));
    expect(screen.getByText("Identify the BaseAdapter contract")).toBeTruthy();
  });

  test("a chapter you are not in starts collapsed", () => {
    rail("n2");
    expect(screen.queryByText("Explain pool parameters")).toBeNull();
    expect(screen.getByRole("button", { name: /^Expand Connection pooling/ })).toBeTruthy();
  });
});

describe("what a stop is allowed to say (note 1)", () => {
  test("the current stop does not repeat its file path", () => {
    // The path is in the lesson header and in the source pane. Three copies of
    // `requests/adapters.py` on one screen was the note.
    rail("n2");
    expect(screen.queryByText("requests/adapters.py")).toBeNull();
  });

  test("no stop shows a path, current or not", () => {
    rail("n2");
    expect(screen.queryByText("requests/sessions.py")).toBeNull();
  });

  test("the current stop is still identifiable — by state, not by path", () => {
    const { container } = rail("n2");
    const current = container.querySelector('[aria-current="step"]');
    expect(current).toBeTruthy();
    expect(current!.textContent).toContain("Identify the BaseAdapter contract");
  });
});

describe("the chapter heading says whether it is open (note 6)", () => {
  /** The title span inside a heading button carries the tone class. */
  const tone = (title: string) => {
    const span = heading(title).querySelector("span span");
    return (span?.className ?? "")
      .split(" ")
      .filter((c) => /^text-(signal|chalk|graphite)$/.test(c))
      .join(" ");
  };

  test("open, closed and current are three different tones", () => {
    rail("n2");
    // `a1` contains the current stop, so it is open AND current.
    const current = tone("Session–Adapter contract");
    const closed = tone("Connection pooling");
    expect(current).not.toBe(closed);

    // Open it: it is now open but still not the chapter being read.
    fireEvent.click(screen.getByRole("button", { name: /^Expand Connection pooling/ }));
    const opened = tone("Connection pooling");
    expect(opened).not.toBe(closed);
    expect(opened).not.toBe(current);
  });

  test("the current chapter's heading is the loudest", () => {
    rail("n2");
    expect(tone("Session–Adapter contract")).toBe("text-signal");
  });

  test("a collapsed chapter is the quietest", () => {
    rail("n2");
    expect(tone("Connection pooling")).toBe("text-graphite");
  });
});

describe("chapters are actually separated (note 3, second pass)", () => {
  /**
   * The first attempt put `mt-7 … first:mt-0` on the heading row. That row is
   * always the first child of its own section wrapper, so `first:` matched every
   * chapter and zeroed the gap for all of them — measured live at **0px** between
   * collapsed chapters. The stop rows were supplying the only visible spacing,
   * which is why an expanded rail looked fine and hid it.
   *
   * So the claim is not the size. It is that whatever carries the gap has siblings,
   * because a `first:` variant on an only-child cancels itself.
   */
  const gapCarrier = (title: string) => {
    let el: HTMLElement | null = heading(title);
    while (el && !/(^|\s)mt-\d/.test(el.className)) el = el.parentElement;
    return el;
  };

  test("the element carrying the chapter gap is not an only child", () => {
    rail("n2");
    const carrier = gapCarrier("Connection pooling");
    expect(carrier).toBeTruthy();
    // If this is the first child, `first:mt-0` applies and the gap is nothing.
    expect(carrier!.previousElementSibling).toBeTruthy();
  });

  test("the heading row itself carries no top margin", () => {
    rail("n2");
    const row = heading("Connection pooling").parentElement!;
    expect(row.className).not.toMatch(/(^|\s)mt-\d/);
  });

  test("the first chapter has no gap above it, later ones do", () => {
    rail("n2");
    const first = gapCarrier("Session–Adapter contract")!;
    const second = gapCarrier("Connection pooling")!;
    expect(first.previousElementSibling).toBeNull();
    expect(second.className).toMatch(/(^|\s)mt-\d/);
    // Same element type carrying it in both cases — the `first:` variant is what
    // distinguishes them, not two different structures.
    expect(first.className).toBe(second.className);
  });
});

describe("the route scrolls rather than growing past the viewport (note 3)", () => {
  test("the list is its own scroll region inside a fixed-height rail", () => {
    const { container } = rail("n2");
    const aside = container.querySelector("aside");
    const nav = container.querySelector("nav");
    // `h-full min-h-0` on the rail and `overflow-y-auto min-h-0 flex-1` on the
    // list is what makes a fourteen-stop route scroll instead of pushing the
    // optional row and the footer off the bottom.
    expect(aside!.className).toContain("h-full");
    expect(aside!.className).toContain("min-h-0");
    expect(nav!.className).toContain("overflow-y-auto");
    expect(nav!.className).toContain("min-h-0");
  });
});

describe("the heading and the chevron are two controls, not one", () => {
  test("clicking the heading opens the chapter overview without collapsing it", () => {
    const { onOpenSection } = rail("n2");
    fireEvent.click(heading("Session–Adapter contract"));
    expect(onOpenSection).toHaveBeenCalledWith("a1");
    // Still open: opening an overview is not a collapse.
    expect(screen.getByText("Identify the BaseAdapter contract")).toBeTruthy();
  });

  test("collapsing does not open the overview", () => {
    const { onOpenSection } = rail("n2");
    fireEvent.click(screen.getByRole("button", { name: /^Collapse Session–Adapter contract/ }));
    expect(onOpenSection).not.toHaveBeenCalled();
  });

  test("a stop hands the node back, not an id", () => {
    const { onJump } = rail("n2");
    fireEvent.click(screen.getByText("Explain the Session–adapter handoff"));
    expect(onJump).toHaveBeenCalled();
    expect(onJump.mock.calls[0][0].id).toBe("n1");
  });
});
