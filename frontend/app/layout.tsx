import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { BOOT_SCRIPT, DEFAULT_PREFS } from "@/lib/prefs";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
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
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        {/* Blocking on purpose: it must run before anything paints, or every
            load flashes the default theme before the chosen one. */}
        <script dangerouslySetInnerHTML={{ __html: BOOT_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
