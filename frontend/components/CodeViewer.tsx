"use client";

import { useEffect, useRef, useState } from "react";
import { getFile } from "@/lib/api";
import { errorText, t } from "@/lib/strings";

interface Props {
  sessionId: string;
  filePath: string;
  highlightStart?: number;
  highlightEnd?: number;
  onClose: () => void;
}

export default function CodeViewer({
  sessionId, filePath, highlightStart, highlightEnd, onClose,
}: Props) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const firstHotLine = useRef<HTMLTableRowElement | null>(null);

  useEffect(() => {
    setContent(null);
    setError(null);
    getFile(sessionId, filePath)
      .then((f) => setContent(f.content))
      .catch((e) => setError(errorText(e.message)));
  }, [sessionId, filePath]);

  useEffect(() => {
    if (content && firstHotLine.current) {
      firstHotLine.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [content]);

  const lines = content?.split("\n") ?? [];

  return (
    <aside className="flex min-h-0 flex-col bg-trench">
      <div className="flex shrink-0 items-center gap-2.5 border-b border-rule px-3.5 py-2.5">
        <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-graphite">
          {filePath}
        </span>
        {highlightStart != null && (
          <span className="shrink-0 font-mono text-[10px] text-signal-dim">
            {highlightStart}–{highlightEnd}
          </span>
        )}
        <button
          onClick={onClose}
          aria-label={t.session.hideSource}
          className="shrink-0 font-mono text-[11px] text-graphite transition hover:text-signal"
        >
          ✕
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto py-2">
        {error && <p className="px-4 py-3 text-[12px] text-rust">{error}</p>}
        {!content && !error && (
          <p className="px-4 py-3 font-mono text-[11px] text-graphite">
            {t.session.loading}
          </p>
        )}
        {content && (
          <table className="w-full border-collapse font-mono text-[11px] leading-[1.75]">
            <tbody>
              {lines.map((line, i) => {
                const lineNum = i + 1;
                const isHot =
                  highlightStart != null &&
                  highlightEnd != null &&
                  lineNum >= highlightStart &&
                  lineNum <= highlightEnd;
                return (
                  <tr
                    key={i}
                    ref={isHot && lineNum === highlightStart ? firstHotLine : undefined}
                    className={isHot ? "bg-signal/[0.07]" : undefined}
                    style={isHot && lineNum === highlightStart
                      ? { boxShadow: "inset 2px 0 0 var(--color-signal)" }
                      : undefined}
                  >
                    <td
                      className={`w-10 select-none border-r border-rule py-0 pr-2.5 text-right tabular-nums ${
                        isHot ? "text-signal-dim" : "text-[#3e4e58]"
                      }`}
                    >
                      {lineNum}
                    </td>
                    <td
                      className={`whitespace-pre py-0 pl-3 pr-4 ${
                        isHot ? "text-[#c8d5dd]" : "text-[#8fa0ac]"
                      }`}
                    >
                      {line || " "}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </aside>
  );
}
