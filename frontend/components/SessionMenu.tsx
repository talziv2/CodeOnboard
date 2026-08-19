"use client";

import { useEffect, useRef, useState } from "react";
import Button from "@/components/ui/Button";
import { t } from "@/lib/strings";

/**
 * Everything you can do TO the session, in one place.
 *
 * These four actions used to sit in the header as loose buttons, and between them
 * they took 919px of a 1280px row — which is why the goal, the one piece of
 * context that says what this session is FOR, was rendering at 110px and at
 * nothing below about 1150px. None of them is used often. A stop-level action
 * belongs on the stop; these are all statements about the whole journey, so they
 * belong behind one control that costs 28px.
 *
 * Ordered by consequence, quietest first: adjusting scope moves units between
 * priority buckets and plans nothing new, the briefing is a page to re-read,
 * starting over builds a fresh session on the same goal, and finishing ends this
 * one. Only the last is confirmed, and the confirmation is inline rather than a
 * `window.confirm` — a native dialog cannot say what will happen to the work
 * already done, which is the only question worth asking here.
 *
 * `Show source` appears only when the pane is closed. The pane owns its own
 * close, so a `Hide source` here would be a second control for something the
 * thing itself already does; without the `Show` half, though, closing the pane
 * would be one-way whenever the lesson has no citation to click.
 */
export default function SessionMenu({
  stopCount,
  scoping,
  scopeNote,
  onScope,
  sourceHidden,
  onShowSource,
  onBriefing,
  onStartOver,
  restarting,
  onFinish,
  className = "",
}: {
  stopCount: number;
  scoping: boolean;
  scopeNote: string | null;
  onScope: (direction: "shorter" | "deeper") => void;
  /** Undefined when there is no source pane to speak of (the map tab). */
  sourceHidden?: boolean;
  onShowSource?: () => void;
  onBriefing: () => void;
  onStartOver: () => void;
  restarting: boolean;
  onFinish: () => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [confirmingFinish, setConfirmingFinish] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // Dismissal: escape, or a click outside. Capture on the key, so the session
  // page's own Escape handler does not also fire and close the map behind this.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
        setConfirmingFinish(false);
        buttonRef.current?.focus();
      }
    };
    const onPointer = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpen(false);
        setConfirmingFinish(false);
      }
    };
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("pointerdown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => {
          setOpen((v) => !v);
          setConfirmingFinish(false);
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
            {sourceHidden && onShowSource && (
              <MenuItem
                onClick={() => {
                  onShowSource();
                  setOpen(false);
                }}
              >
                {t.session.showSource}
              </MenuItem>
            )}
            <MenuItem
              onClick={() => {
                onBriefing();
                setOpen(false);
              }}
            >
              {t.welcome.headerLink}
            </MenuItem>
            <MenuItem onClick={onStartOver} disabled={restarting}>
              {restarting ? t.session.startingOver : t.session.startOver}
            </MenuItem>
          </div>

          <div className="flex flex-col gap-2 border-t border-rule pt-3">
            {confirmingFinish ? (
              <>
                <p className="text-meta text-paper">{t.session.finishConfirm}</p>
                <div className="flex gap-2">
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => {
                      onFinish();
                      setOpen(false);
                      setConfirmingFinish(false);
                    }}
                  >
                    {t.session.finishYes}
                  </Button>
                  <Button
                    variant="chrome"
                    size="sm"
                    onClick={() => setConfirmingFinish(false)}
                  >
                    {t.session.finishNo}
                  </Button>
                </div>
              </>
            ) : (
              <MenuItem onClick={() => setConfirmingFinish(true)}>
                {t.session.finish}
              </MenuItem>
            )}
          </div>
        </div>
      )}
    </div>
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
