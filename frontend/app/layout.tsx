import type { Metadata } from "next";
import { Geist_Mono, Red_Hat_Text } from "next/font/google";
import { AuthProvider } from "@/lib/auth";
import { BOOT_SCRIPT, DEFAULT_PREFS } from "@/lib/prefs";
import "./globals.css";

/**
 * Red Hat Text, and the choice is about the lesson column rather than the chrome.
 *
 * Geist is a grotesque built for interface labels, and it made 16px prose in a
 * 48ch measure read as a long caption. Red Hat Text is a text face: taller
 * x-height, rounder counters, more open apertures, so the same paragraph at the
 * same size reads as something meant to be read.
 *
 * The variable axis (300–700) is loaded, not four static cuts, because the app
 * already asks for `font-medium` beside body weight in the same line of type and
 * a missing cut is silently synthesised by the browser into a smeared fake bold.
 *
 * ITALIC IS LOADED, WHICH IS NEW. Model-authored markdown emits `<em>` through
 * `ui/Prose.tsx`, and blockquotes and the lesson's `why_now` line are italic too —
 * so emphasis was on screen constantly and every instance of it was a
 * browser-synthesised oblique, because Geist ships no italic at all and there was
 * nothing to load. Red Hat Text does, so it is asked for: a real italic is a
 * different set of letterforms rather than the upright ones sheared, and emphasis
 * inside an explanation is worth one more font file.
 *
 * `Geist_Mono` below is deliberately not touched — the mono face is a separate
 * decision from the reading face. Be aware, though, that it is ALSO not used:
 * `--font-geist-mono` is defined here and consumed nowhere, so `font-mono`
 * resolves to Tailwind's default stack and every eyebrow, filename and count on
 * every screen is the operating system's mono face. Confirmed in the built
 * stylesheet, not inferred. That means this loader downloads a font family the
 * app never renders; the fix is either to point `--font-mono` at it in
 * `globals.css` — a real visual change, and one to look at in a browser — or to
 * delete the loader. Both are out of scope here, and leaving it is the status quo
 * rather than a choice this change is making.
 */
const redHatText = Red_Hat_Text({
  variable: "--font-red-hat-text",
  subsets: ["latin"],
  style: ["normal", "italic"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "CodeOnboard",
  description: "Build an understanding of an unfamiliar codebase, one anchored concept at a time.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      // The server renders the default; the boot script below corrects it from
      // localStorage before first paint, which React would otherwise flag as a
      // hydration mismatch on an attribute it was told to own.
      data-theme={DEFAULT_PREFS.theme}
      suppressHydrationWarning
      className={`${redHatText.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        {/* Blocking on purpose: it must run before anything paints, or every
            load flashes the default theme before the chosen one. */}
        <script dangerouslySetInnerHTML={{ __html: BOOT_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col">
        {/* One `GET /auth/me` for the whole app, held here so every page reads
            the same answer. The cookie is HttpOnly, so this is the only way the
            client can know who it is — the server stays the authority. */}
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
