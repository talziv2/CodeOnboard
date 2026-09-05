"use client";

import { useState } from "react";
import Button from "@/components/ui/Button";
import SectionLabel from "@/components/ui/SectionLabel";
import type { PatchFile } from "@/lib/api";
import { t } from "@/lib/strings";

/**
 * Where the learner writes the change. **Not an editor, and not a diff.**
 *
 * A patch here is a list of `{path, contents}` files, and the reasons are
 * practical rather than aesthetic:
 *
 *   - the scope check becomes a set comparison instead of a diff parser;
 *   - `CodeLines` highlights Python and has no `diff` grammar, so a unified diff
 *     would render as grey text;
 *   - hand-writing a valid unified diff into a textarea in three minutes fails
 *     on punctuation rather than on substance, which is a demo failure mode.
 *
 * THE PATH FIELD IS FREELY TYPEABLE, deliberately. The boundary's targets are
 * offered as buttons, but nothing stops the learner naming another file — and it
 * must not, because a scope check that cannot fail proves nothing.
 *
 * ON THE SINGLE-COMPOSER INVARIANT (`AnswerComposer`): the lesson's textarea and
 * this one must never be on screen together. That holds because the contribution
 * stage REPLACES the lesson area, exactly as `CompletionScreen` does. This
 * component must never be rendered beside a live lesson.
 *
 * Nothing typed here reaches the repository checkout. It is stored on the
 * session and read back; `data/repos/<owner>/<name>` is shared by every session
 * of that repository and is never written.
 */
export default function ImplementStep({
  patch,
  suggestions,
  onSave,
  onStuck,
  busy,
}: {
  patch: PatchFile[];
  /** Paths from the change boundary, offered as a starting point. */
  suggestions: string[];
  onSave: (files: PatchFile[]) => void;
  onStuck?: () => void;
  busy: boolean;
}) {
  const [files, setFiles] = useState<PatchFile[]>(
    patch.length > 0
      ? patch
      : suggestions.slice(0, 1).map((path) => ({
          path, contents: "", intent: "modify" as const,
        })),
  );

  const patchFile = (index: number, change: Partial<PatchFile>) =>
    setFiles(files.map((f, i) => (i === index ? { ...f, ...change } : f)));

  const addFile = (path = "") =>
    setFiles([...files, { path, contents: "", intent: "modify" }]);

  const removeFile = (index: number) =>
    setFiles(files.filter((_, i) => i !== index));

  const unusedSuggestions = suggestions.filter(
    (path) => !files.some((f) => f.path === path),
  );

  return (
    <section className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <SectionLabel tone="raised">{t.contribution.implementHeading}</SectionLabel>
        <p className="text-aside text-graphite">{t.contribution.implementNote}</p>
      </div>

      {files.length === 0 && (
        <p className="text-aside text-graphite">{t.contribution.implementEmpty}</p>
      )}

      {files.map((file, index) => (
        <div
          key={index}
          className="flex flex-col gap-3 rounded-panel border border-rule bg-well p-4"
        >
          <div className="flex items-center gap-3">
            <label className="flex-1">
              <span className="sr-only">{t.contribution.implementPath}</span>
              <input
                type="text"
                value={file.path}
                placeholder={t.contribution.implementPath}
                onChange={(e) => patchFile(index, { path: e.target.value })}
                className="w-full rounded-field border border-rule bg-trench px-3 py-2 font-mono text-micro text-chalk placeholder:text-graphite focus:border-signal-dim"
              />
            </label>
            <Button
              variant="ghost"
              onClick={() => removeFile(index)}
              className="font-mono text-micro text-graphite hover:text-paper"
            >
              {t.contribution.implementRemove}
            </Button>
          </div>
          <label>
            <span className="sr-only">{t.contribution.implementCode}</span>
            {/* Learner-authored text: monospace, pre-wrap, never markdown. */}
            <textarea
              rows={12}
              value={file.contents}
              onChange={(e) => patchFile(index, { contents: e.target.value })}
              spellCheck={false}
              className="w-full resize-y whitespace-pre rounded-field border border-rule bg-trench p-3 font-mono text-micro text-chalk placeholder:text-graphite focus:border-signal-dim"
            />
          </label>
        </div>
      ))}

      <div className="flex flex-wrap items-center gap-3">
        <Button variant="secondary" size="sm" onClick={() => addFile()}>
          {t.contribution.implementAdd}
        </Button>
        {unusedSuggestions.map((path) => (
          <button
            key={path}
            type="button"
            onClick={() => addFile(path)}
            className="rounded-field border border-rule px-2.5 py-1 font-mono text-micro text-graphite hover:text-paper"
          >
            + {path}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-4">
        <Button
          variant="primary"
          size="md"
          onClick={() => onSave(files.filter((f) => f.path.trim()))}
          disabled={busy || files.every((f) => !f.path.trim())}
        >
          {busy ? t.contribution.implementSaving : t.contribution.implementSave}
        </Button>
        {onStuck && (
          // A LINK, never a second textarea — the same rule `AnswerComposer`
          // holds, and for the same reason. The Tutor opens in its own pane.
          <button
            type="button"
            onClick={onStuck}
            className="font-mono text-micro text-graphite underline underline-offset-4 hover:text-paper"
          >
            {t.contribution.implementStuck}
          </button>
        )}
      </div>
    </section>
  );
}
