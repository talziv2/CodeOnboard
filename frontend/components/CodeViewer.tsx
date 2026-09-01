"use client";

import { useEffect, useState } from "react";
import CodeLines from "@/components/CodeLines";
import PaneShell from "@/components/panel/PaneShell";
import { getFile } from "@/lib/api";
import { type PanePrefs } from "@/lib/prefs";
import { errorText, t } from "@/lib/strings";

interface Props {
  sessionId: string;
  filePath: string;
  highlightStart?: number;
  highlightEnd?: number;
  /** Bumped on every request for a location, so repeats still scroll. */
  focusKey: number;
  source: PanePrefs;
  onSourceChange: (change: Partial<PanePrefs>) => void;
  onClose: () => void;
}

/**
 * The repository's source, beside the lesson.
 *
 * THE PANE ITSELF IS NO LONGER HERE. `FloatShell`, `DockDivider` and the mode
 * switch moved to `components/panel/PaneShell.tsx` when the Tutor needed the same
 * behaviour — see that file for why they were shared rather than copied. What is
 * left in this component is what was always specific to source: which file, which
 * range, and how to render it.
 *
 * The extraction was behaviour-preserving, and `CodeViewer.test.tsx` is the
 * evidence: it asserts the two modes, the divider, the eight resize grips and the
 * header drag, and it passes unchanged.
 */
export default function CodeViewer({
  sessionId, filePath, highlightStart, highlightEnd, focusKey,
  source, onSourceChange, onClose,
}: Props) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setContent(null);
    setError(null);
    getFile(sessionId, filePath)
      // Line numbers and the highlight band are counted in "\n"s, so CRLF files
      // must not leave a stray carriage return at the end of every line.
      .then((f) => setContent(f.content.replace(/\r\n/g, "\n")))
      .catch((e) => setError(errorText(e.message)));
  }, [sessionId, filePath]);

  const body =
    error != null ? (
      <p className="px-4 py-3 text-meta text-rust">{error}</p>
    ) : content == null ? (
      <p className="px-4 py-3 font-mono text-micro text-graphite">
        {t.session.loading}
      </p>
    ) : (
      <CodeLines
        code={content}
        path={filePath}
        highlightStart={highlightStart}
        highlightEnd={highlightEnd}
        focusKey={focusKey}
      />
    );

  return (
    <PaneShell
      prefs={source}
      onPrefsChange={onSourceChange}
      onClose={onClose}
      tourId="source-pane"
      label={t.source.window}
      closeLabel={t.session.hideSource}
      header={
        <>
          <span className="min-w-0 flex-1 truncate font-mono text-micro text-graphite">
            {filePath}
          </span>
          {/* `signal`, not `signal-dim`, which measured 3.84:1 on trench. This is
              the band under discussion — "you are here" — so the full accent is
              also the semantically correct one of the two. */}
          {highlightStart != null && (
            <span className="shrink-0 font-mono text-micro text-signal">
              {highlightStart}–{highlightEnd}
            </span>
          )}
        </>
      }
    >
      {body}
    </PaneShell>
  );
}
