"use client";

import { useEffect, useState } from "react";
import { langForFence, tokenize, type CodeToken } from "@/lib/highlight";

/**
 * A fenced code block inside lesson prose.
 *
 * Coloured by the same Shiki core, the same two themes and the same `.tok`
 * variable pair as the source pane — see `lib/highlight.ts`. Sharing that is the
 * whole reason this is worth doing: a snippet quoted in the explanation and the
 * same lines opened in the pane are then the same colours, which is what makes
 * the two read as one artifact rather than as prose that happens to mention code.
 *
 * Colour arrives after the code does, never instead of it, exactly as in
 * `CodeLines`: the plain text renders on the first paint and repaints when the
 * grammar has loaded. An unknown fence language, or a failed fetch, leaves an
 * uncoloured block — which is still a code block, correctly set in mono on its
 * own surface.
 *
 * NO LINE NUMBERS and no highlight band. Those belong to the pane, where the
 * numbers are how a citation is found; here they would be furniture around four
 * lines of illustration.
 */
export default function ProseCode({ code, lang }: { code: string; lang: string | null }) {
  const [tokens, setTokens] = useState<CodeToken[][] | null>(null);

  useEffect(() => {
    setTokens(null);
    const grammar = langForFence(lang);
    if (!grammar) return;

    let alive = true;
    tokenize(code, grammar)
      .then((t) => alive && setTokens(t))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [code, lang]);

  return (
    <pre
      // Not inside `.measure`: a snippet is not prose and wrapping it to 70
      // characters would break lines the author chose. It scrolls instead.
      className="overflow-x-auto rounded-field border border-rule bg-trench px-3.5 py-3 font-mono text-meta text-code-line"
    >
      <code>
        {tokens
          ? tokens.map((row, i) => (
              <span key={i} className="block">
                {row.length
                  ? row.map((token, j) => (
                      <span key={j} className="tok" style={token.style as React.CSSProperties}>
                        {token.content}
                      </span>
                    ))
                  : " "}
              </span>
            ))
          : code}
      </code>
    </pre>
  );
}
