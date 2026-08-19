"use client";

import { useState, useEffect } from "react";
import { goalStart, goalAnswer, goalBack } from "@/lib/api";
import type { Question } from "@/lib/api";
import AnswerTranscript, { type TranscriptEntry } from "@/components/goal/AnswerTranscript";
import OptionList from "@/components/goal/OptionList";
import Button from "@/components/ui/Button";
import { errorText, t } from "@/lib/strings";

interface Props {
  repoUrl: string;
  onDone: (sessionId: string, goal: Record<string, string>) => void;
}

/**
 * The goal interview: one question at a time, with everything already answered
 * still on screen.
 *
 * Three things are deliberate here.
 *
 * ANSWERS ACCUMULATE LOCALLY. `history` is built as the user goes and truncated
 * when they step back. The backend has no transcript concept, and adding one
 * would be a schema change to display something the client already knows.
 *
 * `goalBack` STAYS THE ONLY WAY BACKWARDS, including for the transcript's Change
 * control on an answer four questions ago — that is a loop over the same call,
 * not a new endpoint. It matters because the backend owns the consequence:
 * crossing question 2 clears `goal_type`, which is what makes the follow-up
 * questions recompute. A client that jumped straight to question 2 would leave
 * the server believing in a goal type the user had abandoned, and the interview
 * would finish with answers to questions that no longer applied.
 *
 * `total` IS A LOWER BOUND, not a target, and is documented as such on the wire:
 * five core questions plus one follow-up, or two for `improve_existing_system`
 * and `debug_issue`. So "Question 3 of 6" can honestly become "of 7" after
 * question 2 is answered, and the progress text is read from the response every
 * time rather than cached.
 */
export default function GoalDialogue({ repoUrl, onDone }: Props) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [question, setQuestion] = useState<Question | null>(null);
  const [answer, setAnswer] = useState("");
  const [history, setHistory] = useState<TranscriptEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setQuestion(null);
      setAnswer("");
      setHistory([]);
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
    if (!sessionId || !answer.trim() || loading || !question) return;
    setLoading(true);
    setError(null);
    try {
      const res = await goalAnswer(sessionId, answer);
      // Recorded only once the backend has accepted it — the vocabulary check
      // lives there, so an out-of-vocabulary answer must not appear in the
      // transcript as though it had been taken.
      setHistory((prev) => [
        ...prev,
        { index: question.index, question: question.text, answer },
      ]);
      setAnswer("");
      if (res.done && res.goal) onDone(sessionId, res.goal);
      else if (res.question) setQuestion(res.question);
    } catch (e: unknown) {
      setError(e instanceof Error ? errorText(e.message) : t.goal.answerFailed);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Step back to a specific question, one `goalBack` call at a time.
   *
   * Sequential and not parallel on purpose: each call un-answers exactly one
   * question, and the server's position is what decides where the next one lands.
   */
  const jumpTo = async (target: number) => {
    if (!sessionId || loading || !question || target < 1 || target >= question.index) return;
    setLoading(true);
    setError(null);
    let current = question;
    let restored = "";
    let trail = history;
    try {
      while (current.index > target) {
        const res = await goalBack(sessionId);
        current = res.question;
        restored = res.answer;
        trail = trail.slice(0, -1);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? errorText(e.message) : t.goal.backFailed);
    } finally {
      // Committed in `finally` because partial progress is still real: if the
      // third call of three fails, two questions are already un-answered on the
      // server, and leaving the client showing the old position would describe a
      // state the server has left.
      setQuestion(current);
      setAnswer(restored);
      setHistory(trail);
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

  const total = Math.max(question.total, question.index);
  const answered = answer.trim().length > 0;
  const atStart = question.index <= 1;

  return (
    <div className="flex w-full max-w-xl flex-col gap-7">
      {history.length > 0 && (
        <section className="flex flex-col gap-3">
          <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
            {t.goal.answers}
          </span>
          <AnswerTranscript entries={history} onEdit={jumpTo} disabled={loading} />
        </section>
      )}

      {/* Keyed on the question so React remounts the block: that is what replays
          `rise` on every move, forwards or back, and what re-lands focus on the
          new answer control. The tick bar this replaced said the same thing as
          "Question 3 of 6", while the transcript above now says it more usefully —
          it shows what the answers WERE, not just how many there are. */}
      <div key={question.index} className="rise flex flex-col gap-5">
        <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
          {t.goal.progress(question.index, total)}
        </span>

        <h2 className="font-display text-head font-medium tracking-tight text-chalk text-balance">
          {question.text}
        </h2>

        {question.options ? (
          <OptionList
            options={question.options}
            value={answer}
            onSelect={setAnswer}
            onConfirm={submit}
            disabled={loading}
          />
        ) : (
          <textarea
            className="w-full resize-none rounded-field border border-rule bg-trench p-3 text-start text-aside text-chalk placeholder:text-graphite focus:border-signal-dim"
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
              opacity-based disabled state, rendering at roughly 1.5:1.

              Tertiary now rather than an outline: the transcript's Change control
              is the specific way back and this is the general one, so it should
              not hold the same weight as Continue. */}
          {!atStart && (
            <Button variant="ghost" onClick={() => jumpTo(question.index - 1)} disabled={loading}>
              {t.goal.back}
            </Button>
          )}
          <Button variant="primary" size="lg" onClick={submit} disabled={loading || !answered}>
            {loading ? t.goal.thinking : t.goal.continue}
          </Button>
          {/* Says why Continue is dead rather than leaving the user to guess, then
              which keys work once it is live. The two hints differ because the two
              controls do: the options list separates choosing from confirming and
              the text box does not. */}
          <span className="font-mono text-micro text-graphite">
            {!answered
              ? t.goal.answerRequired
              : question.options
                ? t.goal.optionHint
                : t.goal.enterHint}
          </span>
        </div>
      </div>
    </div>
  );
}
