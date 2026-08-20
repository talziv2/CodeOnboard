"use client";

import { memo, useEffect, useRef, useState } from "react";
import { MAX_HIGHLIGHT_LINES, langForPath, tokenize, type CodeToken } from "@/lib/highlight";

interface Props {
  code: string;
  path: string;
  highlightStart?: number;
  highlightEnd?: number;
  /**
   * Bumped by the session page every time the learner asks for a location —
   * including when they ask for the *same* one again. Without it, re-opening a
   * range already on screen changes no prop and the pane sits where it was.
   */
  focusKey: number;
}

/**
 * The scrolling body of the source pane: the code itself.
 *
 * Split out and memoised because the pane around it is draggable and
 * resizable. Those gestures must not re-render a thousand table rows, and this
 * component's props don't change while one is in flight.
 */
function CodeLines({ code, path, highlightStart, highlightEnd, focusKey }: Props) {
  const scroller = useRef<HTMLDivElement>(null);
  const firstHot = useRef<HTMLTableRowElement>(null);
  const [tokens, setTokens] = useState<CodeToken[][] | null>(null);

  const lines = code.split("\n");

  // Colour arrives after the code does, never instead of it: the plain text is
  // rendered immediately and repaints when the grammar has loaded. A failure
  // here leaves exactly the uncoloured pane this replaced.
  useEffect(() => {
    setTokens(null);
    const lang = langForPath(path);
    if (!lang || lines.length > MAX_HIGHLIGHT_LINES) return;

    let alive = true;
    tokenize(code, lang)
      .then((t) => alive && setTokens(t))
      .catch(() => {});
    return () => {
      alive = false;
    };
    // `lines` is derived from `code`; re-splitting is not a reason to re-tokenise.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, path]);

  // Put the anchored lines a third of the way down rather than at the very top:
  // the code above a definition is usually what makes it readable.
  //
  // Animated only for a short hop, where the movement tells the reader the pane
  // stayed in the same neighbourhood. Crossing a thousand lines is not a
  // movement worth watching — it's a jump — and sliding through the whole file
  // to get there is slower and harder to follow than simply arriving.
  useEffect(() => {
    const box = scroller.current;
    if (!box) return;
    const row = firstHot.current;
    const top = row ? Math.max(0, row.offsetTop - box.clientHeight / 3) : 0;
    const near = Math.abs(top - box.scrollTop) < box.clientHeight * 1.5;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    box.scrollTo({ top, behavior: near && !still ? "smooth" : "auto" });
  }, [code, highlightStart, highlightEnd, focusKey]);

  return (
    <div
      ref={scroller}
      // Positioned so `offsetTop` above is measured against this box and not
      // against the document.
      className="relative min-h-0 flex-1 overflow-auto py-2"
    >
      <table className="w-full border-collapse font-mono text-micro">
        <tbody>
          {lines.map((line, i) => {
            const lineNum = i + 1;
            const isHot =
              highlightStart != null &&
              highlightEnd != null &&
              lineNum >= highlightStart &&
              lineNum <= highlightEnd;
            const row = tokens?.[i];

            return (
              <tr
                key={i}
                ref={isHot && lineNum === highlightStart ? firstHot : undefined}
                className={isHot ? "bg-signal/[0.07]" : undefined}
                style={
                  isHot && lineNum === highlightStart
                    ? { boxShadow: "inset 2px 0 0 var(--color-signal)" }
                    : undefined
                }
              >
                <td
                  // `signal`, not `signal-dim`. Raising the cold gutter to the
                  // 4.5 floor left the dim variant at 3.42:1 on the tinted hot
                  // row — the line under discussion had the least legible number
                  // in the pane, which is backwards. Now 8.62 / 5.56, above cold
                  // gutter's 4.53, so prominence runs the same direction as
                  // attention.
                  className={`w-10 select-none border-r border-rule py-0 pr-2.5 text-right align-top tabular-nums ${
                    isHot ? "text-signal" : "text-code-gutter"
                  }`}
                >
                  {lineNum}
                </td>
                <td
                  // Cold code keeps its syntax colours at full strength. It also
                  // used to carry `code-cold`, an opacity veil, which turned out
                  // to be the sole cause of failure for ~1100 glyphs in dark and
                  // ~1700 in light — light had no headroom for a fade at all. The
                  // band is marked by its tint, its inset rule, its `signal` line
                  // number and this brighter inherited colour, so the veil was
                  // the fourth signal and the only subtractive one. See the note
                  // beside `.tok` in globals.css.
                  className={`whitespace-pre py-0 pl-3 pr-4 ${
                    isHot ? "text-code-hot" : "text-code-line"
                  }`}
                >
                  {row && row.length > 0
                    ? row.map((token, j) => (
                        <span key={j} className="tok" style={token.style as React.CSSProperties}>
                          {token.content}
                        </span>
                      ))
                    : line || " "}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default memo(CodeLines);
