"use client";

import { useState, useEffect } from "react";
import { goalStart, goalAnswer, goalBack } from "@/lib/api";
import type { Question } from "@/lib/api";
import Button from "@/components/ui/Button";
import { errorText, t } from "@/lib/strings";

interface Props {
  repoUrl: string;
  onDone: (sessionId: string, goal: Record<string, string>) => void;
}

export default function GoalDialogue({ repoUrl, onDone }: Props) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [question, setQuestion] = useState<Question | null>(null);
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setQuestion(null);
      setAnswer("");
      try {
        const res = await goalStart(repoUrl);
        setSessionId(res.session_id);
        setQuestion(res.question);
      } catch (e: unknown) {
        setError(e instanceof Error ? errorText(e.message) : t.home.serverUnreachable);
      } finally {
        setLoading(false);
      }
    })();
  }, [repoUrl]);

  const submit = async () => {
    if (!sessionId || !answer.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await goalAnswer(sessionId, answer);
      setAnswer("");
      if (res.done && res.goal) onDone(sessionId, res.goal);
      else if (res.question) setQuestion(res.question);
    } catch (e: unknown) {
      setError(e instanceof Error ? errorText(e.message) : t.goal.answerFailed);
    } finally {
      setLoading(false);
    }
  };

  // The backend un-answers the last question and hands it back with what was
  // said, so the previous answer is restored rather than re-typed. It also owns
  // the consequences — going back past Q2 clears the goal_type that decides
  // which follow-ups come later.
  const back = async () => {
    if (!sessionId || loading || !question || question.index <= 1) return;
    setLoading(true);
    setError(null);
    try {
      const res = await goalBack(sessionId);
      setQuestion(res.question);
      setAnswer(res.answer);
    } catch (e: unknown) {
      setError(e instanceof Error ? errorText(e.message) : t.goal.backFailed);
    } finally {
      setLoading(false);
    }
  };

  if (loading && !question) {
    return (
      <p className="animate-pulse font-mono text-aside text-graphite">{t.goal.starting}</p>
    );
  }

  if (!question) {
    return error ? <p className="text-aside text-rust">{error}</p> : null;
  }

  const ticks = Math.max(question.total, question.index);
  const answered = answer.trim().length > 0;
  const atStart = question.index <= 1;

  return (
    <div className="flex w-full max-w-xl flex-col gap-5">
      <div className="flex flex-col gap-2">
        <div className="flex gap-1" role="presentation">
          {Array.from({ length: ticks }, (_, i) => (
            <span
              key={i}
              className={`h-0.5 flex-1 rounded-full transition-colors ${
                i < question.index ? "bg-signal" : "bg-rule"
              }`}
            />
          ))}
        </div>
        <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
          {t.goal.progress(question.index, ticks)}
        </span>
      </div>

      <h2 className="font-display text-head font-medium tracking-tight text-chalk text-balance">
        {question.text}
      </h2>

      {question.options ? (
        /* A fixed vocabulary: the backend rejects anything outside it, and
           `familiarity` is matched against the same strings downstream. So the
           options are the whole input — no free-text box beside them to type an
           answer that can only be refused. */
        <div className="flex flex-wrap gap-2">
          {question.options.map((opt) => (
            <button
              key={opt}
              onClick={() => setAnswer(opt)}
              disabled={loading}
              className={`rounded border px-3 py-1.5 text-start text-aside transition ${
                answer === opt
                  ? "border-signal-dim bg-signal/15 text-signal"
                  : "border-rule text-graphite hover:border-signal-dim hover:text-chalk"
              }`}
            >
              {opt}
            </button>
          ))}
        </div>
      ) : (
        <textarea
          className="w-full resize-none rounded border border-rule bg-trench p-3 text-start text-aside text-chalk placeholder:text-graphite focus:border-signal-dim"
          rows={3}
          placeholder={t.goal.answerPlaceholder}
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          disabled={loading}
          autoFocus
        />
      )}

      {error && <p className="text-aside text-rust">{error}</p>}

      <div className="flex items-center gap-3">
        {/* Absent on the first question rather than present-and-disabled. There
            is nowhere to go back TO, and a control that occupies space to say so
            is worse than no control — it was the starkest case of the old
            opacity-based disabled state, rendering at roughly 1.5:1. */}
        {!atStart && (
          <Button variant="secondary" size="md"
            onClick={back}
            disabled={loading}
          >
            {t.goal.back}
          </Button>
        )}
        <Button variant="primary" size="lg"
          onClick={submit}
          disabled={loading || !answered}
         
        >
          {loading ? t.goal.thinking : t.goal.continue}
        </Button>
        {/* Says why Continue is dead rather than leaving the user to guess.
            The ↵ hint belongs only to the free-text box that honours it. */}
        <span className="font-mono text-micro text-graphite">
          {!answered
            ? t.goal.answerRequired
            : question.options
              ? ""
              : t.goal.enterHint}
        </span>
      </div>
    </div>
  );
}
