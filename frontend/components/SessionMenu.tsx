"use client";

import { useEffect, useRef, useState } from "react";
import Button from "@/components/ui/Button";
import { t } from "@/lib/strings";

/**
 * Everything you can do TO the session, in one place.
 *
 * These actions used to sit in the header as loose buttons, and between them they
 * took 919px of a 1280px row — which is why the goal, the one piece of context
 * that says what this session is FOR, was rendering at 110px and at nothing below
 * about 1150px. None of them is used often. A stop-level action belongs on the
 * stop; these are all statements about the whole journey, so they belong behind
 * one control that costs 28px.
 *
 * Ordered by consequence, quietest first: adjusting scope moves units between
 * priority buckets and plans nothing new, the briefing is a page to re-read, the
 * tour is a walkthrough to watch again — then the three that change or end the
 * session, each confirmed inline.
 *
 * ── WHY START OVER AND REBUILD ARE TWO ITEMS ─────────────────────────────────
 *
 * They were one. `Start over` re-ran the entire repository-analysis pipeline: two
 * to four minutes, a Sonnet planning call, and a route that was NOT the one on
 * screen. Someone asking to start over is asking to walk the same path again, so
 * that is what `Start over` now does — a restore from the persisted plan, no model
 * call, milliseconds. Rebuilding is a real thing to want and it is still here,
 * under its own name, with the wait stated in its confirmation.
 *
 * All three confirmations are inline rather than `window.confirm`, because a
 * native dialog cannot say what happens to the work already done — which is the
 * only question any of them raises. They share one `confirming` value rather than
 * a boolean each: two open confirmations for two different destructive actions is
 * a way to press the wrong one.
 *
 * Opening the source is NOT in here, deliberately. It was, briefly, and it was
 * the wrong category: everything in this menu is session management, while opening
 * the code beside a lesson is part of reading the lesson. Lessons cite code
 * throughout and the pane starts closed, so its control has to be findable
 * without already knowing the menu holds it. It sits in the lesson bar instead.
 */
type Confirming = "startOver" | "rebuild" | "finish" | null;

export default function SessionMenu({
  stopCount,
  scoping,
  scopeNote,
  onScope,
  onBriefing,
  onReplayTour,
  onStartOver,
  startingOver,
  onRebuild,
  rebuilding,
  onFinish,
  className = "",
}: {
  stopCount: number;
  scoping: boolean;
  scopeNote: string | null;
  onScope: (direction: "shorter" | "deeper") => void;
  onBriefing: () => void;
  /** Run the first-run walkthrough again. Absent where there is no tour to run. */
  onReplayTour?: () => void;
  /** Restore the SAME route and clear the learner's work. Fast, no model call. */
  onStartOver: () => void;
  startingOver: boolean;
  /** Plan a NEW route for the same goal. The two-to-four-minute one. */
  onRebuild: () => void;
  rebuilding: boolean;
  onFinish: () => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState<Confirming>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const busy = startingOver || rebuilding;

  // Dismissal: escape, or a click outside. Capture on the key, so the session
  // page's own Escape handler does not also fire and close the map behind this.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
        setConfirming(null);
        buttonRef.current?.focus();
      }
    };
    const onPointer = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpen(false);
        setConfirming(null);
      }
    };
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("pointerdown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  /** Fire an action, then get out of the way — each has its own surface now. */
  const commit = (action: () => void) => {
    action();
    setOpen(false);
    setConfirming(null);
  };

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => {
          setOpen((v) => !v);
          setConfirming(null);
        }}
        aria-label={t.session.menu}
        aria-haspopup="dialog"
        aria-expanded={open}
        className={`flex h-[1.75rem] w-[1.75rem] shrink-0 items-center justify-center rounded-field border font-mono text-aside leading-none transition ${
          open
            ? "border-signal-dim bg-signal/15 text-signal"
            : "border-rule bg-slab text-graphite hover:border-signal-dim hover:text-signal"
        }`}
      >
        <span aria-hidden>⋯</span>
      </button>

      {open && (
        <div
          role="dialog"
          aria-label={t.session.menuTitle}
          className="absolute end-0 top-[calc(100%+0.5rem)] z-50 flex w-[17rem] flex-col gap-4 rounded-panel border border-rule bg-slab p-3.5 shadow-overlay"
        >
          {/* Scope (U4): a statement about the whole journey, which is why it was
              in the header at all and why it is here now rather than on a stop. */}
          <section className="flex flex-col gap-2">
            <span className="font-mono text-micro uppercase tracking-[0.13em] text-graphite">
              {t.scope.label(stopCount)}
            </span>
            <div className="flex gap-2">
              <Button
                variant="chrome"
                size="xs"
                onClick={() => onScope("shorter")}
                disabled={scoping}
              >
                {scoping ? t.scope.working : t.scope.shorter}
              </Button>
              <Button
                variant="chrome"
                size="xs"
                onClick={() => onScope("deeper")}
                disabled={scoping}
              >
                {t.scope.deeper}
              </Button>
            </div>
            {scopeNote && (
              <span className="font-mono text-micro text-signal">{scopeNote}</span>
            )}
          </section>

          <div className="flex flex-col gap-1 border-t border-rule pt-3">
            <MenuItem onClick={() => commit(onBriefing)}>
              {t.welcome.headerLink}
            </MenuItem>
            {/* Sits with the briefing rather than with the destructive group
                below: both are "show me the orientation again", and neither
                changes anything about the session. */}
            {onReplayTour && (
              <MenuItem onClick={() => commit(onReplayTour)}>
                {t.tour.replay}
              </MenuItem>
            )}
          </div>

          {/* The three that change or end the session, each confirmed. Start over
              leads because it is the one people actually want: same route, fresh
              start, instant. */}
          <div className="flex flex-col gap-2 border-t border-rule pt-3">
            {confirming === "startOver" ? (
              <Confirm
                question={t.session.startOverConfirm}
                yes={t.session.startOverYes}
                no={t.session.startOverNo}
                onYes={() => commit(onStartOver)}
                onNo={() => setConfirming(null)}
              />
            ) : (
              <MenuItem onClick={() => setConfirming("startOver")} disabled={busy}>
                {startingOver ? t.session.startingOver : t.session.startOver}
              </MenuItem>
            )}

            {confirming === "rebuild" ? (
              <Confirm
                question={t.session.rebuildConfirm}
                yes={t.session.rebuildYes}
                no={t.session.rebuildNo}
                onYes={() => commit(onRebuild)}
                onNo={() => setConfirming(null)}
              />
            ) : (
              <MenuItem onClick={() => setConfirming("rebuild")} disabled={busy}>
                {rebuilding ? t.session.rebuilding : t.session.rebuild}
              </MenuItem>
            )}
          </div>

          <div className="flex flex-col gap-2 border-t border-rule pt-3">
            {confirming === "finish" ? (
              <Confirm
                question={t.session.finishConfirm}
                yes={t.session.finishYes}
                no={t.session.finishNo}
                onYes={() => commit(onFinish)}
                onNo={() => setConfirming(null)}
              />
            ) : (
              <MenuItem onClick={() => setConfirming("finish")}>
                {t.session.finish}
              </MenuItem>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * One inline confirmation: what will happen, then the two ways out.
 *
 * The question is a statement of consequence rather than "are you sure" — the
 * real question for all three of these is what happens to the work already done,
 * and only prose can answer it.
 */
function Confirm({
  question,
  yes,
  no,
  onYes,
  onNo,
}: {
  question: string;
  yes: string;
  no: string;
  onYes: () => void;
  onNo: () => void;
}) {
  return (
    <>
      <p className="text-meta text-paper">{question}</p>
      <div className="flex gap-2">
        <Button variant="primary" size="sm" onClick={onYes}>
          {yes}
        </Button>
        <Button variant="chrome" size="sm" onClick={onNo}>
          {no}
        </Button>
      </div>
    </>
  );
}

function MenuItem({
  onClick,
  disabled = false,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="-mx-1.5 rounded-field px-1.5 py-1.5 text-start text-aside text-paper transition hover:bg-raise hover:text-signal"
    >
      {children}
    </button>
  );
}
