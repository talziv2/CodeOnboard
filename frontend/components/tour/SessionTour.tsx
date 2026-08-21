"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import TourOverlay from "@/components/tour/TourOverlay";
import {
  entryFix,
  reduceTour,
  startTour,
  TOUR_STEPS,
  type TourContext,
  type TourEvent,
  type TourState,
} from "@/lib/tour";
import { markTourDone, readTour } from "@/lib/tourState";
import type { TabEvent } from "@/lib/surfaceTabs";

/**
 * The tour, wired to the session.
 *
 * It owns three things and deliberately no more: when the walk starts, the
 * reducer's state, and the two side effects a step is allowed to have on the app
 * — putting the column back where a step's target lives (`entryFix`), and opening
 * the source pane for the one step that is about the pane itself.
 *
 * ── WHAT IT IS ALLOWED TO CHANGE ──────────────────────────────────────────────
 *
 * Tab selection in this app moves through exactly one reducer, and R5 says it
 * moves only because the learner asked or because they arrived at a different
 * stop (`lib/surfaceTabs.ts`). The tour does not get an exemption: it dispatches
 * ordinary `TabEvent`s through the same `dispatchTab`, so its navigation is the
 * learner's navigation with the learner's own events. What it must never do is
 * reach past that into `setTabState`, which would be a second thing that moves
 * the selection — the exact hazard the reducer exists to prevent.
 *
 * The source pane is restored only if the TOUR opened it. On the ordinary walk
 * the learner opens it themselves by clicking a code citation, and closing
 * something they clicked would be undoing their own action; the pane's open state
 * is a persisted preference, and them having opened it is real signal. The tour
 * only force-opens it when the citation step was skipped for want of anchors, and
 * that is the one case it puts back.
 */
export default function SessionTour({
  ready,
  fresh,
  replay,
  ctx,
  onTabEvent,
  onSource,
  onEnded,
}: {
  /** The workspace has a graph and a lesson on screen — nothing to point at before. */
  ready: boolean;
  /** Nothing has been settled in this session yet. A resumed session is not a first run. */
  fresh: boolean;
  /**
   * A nonce from the ⋯ menu. `0` means nobody asked, which is the automatic
   * first run; anything higher is an explicit replay and ignores the stored flag.
   */
  replay: number;
  ctx: TourContext;
  onTabEvent: (event: TabEvent) => void;
  onSource: (open: boolean) => void;
  onEnded?: () => void;
}) {
  const [state, setState] = useState<TourState | null>(null);
  // The reducer needs the live context in callbacks that must not change identity
  // every render — a new `onMissing` on every frame would restart the overlay's
  // measurement loop, which is the loop that detects a missing target.
  const ctxRef = useRef(ctx);
  ctxRef.current = ctx;
  const openedByTour = useRef(false);
  const handledReplay = useRef<number | null>(null);

  // ── starting ────────────────────────────────────────────────────────────────
  //
  // `ready` says the session has a graph. It does NOT say there is a lesson on
  // screen: the first stop is written by a model, and until it comes back the
  // column holds "Writing this lesson…" and none of the blocks the tour points
  // at exist. Starting then would walk the brief, the citations and the composer
  // straight past as missing targets — a tour that skips the middle of itself
  // for being early. So the automatic run waits for the brief to actually be in
  // the document.
  //
  // An explicit replay does not wait. The learner asked for it, the lesson is by
  // then long since written, and they may be standing in Route mode where the
  // brief is legitimately absent — `entryFix` brings the column back.
  useEffect(() => {
    if (!ready) return;
    if (handledReplay.current === replay) return;
    const automatic = replay === 0;
    // Automatically: once per browser, and never over a session already in
    // progress — somebody resuming their fifth stop has met the interface.
    if (automatic && (readTour().done || !fresh)) {
      handledReplay.current = replay;
      return;
    }

    const begin = () => {
      handledReplay.current = replay;
      openedByTour.current = false;
      setState(startTour(ctxRef.current));
    };

    if (!automatic) {
      begin();
      return;
    }

    if (document.querySelector('[data-tour="brief"]')) {
      begin();
      return;
    }
    const poll = window.setInterval(() => {
      if (!document.querySelector('[data-tour="brief"]')) return;
      window.clearInterval(poll);
      begin();
    }, 250);
    return () => window.clearInterval(poll);
  }, [ready, fresh, replay]);

  const dispatch = useCallback((event: TourEvent) => {
    setState((current) =>
      current && current.status === "running" ? reduceTour(current, event, ctxRef.current) : current
    );
  }, []);

  // ── the learner did something the tour was waiting for ──────────────────────
  //
  // Fields rather than the object: `ctx` is rebuilt every render, and depending on
  // its identity would run this on every frame the page repaints.
  useEffect(() => {
    dispatch({ kind: "observed", ctx: ctxRef.current });
  }, [ctx.tab, ctx.sourceOpen, dispatch]);

  // ── entering a step ─────────────────────────────────────────────────────────
  const index = state?.status === "running" ? state.index : null;
  useEffect(() => {
    if (index === null) return;
    const step = TOUR_STEPS[index];
    const fix = entryFix(step, ctxRef.current);
    if (fix) onTabEvent(fix);
    if (step.id === "source" && !ctxRef.current.sourceOpen) {
      openedByTour.current = true;
      onSource(true);
    }
    // `onTabEvent` and `onSource` are stable callbacks from the page; the step
    // index is the whole trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index]);

  // ── ending ──────────────────────────────────────────────────────────────────
  const finished = state?.status === "done";
  useEffect(() => {
    if (!finished) return;
    markTourDone();
    if (openedByTour.current) {
      openedByTour.current = false;
      onSource(false);
    }
    // Leave the learner on the lesson. The Route round trip lands them back on
    // whichever learn tab they had open, which by then is Understanding — an
    // empty surface is a poor place to hand the session over.
    onTabEvent({ kind: "picked", tab: "lesson" });
    setState(null);
    onEnded?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finished]);

  const onMissing = useCallback(() => dispatch({ kind: "missing" }), [dispatch]);

  if (!state || state.status !== "running") return null;

  return (
    <TourOverlay
      step={TOUR_STEPS[state.index]}
      index={state.index}
      armed={state.armed}
      onNext={() => dispatch({ kind: "advance" })}
      onBack={() => dispatch({ kind: "back" })}
      onSkip={() => dispatch({ kind: "skip" })}
      onMissing={onMissing}
    />
  );
}
