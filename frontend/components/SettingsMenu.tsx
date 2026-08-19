"use client";

import { useEffect, useRef, useState } from "react";
import {
  TEXT_SIZE_ORDER,
  THEME_ORDER,
  applyPrefs,
  readPrefs,
  writePrefs,
  type Prefs,
  type TextSize,
} from "@/lib/prefs";
import { t } from "@/lib/strings";

/**
 * Display settings — theme and text size.
 *
 * The preference is applied to `<html>` the moment it is chosen, so the whole
 * app repaints under the reader's cursor and the panel itself is the preview.
 * Nothing here is sent anywhere: see `lib/prefs.ts`.
 */
export default function SettingsMenu({ className = "" }: { className?: string }) {
  const [open, setOpen] = useState(false);
  // Read straight from storage rather than starting at the default and
  // correcting: the boot script has already painted the stored preference, and
  // a corrected default would make the panel disagree with the page it is on.
  const [prefs, setPrefs] = useState<Prefs>(() => readPrefs());
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const update = (patch: Partial<Prefs>) => {
    const next = { ...prefs, ...patch };
    setPrefs(next);
    writePrefs(next);
    applyPrefs(next);
  };

  // "System" is a live subscription, not a one-time reading: the OS can flip at
  // sunset while the session is open.
  useEffect(() => {
    if (prefs.theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const onChange = () => applyPrefs(prefs);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [prefs]);

  // Dismissal: escape, or a click that lands outside the panel.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    const onPointer = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    // Capture, so the session page's own Escape handler doesn't also fire and
    // close the map behind an open panel.
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("pointerdown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={t.settings.open}
        aria-haspopup="dialog"
        aria-expanded={open}
        className={`flex h-[1.75rem] w-[1.75rem] shrink-0 items-center justify-center rounded border transition ${
          open
            ? "border-signal-dim bg-signal/15 text-signal"
            : "border-rule bg-slab text-graphite hover:border-signal-dim hover:text-signal"
        }`}
      >
        <GearIcon />
      </button>

      {open && (
        <div
          role="dialog"
          aria-label={t.settings.title}
          className="absolute end-0 top-[calc(100%+0.5rem)] z-50 flex w-[15rem] flex-col gap-4 rounded-md border border-rule bg-slab p-3.5 shadow-[0_10px_30px_rgba(0,0,0,0.35)]"
        >
          <Field label={t.settings.theme}>
            <div className="grid grid-cols-3 gap-1">
              {THEME_ORDER.map((choice) => (
                <Choice
                  key={choice}
                  selected={prefs.theme === choice}
                  onSelect={() => update({ theme: choice })}
                >
                  {t.settings.themes[choice]}
                </Choice>
              ))}
            </div>
          </Field>

          <Field label={t.settings.textSize}>
            <div className="grid grid-cols-4 gap-1">
              {TEXT_SIZE_ORDER.map((size) => (
                <Choice
                  key={size}
                  selected={prefs.textSize === size}
                  onSelect={() => update({ textSize: size })}
                  label={t.settings.textSizeNames[size]}
                >
                  {/* Rendered at its own step, so the control shows what it does. */}
                  <span className={PREVIEW_SIZE[size]}>{t.settings.textSizes[size]}</span>
                </Choice>
              ))}
            </div>
          </Field>

          <p className="font-mono text-micro text-graphite">
            {t.settings.note}
          </p>
        </div>
      )}
    </div>
  );
}

/** Each step previewed at roughly its own relative size. */
const PREVIEW_SIZE: Record<TextSize, string> = {
  small: "text-micro",
  medium: "text-micro",
  large: "text-meta",
  xlarge: "text-aside",
};

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
        {label}
      </span>
      {children}
    </div>
  );
}

function Choice({
  selected, onSelect, label, children,
}: {
  selected: boolean;
  onSelect: () => void;
  /** Spoken name, when the visible content is an abbreviation. */
  label?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      aria-label={label}
      className={`flex h-[1.9rem] items-center justify-center rounded border text-micro transition ${
        selected
          ? "border-signal-dim bg-signal/15 font-medium text-signal"
          : "border-rule text-graphite hover:border-signal-dim hover:text-chalk"
      }`}
    >
      {children}
    </button>
  );
}

function GearIcon() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      className="h-[0.875rem] w-[0.875rem] fill-none stroke-current stroke-[1.3]"
    >
      <circle cx="8" cy="8" r="2.4" />
      <path
        d="M8 1.4v1.7M8 12.9v1.7M14.6 8h-1.7M3.1 8H1.4M12.67 3.33l-1.2 1.2M4.53 11.47l-1.2 1.2M12.67 12.67l-1.2-1.2M4.53 4.53l-1.2-1.2"
        strokeLinecap="round"
      />
    </svg>
  );
}
