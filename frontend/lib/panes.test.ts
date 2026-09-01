import { describe, expect, test } from "vitest";
import {
  closePane,
  dockedPane,
  isDocked,
  openPane,
  openPanes,
  paneOf,
  setPaneMode,
} from "@/lib/panes";
import { DEFAULT_PREFS, DEFAULT_SOURCE, DEFAULT_TUTOR, type Prefs } from "@/lib/prefs";

/**
 * The one-dock-slot rule, case by case.
 *
 * Every test here is a sentence from `lib/panes.ts`'s header, and the reason they
 * are worth writing is that the failure mode is invisible: two docked panes do not
 * throw, they render one into a grid track that only reserved room for the other.
 */

const base = (over: Partial<Prefs> = {}): Prefs => ({
  ...DEFAULT_PREFS,
  source: { ...DEFAULT_SOURCE },
  tutor: { ...DEFAULT_TUTOR },
  ...over,
});

const apply = (prefs: Prefs, patch: Partial<Prefs>): Prefs => ({ ...prefs, ...patch });

const docked = (over = {}) => ({ ...DEFAULT_SOURCE, open: true, mode: "dock" as const, ...over });
const floating = (over = {}) => ({ ...DEFAULT_SOURCE, open: true, mode: "float" as const, ...over });

describe("only one pane may hold the column", () => {
  test("opening Chat while Source is docked closes Source", () => {
    const prefs = base({ source: docked() });
    const next = apply(prefs, openPane(prefs, "tutor"));

    expect(next.tutor.open).toBe(true);
    expect(next.tutor.mode).toBe("dock");
    expect(next.source.open).toBe(false);
    expect(dockedPane(next)).toBe("tutor");
  });

  test("the evicted pane keeps its mode, so reopening restores what they had", () => {
    const prefs = base({ source: docked({ dockWidth: 30 }) });
    const afterOpen = apply(prefs, openPane(prefs, "tutor"));

    expect(afterOpen.source.mode).toBe("dock");
    expect(afterOpen.source.dockWidth).toBe(30);

    const back = apply(afterOpen, openPane(afterOpen, "source"));
    expect(back.source.open).toBe(true);
    expect(back.source.mode).toBe("dock");
    expect(back.tutor.open).toBe(false);
  });

  test("docking through the mode control evicts too — same state, different door", () => {
    const prefs = base({ source: docked(), tutor: floating() });
    expect(dockedPane(prefs)).toBe("source");

    const next = apply(prefs, setPaneMode(prefs, "tutor", "dock"));
    expect(next.tutor.mode).toBe("dock");
    expect(next.source.open).toBe(false);
    expect(dockedPane(next)).toBe("tutor");
  });

  test("two panes are never both docked, however they got there", () => {
    let prefs = base();
    prefs = apply(prefs, openPane(prefs, "source"));
    prefs = apply(prefs, openPane(prefs, "tutor"));
    prefs = apply(prefs, setPaneMode(prefs, "source", "dock"));

    const bothDocked = isDocked(prefs.source) && isDocked(prefs.tutor);
    expect(bothDocked).toBe(false);
  });
});

describe("detaching is what lets them coexist", () => {
  test("floating Chat gives the column back, so Source can dock beside it", () => {
    let prefs = base({ source: docked() });
    prefs = apply(prefs, openPane(prefs, "tutor"));       // Source evicted
    prefs = apply(prefs, setPaneMode(prefs, "tutor", "float"));
    prefs = apply(prefs, openPane(prefs, "source"));      // docks; nothing to evict

    expect(prefs.source.open).toBe(true);
    expect(prefs.source.mode).toBe("dock");
    expect(prefs.tutor.open).toBe(true);
    expect(prefs.tutor.mode).toBe("float");
    expect(dockedPane(prefs)).toBe("source");
    expect(openPanes(prefs)).toEqual(["source", "tutor"]);
  });

  test("Source floating and Chat docked is the mirror image, and also reachable", () => {
    let prefs = base({ source: floating() });
    prefs = apply(prefs, openPane(prefs, "tutor"));

    expect(prefs.source.open).toBe(true);
    expect(dockedPane(prefs)).toBe("tutor");
    expect(openPanes(prefs)).toEqual(["tutor", "source"]);
  });

  test("both floating claims no column at all", () => {
    const prefs = base({ source: floating(), tutor: floating() });
    expect(dockedPane(prefs)).toBeNull();
    expect(openPanes(prefs).sort()).toEqual(["source", "tutor"]);
  });

  test("floating a pane never evicts the other", () => {
    const prefs = base({ source: docked() });
    const next = apply(prefs, openPane(prefs, "tutor", true));   // must float

    expect(next.tutor.mode).toBe("float");
    expect(next.source.open).toBe(true);
    expect(dockedPane(next)).toBe("source");
  });
});

describe("a dock that would crowd the lesson opens floating instead", () => {
  test("mustFloat overrides the stored mode on open", () => {
    const prefs = base();
    const next = apply(prefs, openPane(prefs, "tutor", true));
    expect(next.tutor.open).toBe(true);
    expect(next.tutor.mode).toBe("float");
  });

  test("it is a starting point, not a lock — the stored mode is untouched next time", () => {
    let prefs = base();
    prefs = apply(prefs, openPane(prefs, "tutor", true));
    prefs = apply(prefs, closePane(prefs, "tutor"));
    // Reopening on a wider window gets the dock back, because `mode` was only
    // overridden for that one open and then committed by the caller as float…
    prefs = apply(prefs, setPaneMode(prefs, "tutor", "dock"));
    prefs = apply(prefs, openPane(prefs, "tutor", false));
    expect(prefs.tutor.mode).toBe("dock");
  });

  test("a pane already stored as float is unaffected by mustFloat", () => {
    const prefs = base({ tutor: { ...DEFAULT_TUTOR, mode: "float" } });
    const next = apply(prefs, openPane(prefs, "tutor", true));
    expect(next.tutor.mode).toBe("float");
  });
});

describe("closing", () => {
  test("closing one never opens or moves the other — eviction is not a stack", () => {
    let prefs = base({ source: docked() });
    prefs = apply(prefs, openPane(prefs, "tutor"));
    expect(prefs.source.open).toBe(false);

    prefs = apply(prefs, closePane(prefs, "tutor"));
    expect(prefs.tutor.open).toBe(false);
    expect(prefs.source.open).toBe(false);
    expect(dockedPane(prefs)).toBeNull();
  });

  test("closing preserves everything else about the pane", () => {
    const prefs = base({ tutor: { ...DEFAULT_TUTOR, open: true, mode: "float", dockWidth: 40 } });
    const next = apply(prefs, closePane(prefs, "tutor"));
    expect(next.tutor).toEqual({ ...prefs.tutor, open: false });
  });
});

describe("older stored preferences", () => {
  test("a blob with no tutor key resolves to the default rather than undefined", () => {
    const legacy = { ...DEFAULT_PREFS, source: docked() } as Prefs;
    delete (legacy as Partial<Prefs>).tutor;

    expect(paneOf(legacy, "tutor")).toEqual(DEFAULT_TUTOR);
    expect(dockedPane(legacy)).toBe("source");
    expect(openPanes(legacy)).toEqual(["source"]);
  });
});
