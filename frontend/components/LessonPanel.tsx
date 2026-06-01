"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { getLesson, respond, advance } from "@/lib/api";
import type { Lesson, RespondResult } from "@/lib/api";

interface Props {
  sessionId: string;
  nodeId: string;
  nodeTitle: string;
  nodeFile?: string;
  lineStart?: number;
  lineEnd?: number;
  onFileClick: (file: string) => void;
  onAdvance: () => Promise<void>;
  onFinish: () => void;
}

const classificationColor: Record<string, string> = {
  understood: "text-green-400",
  partial: "text-amber-400",
  confused: "text-red-400",
  "off-topic": "text-red-400",
};

export default function LessonPanel({ sessionId, nodeId, nodeTitle, nodeFile, lineStart, lineEnd, onFileClick, onAdvance, onFinish }: Props) {
  const router = useRouter();
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<RespondResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    setLesson(null);
    setResult(null);
    setAnswer("");
    setError(null);
    setLoading(true);
    getLesson(sessionId)
      .then(setLesson)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [sessionId, nodeId]);

  const submitAnswer = async () => {
    if (!answer.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await respond(sessionId, answer, nodeId);
      setResult(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  const handleAdvance = async () => {
    setLoading(true);
    try {
      const res = await advance(sessionId, "next", nodeId) as { done?: boolean };
      await onAdvance(); // always reload graph so last node turns green
      if (res?.done) {
        setDone(true);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  if (done) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-6 text-center">
        <div className="text-5xl">🎉</div>
        <h2 className="text-2xl font-bold text-white">You finished!</h2>
        <p className="text-gray-400 max-w-xs">You've completed all the nodes in this learning path. Great work.</p>
        <button
          onClick={() => router.push("/")}
          className="px-6 py-3 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition"
        >
          Start a new session
        </button>
      </div>
    );
  }

  if (loading && !lesson) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 animate-pulse">
        Loading lesson…
      </div>
    );
  }

  if (error && !lesson) {
    return <div className="text-red-400 p-4">{error}</div>;
  }

  if (!lesson) return null;

  return (
    <div className="flex flex-col gap-5 overflow-y-auto pr-1">
      <div className="flex flex-col gap-1">
        <h2 className="text-xl font-bold text-white">{nodeTitle}</h2>
        {nodeFile && (
          <button
            onClick={() => onFileClick(nodeFile)}
            className="text-xs font-mono text-indigo-400 hover:text-indigo-300 text-left underline underline-offset-2 transition"
          >
            {nodeFile}{lineStart != null ? ` · lines ${lineStart}–${lineEnd}` : ""}
          </button>
        )}
      </div>

      <div>
        <h3 className="text-xs uppercase tracking-widest text-gray-400 mb-2">Walkthrough</h3>
        <p className="text-gray-200 text-sm leading-relaxed whitespace-pre-wrap">
          {lesson.lesson.walkthrough}
        </p>
      </div>

      {!result && (
        <div className="flex flex-col gap-3">
          <h3 className="text-xs uppercase tracking-widest text-gray-400">Check your understanding</h3>
          <p className="text-gray-200 text-sm">{lesson.lesson.prompt}</p>
          <textarea
            rows={4}
            className="w-full rounded-lg bg-gray-800 border border-gray-600 text-white p-3 resize-none focus:outline-none focus:border-indigo-500 text-sm"
            placeholder="Write your answer…"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            disabled={loading}
          />
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button
            onClick={submitAnswer}
            disabled={loading || !answer.trim()}
            className="self-end px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-sm font-medium transition"
          >
            {loading ? "Grading…" : "Submit"}
          </button>
        </div>
      )}

      {result && (
        <div className="flex flex-col gap-3 bg-gray-800 rounded-xl p-4 border border-gray-700">
          <p className={`font-bold capitalize ${classificationColor[result.classification] ?? "text-white"}`}>
            {result.classification}
          </p>
          <p className="text-gray-300 text-sm leading-relaxed">{result.rationale}</p>

          {result.classification === "understood" ? (
            <button
              onClick={handleAdvance}
              disabled={loading}
              className="self-end px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-sm font-medium transition"
            >
              {loading ? "Loading…" : "Next →"}
            </button>
          ) : (
            <div className="flex items-center gap-3 self-end">
              <p className="text-amber-400 text-xs">Try again or skip</p>
              <button
                onClick={() => { setResult(null); setAnswer(""); onAdvance(); }}
                className="px-4 py-2 rounded-lg border border-gray-600 text-gray-300 hover:text-white text-sm transition"
              >
                Try again
              </button>
              <button
                onClick={handleAdvance}
                disabled={loading}
                className="px-4 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 disabled:opacity-40 text-gray-300 text-sm transition"
              >
                {loading ? "Loading…" : "Skip anyway →"}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Always-visible finish button */}
      <div className="border-t border-gray-800 pt-4 mt-2">
        <button
          onClick={onFinish}
          className="text-xs text-gray-500 hover:text-gray-300 transition"
        >
          Finish session early
        </button>
      </div>
    </div>
  );
}
