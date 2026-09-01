"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import HintLadder, { RevealedExplanation } from "@/components/tutor/HintLadder";
import TutorComposer from "@/components/tutor/TutorComposer";
import TutorTurn from "@/components/tutor/TutorTurn";
import PaneShell from "@/components/panel/PaneShell";
import Button from "@/components/ui/Button";
import {
  askTutor,
  getTutor,
  tutorHint,
  tutorPin,
  tutorReveal,
  type TutorCitation,
  type TutorMode,
  type TutorSuggestion,
  type TutorTurn as Turn,
} from "@/lib/api";
import { type PanePrefs } from "@/lib/prefs";
import { errorTextOr, t } from "@/lib/strings";

/**
 * The Tutor, in the same pane the source uses.
 *
 * ── WHAT THIS COMPONENT DOES NOT DECIDE ───────────────────────────────────────
 *
 * Which mode it is in, whether a hint is available, whether the reveal is, what
 * an offer would do, and how much allowance is left. **All of it arrives from the
 * server**, on every response, and is re-read rather than re-derived — D22's rule
 * that the frontend renders learning decisions and does not compute them.
 *
 * The mode especially. A client that inferred "there is a question on screen, so
 * scaffold" would be a client whose inference could be wrong, and the failure
 * mode of being wrong here is handing over the answer key. `mode.mode` is
 * recomputed from the graph on the server for every single call.
 *
 * ── THE TRANSCRIPT IS FILTERED, NOT SPLIT ─────────────────────────────────────
 *
 * One session-scoped conversation, shown for the stop the learner is on, with the
 * rest behind a closed disclosure. Landing on a new stop showing the previous
 * stop's conversation is the same "empty room" mistake `surfaceTabs.ts` names
 * about tabs — and hiding the earlier turns entirely would make the panel look
 * like it forgot.
 */
export default function TutorPanel({
  sessionId,
  nodeId,
  prefs,
  onPrefsChange,
  onClose,
  onCite,
  onSuggestion,
  onTranscriptChange,
}: {
  sessionId: string;
  /** The stop the learner is on. Changing it re-filters, never re-fetches. */
  nodeId: string | null;
  prefs: PanePrefs;
  onPrefsChange: (change: Partial<PanePrefs>) => void;
  onClose: () => void;
  /** A citation click opens the source pane at that range. */
  onCite: (citation: TutorCitation) => void;
  /** A validated offer, pressed. The page routes it to the existing endpoint. */
  onSuggestion: (suggestion: TutorSuggestion) => void;
  /** So the lesson surface can show pinned notes without a second fetch. */
  onTranscriptChange?: (turns: Turn[]) => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [mode, setMode] = useState<TutorMode | null>(null);
  const [offers, setOffers] = useState<TutorSuggestion[]>([]);
  const [remaining, setRemaining] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reveal, setReveal] = useState<string | null>(null);
  const [showEarlier, setShowEarlier] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);

  const publish = useCallback(
    (next: Turn[]) => {
      setTurns(next);
      onTranscriptChange?.(next);
    },
    [onTranscriptChange]
  );

  /** One place every response is absorbed, so no field can be updated in only some. */
  const absorb = useCallback(
    (state: { mode: TutorMode; remaining: number; offers: TutorSuggestion[] }) => {
      setMode(state.mode);
      setRemaining(state.remaining);
      setOffers(state.offers ?? []);
    },
    []
  );

  useEffect(() => {
    let live = true;
    getTutor(sessionId)
      .then((body) => {
        if (!live) return;
        publish(body.turns);
        absorb(body);
      })
      .catch((e) => live && setError(errorTextOr(e.message, t.tutor.failed)));
    return () => {
      live = false;
    };
    // Re-fetched when the STOP changes as well as the session: the mode is a fact
    // about the current node, and a stale one would offer a hint for a question
    // the learner has already left.
  }, [sessionId, nodeId, publish, absorb]);

  // A new turn is the thing to look at. Scrolling the pane, never the page.
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns.length, reveal]);

  const { forThisStop, earlier } = useMemo(() => {
    const here: Turn[] = [];
    const before: Turn[] = [];
    for (const turn of turns) (turn.node_id === nodeId ? here : before).push(turn);
    return { forThisStop: here, earlier: before };
  }, [turns, nodeId]);

  const run = async (call: () => Promise<{
    mode: TutorMode; remaining: number; offers: TutorSuggestion[];
    turn?: Turn | null; failed?: boolean; text?: string;
  }>) => {
    setBusy(true);
    setError(null);
    try {
      const body = await call();
      absorb(body);
      if (body.failed || !body.turn) {
        setError(body.text ?? t.tutor.failed);
        return;
      }
      publish([...turns, body.turn]);
    } catch (e: unknown) {
      setError(errorTextOr(e instanceof Error ? e.message : "", t.tutor.failed));
    } finally {
      setBusy(false);
    }
  };

  const onReveal = async () => {
    setBusy(true);
    setError(null);
    try {
      const body = await tutorReveal(sessionId, nodeId ?? undefined);
      absorb(body);
      setReveal(body.reveal);
    } catch (e: unknown) {
      setError(errorTextOr(e instanceof Error ? e.message : "", t.tutor.failed));
    } finally {
      setBusy(false);
    }
  };

  const onPin = async (turn: Turn) => {
    const next = !turn.pinned;
    // Optimistic: pinning is a note-keeping gesture, and a spinner on it would be
    // heavier than the act. A failure re-reads from the server below.
    publish(turns.map((x) => (x.id === turn.id ? { ...x, pinned: next } : x)));
    try {
      await tutorPin(sessionId, turn.id, next);
    } catch {
      publish(turns.map((x) => (x.id === turn.id ? { ...x, pinned: turn.pinned } : x)));
    }
  };

  const scaffold = mode?.mode === "scaffold";

  return (
    <PaneShell
      prefs={prefs}
      onPrefsChange={onPrefsChange}
      onClose={onClose}
      tourId="tutor-pane"
      label={t.tutor.window}
      closeLabel={t.session.hideChat}
      header={
        <span className="min-w-0 flex-1 truncate font-mono text-micro text-graphite">
          {t.tutor.title}
        </span>
      }
    >
      {/* THE MODE STRIP. The two modes must never be confusable at a glance, so
          they differ in colour as well as in words — and `aria-live` announces
          the switch, because a learner who submits an answer and sees the tutor
          change character must be told rather than left to notice. */}
      {mode && (
        <div
          aria-live="polite"
          className={`shrink-0 border-b px-3.5 py-2 ${
            scaffold ? "border-brass/40 bg-brass/10" : "border-rule bg-slab"
          }`}
        >
          <span
            className={`font-mono text-micro uppercase tracking-[0.14em] ${
              scaffold ? "text-brass" : "text-signal"
            }`}
          >
            {scaffold ? t.tutor.modeScaffold : t.tutor.modeExplain}
          </span>
          <p className="mt-1 text-micro text-graphite">
            {scaffold ? t.tutor.scaffoldBlurb : t.tutor.explainBlurb}
          </p>
        </div>
      )}

      <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto px-3.5 py-3">
        {earlier.length > 0 && (
          <details
            open={showEarlier}
            onToggle={(e) => setShowEarlier((e.currentTarget as HTMLDetailsElement).open)}
            className="mb-3"
          >
            <summary className="cursor-pointer font-mono text-micro text-graphite hover:text-signal">
              {t.tutor.earlier(earlier.length)}
            </summary>
            <ul className="mt-3 flex flex-col gap-4 opacity-70">
              {earlier.map((turn) => (
                <TutorTurn key={turn.id} turn={turn} onCite={onCite} onPin={onPin} stale />
              ))}
            </ul>
          </details>
        )}

        {forThisStop.length === 0 && !reveal ? (
          <p className="text-meta text-graphite">
            {scaffold ? t.tutor.emptyScaffold : t.tutor.empty}
          </p>
        ) : (
          <ul className="flex flex-col gap-4">
            {forThisStop.map((turn) => (
              <TutorTurn key={turn.id} turn={turn} onCite={onCite} onPin={onPin} />
            ))}
          </ul>
        )}

        {reveal && (
          <div className="mt-4">
            <RevealedExplanation text={reveal} />
          </div>
        )}

        {offers.length > 0 && (
          <ul className="mt-4 flex flex-col gap-2">
            {offers.map((offer) => (
              <li key={`${offer.kind}-${offer.node_id ?? ""}`} className="flex flex-col gap-1.5">
                <span className="text-micro text-graphite">
                  {offer.signal === "returning"
                    ? t.tutor.offerReturning
                    : t.tutor.offerDwelling}
                </span>
                <Button variant="chrome" size="sm" onClick={() => onSuggestion(offer)}>
                  {t.tutor.offer[offer.label_key] ?? offer.label_key}
                </Button>
              </li>
            ))}
          </ul>
        )}

        {/* A SUGGESTION IS A CONTROL, NEVER AN ACTION. Nothing happens until the
            learner presses it, and what it posts to is the endpoint that already
            existed. */}
        {forThisStop.at(-1)?.suggestion && (
          <div className="mt-4">
            <Button
              variant="chrome"
              size="sm"
              onClick={() => onSuggestion(forThisStop.at(-1)!.suggestion!)}
            >
              {t.tutor.offer[forThisStop.at(-1)!.suggestion!.label_key] ??
                forThisStop.at(-1)!.suggestion!.label_key}
            </Button>
          </div>
        )}

        {error && (
          <p role="alert" className="mt-3 text-meta text-rust">
            {error}
          </p>
        )}
      </div>

      {/* THE LADDER, and the notice that replaces it.
          
          `revealed` is rendered OUTSIDE the `scaffold` gate on purpose: revealing
          spends the prompt, which makes the server report EXPLAIN — so gating the
          notice on scaffold would hide the one sentence that tells the learner
          what their click just did. They would see the explanation appear and no
          statement that the question is over. */}
      {mode?.revealed && (
        <HintLadder mode={mode} busy={busy} onHint={() => {}} onReveal={() => {}} />
      )}
      {mode && scaffold && !mode.revealed && (
        <HintLadder
          mode={mode}
          busy={busy}
          onHint={() => run(() => tutorHint(sessionId, nodeId ?? undefined))}
          onReveal={onReveal}
        />
      )}

      {remaining <= 0 ? (
        <p className="shrink-0 border-t border-rule px-3.5 py-3 text-meta text-brass">
          {t.tutor.capReached}
        </p>
      ) : (
        <TutorComposer
          scaffold={scaffold}
          disabled={busy}
          busy={busy}
          remaining={remaining}
          onAsk={(question) => run(() => askTutor(sessionId, question, nodeId ?? undefined))}
        />
      )}
    </PaneShell>
  );
}
