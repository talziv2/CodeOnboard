"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  DEFAULT_LOCALE,
  DICTIONARIES,
  DIRECTION,
  LOCALE_COOKIE,
  translateError,
  type Dictionary,
  type Locale,
} from "@/lib/i18n";

interface I18nValue {
  locale: Locale;
  dir: "ltr" | "rtl";
  /** The active dictionary. Named `t` because every call site reads `t.x.y`. */
  t: Dictionary;
  setLocale: (next: Locale) => void;
  /** Maps a backend error slug to a readable sentence in the active language. */
  te: (message: string) => string;
}

const I18nContext = createContext<I18nValue | null>(null);

/** A year, in seconds. The choice is a preference, not a session. */
const COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

export function LocaleProvider({
  initialLocale,
  children,
}: {
  initialLocale: Locale;
  children: React.ReactNode;
}) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    // The cookie is what the server layout reads on the next request, so the
    // choice survives a reload without a flash of the wrong direction.
    document.cookie = `${LOCALE_COOKIE}=${next};path=/;max-age=${COOKIE_MAX_AGE};samesite=lax`;
    // Update the live document too — this render is client-side, and the
    // server-rendered `<html>` attributes won't change until a navigation.
    document.documentElement.lang = next;
    document.documentElement.dir = DIRECTION[next];
  }, []);

  const value = useMemo<I18nValue>(() => {
    const t = DICTIONARIES[locale] ?? DICTIONARIES[DEFAULT_LOCALE];
    return {
      locale,
      dir: DIRECTION[locale],
      t,
      setLocale,
      te: (message: string) => translateError(t, message),
    };
  }, [locale, setLocale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext);
  if (value === null) {
    throw new Error("useI18n must be used inside <LocaleProvider>");
  }
  return value;
}

/**
 * The dictionary for an explicit locale, ignoring the global preference.
 *
 * Used where the language is a property of the thing being displayed rather
 * than of the reader — a learning session, whose titles and lessons were
 * written in one language and persisted.
 */
export function useLocale(locale: Locale): Omit<I18nValue, "setLocale"> {
  return useMemo(() => {
    const t = DICTIONARIES[locale] ?? DICTIONARIES[DEFAULT_LOCALE];
    return {
      locale,
      dir: DIRECTION[locale],
      t,
      te: (message: string) => translateError(t, message),
    };
  }, [locale]);
}

/**
 * Pins a subtree to `locale` regardless of the global preference, and aligns
 * the document direction with it for as long as the subtree is mounted.
 *
 * A session's content language is fixed when the graph is generated. Rendering
 * Hebrew lessons inside English chrome — or worse, laying Hebrew prose out
 * left-to-right — is incoherent, so the session page pins itself to whatever
 * language its content is actually in.
 */
export function LocaleOverride({
  locale,
  children,
}: {
  locale: Locale;
  children: React.ReactNode;
}) {
  const parent = useI18n();
  const scoped = useLocale(locale);

  useEffect(() => {
    // `<html dir>` was server-rendered from the cookie, which may disagree.
    const root = document.documentElement;
    const previous = { lang: root.lang, dir: root.dir };
    root.lang = locale;
    root.dir = DIRECTION[locale];
    return () => {
      root.lang = previous.lang;
      root.dir = previous.dir;
    };
  }, [locale]);

  const value = useMemo<I18nValue>(
    () => ({ ...scoped, setLocale: parent.setLocale }),
    [scoped, parent.setLocale]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
