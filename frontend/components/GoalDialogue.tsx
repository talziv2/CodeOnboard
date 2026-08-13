"use client";

import { useState, useEffect } from "react";
import { goalStart, goalAnswer } from "@/lib/api";
import type { Question } from "@/lib/api";
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

  if (loading && !question) {
    return (
      <p className="animate-pulse font-mono text-sm text-graphite">{t.goal.starting}</p>
    );
  }

  if (!question) {
    return error ? <p className="text-sm text-rust">{error}</p> : null;
  }

  const ticks = Math.max(question.total, question.index);

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
        <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-graphite">
          {t.goal.progress(question.index, ticks)}
        </span>
      </div>

      <h2 className="font-display text-[22px] font-medium leading-[1.25] tracking-tight text-chalk text-balance">
        {question.text}
      </h2>

      {question.options && (
        <div className="flex flex-wrap gap-2">
          {question.options.map((opt) => (
            <button
              key={opt}
              onClick={() => setAnswer(opt)}
              className={`rounded border px-3 py-1.5 text-[13px] transition ${
                answer === opt
                  ? "border-signal-dim bg-signal/15 text-signal"
                  : "border-rule text-graphite hover:border-signal-dim hover:text-chalk"
              }`}
            >
              {opt}
            </button>
          ))}
        </div>
      )}

      <textarea
        className="w-full resize-none rounded border border-rule bg-trench p-3 text-start text-[13.5px] text-chalk placeholder:text-graphite focus:border-signal-dim focus:outline-none"
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
      />

      {error && <p className="text-sm text-rust">{error}</p>}

      <div className="flex items-center gap-3">
        <button
          onClick={submit}
          disabled={loading || !answer.trim()}
          className="rounded border border-signal-dim bg-signal/15 px-5 py-2 text-[13px] font-medium text-signal transition hover:bg-signal/25 disabled:opacity-40"
        >
          {loading ? t.goal.thinking : t.goal.continue}
        </button>
        <span className="font-mono text-[10.5px] text-graphite">{t.goal.enterHint}</span>
      </div>
    </div>
  );
}
