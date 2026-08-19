"use client";

import { useState, useEffect, useRef } from "react";
import { goalStart, goalAnswer, goalBack } from "@/lib/api";
import type { Question } from "@/lib/api";
import { type TranscriptEntry } from "@/components/goal/AnswerTranscript";
import OptionList from "@/components/goal/OptionList";
import ReviewStep from "@/components/goal/ReviewStep";
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
 * ANSWERS ACCUMULATE LOCALLY, AND ARE SHOWN ONLY AT THE END. `history` is built as
 * the user goes and truncated when they step back, but it is rendered on the review
 * step alone — a transcript beside a live question turned every question into a
 * re-read of everything already said. The backend has no transcript concept, and
 * adding one would be a schema change to display something the client already knows.
 *
 * THE LAST ANSWER DOES NOT START ANYTHING. When the backend returns the synthesised
 * goal it is held on `review` and the answers are shown back for confirmation;
 * `onDone` fires only when the user starts the session. Everything downstream is
 * decided by these answers, and the next thing that happens is a multi-minute
 * pipeline run, so a wrong answer is expensive to discover later. Note the cost of
 * reopening from here: re-confirming the last question synthesises the goal again,
 * which is one more Haiku call.
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
  /**
   * What has been typed or chosen for each question, whether or not it was
   * confirmed, keyed on the question's own text.
   *
   * Without this, choosing an option and then stepping back lost the choice: it
   * lived only in `answer`, the server was never told about it, and coming forward
   * again cleared it. The user had made a decision and the interview forgot it,
   * which is the opposite of the promise the transcript makes.
   *
   * Keyed on the TEXT rather than the index, because index 6 is a different
   * question depending on the goal type. Changing the goal type on the way back
   * must not drop the previous follow-up's answer into the new follow-up, which
   * would put words in the user's mouth.
   *
   * A ref, not state: nothing renders from it directly, and reading it inside an
   * async submit or a multi-step `jumpTo` must not see a stale closure.
   */
  const drafts = useRef<Record<string, string>>({});
  /** Set when every question is answered: the goal, plus the answers to show back. */
  const [review, setReview] = useState<{
    goal: Record<string, string>;
    entries: TranscriptEntry[];
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /**
   * Set when the server no longer has the goal dialogue. From the review step that
   * costs editing but not starting, so it is tracked rather than treated as fatal.
   */
  const [dialogueLost, setDialogueLost] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setQuestion(null);
      setAnswer("");
      setHistory([]);
      setReview(null);
      setDialogueLost(false);
      drafts.current = {};
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

  /** Record the answer as well as showing it, so stepping away cannot lose it. */
  const choose = (value: string) => {
    if (question) drafts.current[question.text] = value;
    setAnswer(value);
  };

  const submit = async () => {
    if (!sessionId || !answer.trim() || loading || !question) return;
    setLoading(true);
    setError(null);
    try {
      const res = await goalAnswer(sessionId, answer);
      // Recorded only once the backend has accepted it — the vocabulary check
      // lives there, so an out-of-vocabulary answer must not appear in the
      // transcript as though it had been taken.
      const entries = [
        ...history,
        { index: question.index, question: question.text, answer },
      ];
      setHistory(entries);
      if (res.done && res.goal) {
        // Built from `entries` rather than read back from state, which has not
        // committed yet — the review must show the answer just given.
        setReview({ goal: res.goal, entries });
        setAnswer("");
      } else if (res.question) {
        setQuestion(res.question);
        // Whatever was already chosen for THIS question, if the user has seen it
        // before and stepped away from it.
        setAnswer(drafts.current[res.question.text] ?? "");
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? errorText(e.message) : t.goal.answerFailed);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Reopen question `target`, one `goalBack` call at a time.
   *
   * Sequential and not parallel on purpose: each call un-answers exactly one
   * question, and the server's position is what decides where the next one lands.
   *
   * The call count is derived from how many answers the SERVER is holding, which
   * differs by where we are. Mid-interview the current question is unanswered, so
   * that is `index - 1`; on the review step every question is answered, so it is
   * `index`. Reopening the last question from the review is therefore one call, and
   * reopening question 1 from a six-question review is six — whereas mid-interview
   * at question 4 it is three, which is the case verified by hand.
   */
  const reopen = async (target: number) => {
    if (!sessionId || loading || !question || target < 1) return;
    const answered = review ? question.index : question.index - 1;
    const steps = answered - target + 1;
    if (steps < 1) return;
    setLoading(true);
    setError(null);
    let current = question;
    let restored = "";
    let done = 0;
    try {
      for (; done < steps; done++) {
        const res = await goalBack(sessionId);
        current = res.question;
        restored = res.answer;
      }
    } catch (e: unknown) {
      // `session_not_found` is not a failed request, it is a vanished interview:
      // the dialogue lives in memory on the server, so a restart or the retention
      // cap can take it while this page is still open. What to say depends on
      // where we are — on the review step the goal is already in hand.
      const gone = e instanceof Error && e.message === "session_not_found";
      if (gone) setDialogueLost(true);
      setError(
        gone
          ? review
            ? t.goal.editExpired
            : t.goal.sessionExpired
          : e instanceof Error
            ? errorText(e.message)
            : t.goal.backFailed,
      );
    } finally {
      // Committed in `finally` because partial progress is still real: if the third
      // call of three fails, two questions are already un-answered on the server,
      // and leaving the client showing the old position would describe a state the
      // server has left. `done` is how far it actually got.
      setQuestion(current);
      // The server's committed answer wins; the draft covers a question it has no
      // answer for, which is any question reached going forward again.
      setAnswer(restored || drafts.current[current.text] || "");
      setHistory((prev) => prev.slice(0, Math.max(0, current.index - 1)));
      // Leaving the review even on a partial failure: the server has un-answered
      // something, so the goal it handed us no longer describes the session.
      if (done > 0) setReview(null);
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

  if (review) {
    return (
      <div className="flex w-full max-w-xl flex-col gap-4">
        <ReviewStep
          entries={review.entries}
          onEdit={reopen}
          onBack={() => reopen(question.index)}
          onStart={() => onDone(sessionId!, review.goal)}
          busy={loading}
          editable={!dialogueLost}
        />
        {error && <p className="text-aside text-rust">{error}</p>}
      </div>
    );
  }

  const total = Math.max(question.total, question.index);
  const answered = answer.trim().length > 0;
  const atStart = question.index <= 1;

  return (
    <div className="flex w-full max-w-xl flex-col gap-7">
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
            onSelect={choose}
            onConfirm={submit}
            disabled={loading}
          />
        ) : (
          <textarea
            className="w-full resize-none rounded-field border border-rule bg-trench p-3 text-start text-aside text-chalk placeholder:text-graphite focus:border-signal-dim"
            rows={3}
            placeholder={t.goal.answerPlaceholder}
            value={answer}
            onChange={(e) => choose(e.target.value)}
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
            <Button variant="ghost" onClick={() => reopen(question.index - 1)} disabled={loading}>
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
