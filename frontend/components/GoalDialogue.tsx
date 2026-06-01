"use client";

import { useState, useEffect } from "react";
import { goalStart, goalAnswer } from "@/lib/api";
import type { Question } from "@/lib/api";

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
      try {
        const res = await goalStart(repoUrl);
        setSessionId(res.session_id);
        setQuestion(res.question);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Failed to start goal dialogue");
      } finally {
        setLoading(false);
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async () => {
    if (!sessionId || !answer.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await goalAnswer(sessionId, answer);
      setAnswer("");
      if (res.done && res.goal) {
        onDone(sessionId, res.goal);
      } else if (res.question) {
        setQuestion(res.question);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  if (loading && !question) {
    return <p className="text-gray-400 animate-pulse">Starting goal dialogue…</p>;
  }

  return (
    <div className="flex flex-col gap-4 w-full max-w-xl">
      {question && (
        <div>
          <p className="text-lg text-white font-medium">{question.text}</p>
          {question.options && (
            <div className="flex flex-wrap gap-2 mt-3">
              {question.options.map((opt) => (
                <button
                  key={opt}
                  onClick={() => setAnswer(opt)}
                  className={`px-3 py-1.5 rounded-lg text-sm border transition ${
                    answer === opt
                      ? "bg-indigo-600 border-indigo-600 text-white"
                      : "border-gray-600 text-gray-300 hover:border-indigo-500"
                  }`}
                >
                  {opt}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      <textarea
        className="w-full rounded-lg bg-gray-800 border border-gray-600 text-white p-3 resize-none focus:outline-none focus:border-indigo-500"
        rows={3}
        placeholder="Your answer…"
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
      {error && <p className="text-red-400 text-sm">{error}</p>}
      <button
        onClick={submit}
        disabled={loading || !answer.trim()}
        className="self-end px-6 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white font-medium transition"
      >
        {loading ? "Thinking…" : "Answer"}
      </button>
    </div>
  );
}
