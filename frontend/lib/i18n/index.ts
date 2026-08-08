import { en, type Dictionary } from "@/lib/i18n/en";
import { he } from "@/lib/i18n/he";

export type { Dictionary };

export const LOCALES = ["en", "he"] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "en";

export const DICTIONARIES: Record<Locale, Dictionary> = { en, he };

export const DIRECTION: Record<Locale, "ltr" | "rtl"> = { en: "ltr", he: "rtl" };

/** Read by the server layout so `<html lang dir>` is right on the first paint. */
export const LOCALE_COOKIE = "codeonboard_locale";

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

export function toLocale(value: unknown): Locale {
  return isLocale(value) ? value : DEFAULT_LOCALE;
}

/**
 * Backend failures arrive as `detail` slugs (`session_not_found`) mixed with
 * real prose (a pipeline error list). Translate the ones we recognise and pass
 * anything else through — a raw stack trace is more useful than a generic
 * "something went wrong".
 */
export function translateError(dict: Dictionary, message: string): string {
  return dict.errors[message.trim()] ?? message;
}
