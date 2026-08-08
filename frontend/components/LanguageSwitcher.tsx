"use client";

import { LOCALES } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/context";

/**
 * Two-locale segmented toggle. Each option is labelled in its own language —
 * "עברית" rather than "Hebrew" — so it is legible to someone who cannot read
 * the language currently active.
 */
export default function LanguageSwitcher({ className = "" }: { className?: string }) {
  const { locale, setLocale, t } = useI18n();

  return (
    <div
      role="group"
      aria-label={t.language.label}
      className={`flex shrink-0 items-center overflow-hidden rounded border border-rule ${className}`}
    >
      {LOCALES.map((code) => {
        const isActive = code === locale;
        return (
          <button
            key={code}
            type="button"
            lang={code}
            onClick={() => setLocale(code)}
            aria-pressed={isActive}
            className={`px-2.5 py-1 font-mono text-[10.5px] transition ${
              isActive
                ? "bg-signal/15 text-signal"
                : "text-graphite hover:text-chalk"
            }`}
          >
            {t.language[code]}
          </button>
        );
      })}
    </div>
  );
}
