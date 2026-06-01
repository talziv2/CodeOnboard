"use client";

import { useEffect, useState, useRef } from "react";
import { getFile } from "@/lib/api";

interface Props {
  sessionId: string;
  filePath: string;
  highlightStart?: number;
  highlightEnd?: number;
  onClose: () => void;
}

export default function CodeViewer({ sessionId, filePath, highlightStart, highlightEnd, onClose }: Props) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const highlightRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setContent(null);
    setError(null);
    getFile(sessionId, filePath)
      .then((f) => setContent(f.content))
      .catch((e) => setError(e.message));
  }, [sessionId, filePath]);

  useEffect(() => {
    if (content && highlightRef.current) {
      highlightRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [content]);

  const lines = content?.split("\n") ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#0f172a", borderRadius: 12, border: "1px solid #1e293b", overflow: "hidden" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 16px", borderBottom: "1px solid #1e293b", background: "#0f172a", flexShrink: 0 }}>
        <button
          onClick={onClose}
          style={{ fontSize: 13, color: "#818cf8", background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}
        >
          ← Graph
        </button>
        <span style={{ flex: 1, fontSize: 12, fontFamily: "monospace", color: "#94a3b8", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {filePath}
        </span>
        {highlightStart != null && (
          <span style={{ fontSize: 11, color: "#64748b" }}>lines {highlightStart}–{highlightEnd}</span>
        )}
      </div>

      {/* Code */}
      <div style={{ flex: 1, overflowY: "auto", padding: "12px 0" }}>
        {error && <p style={{ color: "#f87171", padding: "16px" }}>{error}</p>}
        {!content && !error && (
          <p style={{ color: "#64748b", padding: "16px", fontFamily: "monospace" }}>Loading…</p>
        )}
        {content && (
          <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "monospace", fontSize: 13, lineHeight: 1.6 }}>
            <tbody>
              {lines.map((line, i) => {
                const lineNum = i + 1;
                const isHighlighted = highlightStart != null && highlightEnd != null
                  && lineNum >= highlightStart && lineNum <= highlightEnd;
                return (
                  <tr
                    key={i}
                    ref={isHighlighted && lineNum === highlightStart ? (el) => { if (el) highlightRef.current = el as unknown as HTMLDivElement; } : undefined}
                    style={{ background: isHighlighted ? "#1e1b4b" : "transparent" }}
                  >
                    <td style={{ padding: "0 16px 0 12px", color: "#475569", textAlign: "right", userSelect: "none", minWidth: 48, borderRight: "1px solid #1e293b" }}>
                      {lineNum}
                    </td>
                    <td style={{ padding: "0 16px", color: isHighlighted ? "#e2e8f0" : "#94a3b8", whiteSpace: "pre" }}>
                      {line || " "}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
