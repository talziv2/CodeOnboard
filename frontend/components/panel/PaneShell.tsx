"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  DOCK_MAX_REM,
  DOCK_MIN_REM,
  FLOAT_MIN_H,
  FLOAT_MIN_W,
  applyDockWidth,
  clamp,
  remInPx,
  type FloatRect,
  type PanePrefs,
} from "@/lib/prefs";
import { placeFloat, type PlacedRect } from "@/lib/source-pane";
import { t } from "@/lib/strings";

/**
 * A companion pane: a resizable third column, or a window over the lesson.
 *
 * ── WHY THIS MODULE EXISTS ────────────────────────────────────────────────────
 *
 * All of this lived inside `CodeViewer` and was private to it. Nothing in it is
 * about source code: `FloatShell` is a draggable window, `DockDivider` is a
 * column grip, and the mode buttons are a two-way switch. When the Tutor needed
 * the same behaviour, there were two options — copy it, or move it here.
 *
 * Copying it would have been a second window system, with its own drag maths, its
 * own `placeFloat` call and its own opinion about what `--source-width` means.
 * Two implementations of "a pane you can undock" diverge on the first bug fixed
 * in one of them. So it moved, unchanged, and `CodeViewer` now renders through it
 * — which is why `CodeViewer.test.tsx` passes without an edit. That test suite is
 * the acceptance criterion for this extraction, not a casualty of it.
 *
 * ── WHAT THE CALLER STILL OWNS ────────────────────────────────────────────────
 *
 * The header CONTENT (a file path and a line range; a mode strip and a counter)
 * and the body. This owns the frame, the chrome around the header, and both
 * gestures.
 *
 * `--source-width` is shared by both panes on purpose. Only one may be docked at
 * a time (`lib/panes.ts`), so there is only ever one column to size — and a
 * learner who has dragged that column to the width they like keeps it whichever
 * pane is in it.
 */

/** One resize grip. `cx` / `cy` say which edges the gesture moves. */
const HANDLES: { id: string; cx: -1 | 0 | 1; cy: -1 | 0 | 1; cls: string }[] = [
  { id: "n", cx: 0, cy: -1, cls: "inset-x-0 top-0 h-1.5 cursor-ns-resize" },
  { id: "s", cx: 0, cy: 1, cls: "inset-x-0 bottom-0 h-1.5 cursor-ns-resize" },
  { id: "w", cx: -1, cy: 0, cls: "inset-y-0 left-0 w-1.5 cursor-ew-resize" },
  { id: "e", cx: 1, cy: 0, cls: "inset-y-0 right-0 w-1.5 cursor-ew-resize" },
  // After the edges, so the corners win where they overlap.
  { id: "nw", cx: -1, cy: -1, cls: "left-0 top-0 h-3 w-3 cursor-nwse-resize" },
  { id: "ne", cx: 1, cy: -1, cls: "right-0 top-0 h-3 w-3 cursor-nesw-resize" },
  { id: "sw", cx: -1, cy: 1, cls: "bottom-0 left-0 h-3 w-3 cursor-nesw-resize" },
  { id: "se", cx: 1, cy: 1, cls: "bottom-0 right-0 h-3 w-3 cursor-nwse-resize" },
];

/** Keyboard resize step for the docked divider, in rem. */
const NUDGE = 1.5;

export default function PaneShell({
  prefs,
  onPrefsChange,
  onClose,
  header,
  children,
  tourId,
  label,
  closeLabel,
}: {
  prefs: PanePrefs;
  onPrefsChange: (change: Partial<PanePrefs>) => void;
  onClose: () => void;
  /** Pane-specific header content, rendered inside the shared chrome. */
  header: ReactNode;
  children: ReactNode;
  tourId: string;
  /** Names the floating window for assistive technology. */
  label: string;
  closeLabel: string;
}) {
  const chrome = (
    <PaneHeader
      mode={prefs.mode}
      onMode={(mode) => onPrefsChange({ mode })}
      onClose={onClose}
      closeLabel={closeLabel}
    >
      {header}
    </PaneHeader>
  );

  if (prefs.mode === "float") {
    return (
      <FloatShell
        rect={prefs.float}
        onCommit={(float) => onPrefsChange({ float })}
        tourId={tourId}
        label={label}
      >
        {chrome}
        {children}
      </FloatShell>
    );
  }

  return (
    <aside data-tour={tourId} className="relative flex min-h-0 flex-col bg-trench">
      <DockDivider
        width={prefs.dockWidth}
        onCommit={(dockWidth) => onPrefsChange({ dockWidth })}
      />
      {chrome}
      {children}
    </aside>
  );
}

// ── Chrome ───────────────────────────────────────────────────────────────────

export function PaneHeader({
  mode,
  onMode,
  onClose,
  closeLabel,
  children,
}: {
  mode: PanePrefs["mode"];
  onMode: (mode: PanePrefs["mode"]) => void;
  onClose: () => void;
  closeLabel: string;
  children: ReactNode;
}) {
  return (
    // `pane-grip` marks what a floating pane can be dragged by. The buttons opt
    // back out below, so clicking one never also moves the window.
    <div
      className={`pane-grip flex shrink-0 items-center gap-2.5 border-b border-rule px-3.5 py-2.5 ${
        mode === "float" ? "cursor-move touch-none select-none" : ""
      }`}
    >
      {children}

      <span className="flex shrink-0 items-center rounded-field border border-rule">
        <ModeButton active={mode === "dock"} label={t.source.dock} onClick={() => onMode("dock")}>
          <DockIcon />
        </ModeButton>
        <ModeButton active={mode === "float"} label={t.source.float} onClick={() => onMode("float")}>
          <FloatIcon />
        </ModeButton>
      </span>

      <button
        data-no-drag
        onClick={onClose}
        aria-label={closeLabel}
        className="shrink-0 font-mono text-micro text-graphite transition hover:text-signal"
      >
        ✕
      </button>
    </div>
  );
}

function ModeButton({
  active, label, onClick, children,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      data-no-drag
      type="button"
      onClick={onClick}
      aria-pressed={active}
      aria-label={label}
      title={label}
      className={`flex h-[1.4rem] w-[1.6rem] items-center justify-center transition first:rounded-s-[3px] last:rounded-e-[3px] ${
        active ? "bg-signal/15 text-signal" : "text-graphite hover:text-chalk"
      }`}
    >
      {children}
    </button>
  );
}

/**
 * The docked pane's left edge, dragged to set the column width.
 *
 * The gesture writes the CSS variable directly and only tells React on release
 * — the grid re-flows on every pointer move, and re-rendering the pane's body
 * with it would make the drag stutter on any real source file.
 */
function DockDivider({
  width, onCommit,
}: {
  width: number;
  onCommit: (rem: number) => void;
}) {
  const drag = useRef<{ x: number; from: number; to: number } | null>(null);

  const move = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    // The pane is on the trailing edge, so dragging the divider *left* widens it.
    d.to = clamp(d.from + (d.x - e.clientX) / remInPx(), DOCK_MIN_REM, DOCK_MAX_REM);
    applyDockWidth(d.to);
  };

  const end = (e: React.PointerEvent) => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    onCommit(d.to);
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      // Declared, so the focus probe reads this as intended rather than missed.
      data-focus-exempt=""
      aria-label={t.source.resize}
      tabIndex={0}
      onPointerDown={(e) => {
        e.preventDefault();
        (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
        drag.current = { x: e.clientX, from: width, to: width };
      }}
      onPointerMove={move}
      onPointerUp={end}
      onPointerCancel={end}
      onKeyDown={(e) => {
        const step = e.key === "ArrowLeft" ? NUDGE : e.key === "ArrowRight" ? -NUDGE : 0;
        if (!step) return;
        e.preventDefault();
        const next = clamp(width + step, DOCK_MIN_REM, DOCK_MAX_REM);
        applyDockWidth(next);
        onCommit(next);
      }}
      // The one deliberate opt-out from the global focus ring. This is a
      // full-height 8px drag handle sitting outside the pane's own bounds, so an
      // outline would be drawn half-clipped by the grid track; filling it is both
      // clearer and better placed. The fill IS the focus indicator here.
      className="absolute inset-y-0 -start-1 z-20 w-2 cursor-ew-resize touch-none bg-transparent transition hover:bg-signal/25 focus-visible:bg-signal/40 focus-visible:outline-none"
    />
  );
}

/**
 * The floating pane: a window over the lesson, moved by its header and resized
 * from any edge or corner.
 *
 * Like the docked divider, both gestures write to the element's own style and
 * hand the result to React only on release.
 */
function FloatShell({
  rect, onCommit, children, tourId, label,
}: {
  rect: FloatRect;
  onCommit: (rect: FloatRect) => void;
  children: ReactNode;
  tourId: string;
  label: string;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const [placed, setPlaced] = useState<PlacedRect | null>(null);
  const drag = useRef<
    | ({ px: number; py: number; cx: number; cy: number; moving: boolean } & PlacedRect & {
        next: PlacedRect;
      })
    | null
  >(null);

  // Resolve against the viewport on open, and again if the window changes size
  // — a rect saved on a wider screen must not leave the pane off the edge.
  useEffect(() => {
    const settle = () =>
      setPlaced((prev) => placeFloat(prev ?? rect, window.innerWidth, window.innerHeight));
    settle();
    window.addEventListener("resize", settle);
    return () => window.removeEventListener("resize", settle);
    // Only the stored rect seeds this; later changes come from the gestures.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The gesture starts from where the pane actually *is*, measured now, rather
  // than from the last committed state: the two agree, except in the window
  // between one gesture ending and React re-rendering, and the element is the
  // one that can't be stale.
  const begin = useCallback((e: React.PointerEvent, cx: number, cy: number, moving: boolean) => {
    const el = panel.current;
    if (!el) return;
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    const box = el.getBoundingClientRect();
    const from = { x: box.left, y: box.top, w: box.width, h: box.height };
    drag.current = { px: e.clientX, py: e.clientY, cx, cy, moving, ...from, next: from };
  }, []);

  const move = (e: React.PointerEvent) => {
    const d = drag.current;
    const el = panel.current;
    if (!d || !el) return;

    const dx = e.clientX - d.px;
    const dy = e.clientY - d.py;
    let { x, y, w, h } = d;

    if (d.moving) {
      x += dx;
      y += dy;
    } else {
      if (d.cx === -1) {
        const next = Math.max(FLOAT_MIN_W, w - dx);
        x += w - next;
        w = next;
      } else if (d.cx === 1) {
        w = Math.max(FLOAT_MIN_W, w + dx);
      }
      if (d.cy === -1) {
        const next = Math.max(FLOAT_MIN_H, h - dy);
        y += h - next;
        h = next;
      } else if (d.cy === 1) {
        h = Math.max(FLOAT_MIN_H, h + dy);
      }
    }

    const next = placeFloat({ x, y, w, h }, window.innerWidth, window.innerHeight);
    d.next = next;
    el.style.left = `${next.x}px`;
    el.style.top = `${next.y}px`;
    el.style.width = `${next.w}px`;
    el.style.height = `${next.h}px`;
  };

  const end = (e: React.PointerEvent) => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    setPlaced(d.next);
    onCommit(d.next);
  };

  if (!placed) return null;

  return (
    <div
      ref={panel}
      data-tour={tourId}
      role="dialog"
      aria-label={label}
      style={{ left: placed.x, top: placed.y, width: placed.w, height: placed.h }}
      // One set of move/up handlers for every gesture: whichever grip captured
      // the pointer, its events bubble back here.
      onPointerDown={(e) => {
        const target = e.target as HTMLElement;
        if (target.closest("[data-no-drag]")) return;
        if (!target.closest(".pane-grip")) return;
        begin(e, 0, 0, true);
      }}
      onPointerMove={move}
      onPointerUp={end}
      onPointerCancel={end}
      className="fixed z-40 flex min-h-0 flex-col overflow-hidden rounded-panel border border-rule bg-trench shadow-overlay"
    >
      {children}

      {HANDLES.map((handle) => (
        <div
          key={handle.id}
          aria-hidden
          onPointerDown={(e) => begin(e, handle.cx, handle.cy, false)}
          className={`absolute z-30 touch-none ${handle.cls}`}
        />
      ))}
    </div>
  );
}

// ── Icons ────────────────────────────────────────────────────────────────────

function DockIcon() {
  return (
    <svg aria-hidden viewBox="0 0 16 16" className="h-[0.8rem] w-[0.8rem] fill-none stroke-current stroke-[1.3]">
      <rect x="2" y="3" width="12" height="10" rx="1.2" />
      <path d="M10 3v10" />
    </svg>
  );
}

function FloatIcon() {
  return (
    <svg aria-hidden viewBox="0 0 16 16" className="h-[0.8rem] w-[0.8rem] fill-none stroke-current stroke-[1.3]">
      <rect x="1.8" y="4.6" width="8.6" height="7.6" rx="1.2" />
      <path d="M6 4.6V3.4a1.2 1.2 0 0 1 1.2-1.2H13a1.2 1.2 0 0 1 1.2 1.2v5.4A1.2 1.2 0 0 1 13 10h-1" />
    </svg>
  );
}
