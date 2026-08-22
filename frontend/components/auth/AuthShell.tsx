import SettingsMenu from "@/components/SettingsMenu";
import { t } from "@/lib/strings";

/** The frame both auth pages share — the landing page's wordmark, nothing else. */
export default function AuthShell({
  title, subtitle, children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <main className="relative flex min-h-screen flex-col items-center justify-center bg-ink px-6 pt-16 pb-[20vh]">
      <SettingsMenu className="absolute end-5 top-5" />
      <div className="mb-10 flex flex-col items-center gap-2 text-center">
        <span aria-hidden className="mb-3 h-2 w-2 rotate-45 bg-signal" />
        <h1 className="font-display text-display font-medium tracking-tight text-chalk">
          {t.appName}
        </h1>
        <p className="max-w-sm text-aside text-graphite">{subtitle}</p>
      </div>
      <h2 className="sr-only">{title}</h2>
      {children}
    </main>
  );
}
