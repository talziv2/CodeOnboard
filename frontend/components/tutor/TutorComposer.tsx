"use client";

import { useState } from "react";
import Button from "@/components/ui/Button";
import { t } from "@/lib/strings";

/**
 * Where a question is typed. **Not where an answer is.**
 *
 * ── THE SINGLE-COMPOSER INVARIANT (D2) ────────────────────────────────────────
 *
 * `AnswerComposer` and `VerificationBlock` bind the same `answer` state in the
 * lesson panel, and rendering both put two mirrored textareas on screen under two
 * buttons both labelled "Submit". That was D2, and this component puts a THIRD
 * textarea on screen — so every mitigation below is load-bearing rather than
 * decorative:
 *
 *   - it lives in a SEPARATE COLUMN with its own heading, never inline in the
 *     lesson body;
 *   - it binds its OWN state. Nothing here mirrors the answer, which is why the
 *     state is local rather than lifted;
 *   - the button says **Ask**, never Submit. That word belongs to answers;
 *   - it is NEVER auto-focused — opening the pane does not move focus out of the
 *     lesson;
 *   - `⌘↵` here asks. It never submits an answer, and the two shortcuts never
 *     coexist in one focus scope because the two composers are in different
 *     columns.
 *
 * It is also deliberately quieter than the answer composer: smaller type, a muted
 * border, and a `secondary` button rather than a `primary` one. The lesson is the
 * primary workspace; this is a tool beside it.
 */
export default function TutorComposer({
  scaffold,
  disabled,
  busy,
  remaining,
  onAsk,
}: {
  /** Changes only the placeholder — the two modes are one composer. */
  scaffold: boolean;
  disabled: boolean;
  busy: boolean;
  remaining: number;
  onAsk: (question: string) => void;
}) {
  const [question, setQuestion] = useState("");

  const submit = () => {
    const trimmed = question.trim();
    if (!trimmed || disabled || busy) return;
    onAsk(trimmed);
    setQuestion("");
  };

  return (
    <div className="flex shrink-0 flex-col gap-2 border-t border-rule px-3.5 py-3">
      <textarea
        rows={3}
        // NO autoFocus. Opening the tutor is not a request to stop reading.
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            submit();
          }
        }}
        disabled={disabled || busy}
        aria-label={scaffold ? t.tutor.placeholderScaffold : t.tutor.placeholderExplain}
        placeholder={scaffold ? t.tutor.placeholderScaffold : t.tutor.placeholderExplain}
        className="w-full resize-none rounded-field border border-rule bg-slab p-2.5 text-start text-meta text-chalk placeholder:text-muted focus:border-signal-dim disabled:opacity-60"
      />
      <div className="flex items-center gap-2.5">
        <Button
          variant="secondary"
          size="sm"
          onClick={submit}
          disabled={disabled || busy || !question.trim()}
        >
          {busy ? t.tutor.asking : t.tutor.ask}
        </Button>
        <span className="font-mono text-micro text-muted">{t.tutor.askHint}</span>
        <span className="ms-auto font-mono text-micro text-graphite">
          {t.tutor.remaining(remaining)}
        </span>
      </div>
    </div>
  );
}
