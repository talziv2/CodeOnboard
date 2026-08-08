import type { Metadata } from "next";
import { cookies } from "next/headers";
import { Geist, Geist_Mono } from "next/font/google";
import { DIRECTION, LOCALE_COOKIE, toLocale } from "@/lib/i18n";
import { LocaleProvider } from "@/lib/i18n/context";
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

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Reading the cookie here — rather than in a client effect — means `lang` and
  // `dir` are correct in the very first HTML, so an RTL locale never flashes
  // left-to-right before hydration. It opts this route into dynamic rendering,
  // which costs nothing: every page below is a client component driven by the API.
  const locale = toLocale((await cookies()).get(LOCALE_COOKIE)?.value);

  return (
    <html
      lang={locale}
      dir={DIRECTION[locale]}
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <LocaleProvider initialLocale={locale}>{children}</LocaleProvider>
      </body>
    </html>
  );
}
