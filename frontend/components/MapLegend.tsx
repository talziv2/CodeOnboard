import StatePin from "@/components/ui/StatePin";
import { t } from "@/lib/strings";

/**
 * The map's key: every marker and every kind of line, in one place, on demand.
 *
 * ── Why it exists, and why only now ──────────────────────────────────────────
 *
 * The rail used to carry a permanent legend and it was removed — "a pin's meaning
 * is on the pin, as its accessible name, and the map keeps the full key"
 * (`RouteRail`). That sentence was a promise the map had not yet kept, and it
 * mattered less when a stop was one of four circles. The route now carries seven
 * markers and four line treatments, which is a visual language, and a language
 * nobody is taught is decoration.
 *
 * ── `<details>`, not a popover ────────────────────────────────────────────────
 *
 * Keyboard operation, open/close without React holding the answer, and correct
 * announcement with no ARIA of ours — the same three reasons `Disclosure` gives,
 * and the same element. It also stays clear of a hazard a popover would walk into:
 * Escape in route mode leaves the map entirely, so a key that closed on Escape
 * would need a capture-phase listener to stop the page acting on the same press,
 * and one that did not would drop the learner out of the view they were reading.
 * A disclosure needs neither. The cost is that opening it moves the route down the
 * page, which is the honest trade: nothing is covered and nothing is trapped.
 *
 * ── THE MARKERS ARE THE REAL ONES ─────────────────────────────────────────────
 *
 * Every pin below is a `StatePin` at the map's own size, driven by the same four
 * server-sent facts the route passes it — so the key cannot drift from the thing
 * it explains. A hand-drawn circle of the right colour would have been fewer
 * lines and would have been wrong within one milestone. The line samples are the
 * same CSS the row draws, for the same reason.
 *
 * What is NOT in here is as deliberate: `standingOf` distinguishes `passed_by`
 * from `set_aside`, and both draw the bar. That difference is real to the model
 * and invisible to a learner reading a route — the bar means one thing, *you
 * closed this*, and the card's own caption says which. Two rows for one symbol
 * would teach a distinction the symbol does not make.
 */

/** Every pin the route can draw, from the inputs that actually produce it. */
const PINS: {
  key: string;
  pin: {
    understanding?: "strength" | "recovered" | "unresolved" | "insufficient";
    attempted?: boolean;
    visited?: boolean;
    isCurrent?: boolean;
  };
  label: string;
  meaning: string;
}[] = [
  {
    key: "here",
    pin: { isCurrent: true },
    label: t.rail.youAreHere,
    meaning: t.map.legend.here,
  },
  {
    key: "strength",
    pin: { understanding: "strength", attempted: true },
    label: t.map.understanding.strength,
    meaning: t.map.legend.demonstrated,
  },
  {
    key: "recovered",
    pin: { understanding: "recovered", attempted: true },
    label: t.map.understanding.recovered,
    meaning: t.map.workedThroughHint,
  },
  {
    key: "unresolved",
    pin: { understanding: "unresolved", attempted: true },
    label: t.map.understanding.unresolved,
    meaning: t.map.legend.needsWork,
  },
  {
    key: "attempted",
    pin: { understanding: "insufficient", attempted: true },
    label: t.rail.attempted,
    meaning: t.rail.attemptedHint,
  },
  {
    key: "untouched",
    pin: {},
    label: t.map.understanding.insufficient,
    meaning: t.map.legend.untouched,
  },
  {
    key: "closed",
    pin: { understanding: "insufficient", visited: true },
    label: t.map.legend.closedLabel,
    meaning: t.map.legend.closed,
  },
];

/** The four line treatments, described by the CSS the route itself uses. */
const LINES: { key: string; style: React.CSSProperties; label: string; meaning: string }[] = [
  {
    key: "walked",
    style: { background: "var(--color-signal-dim)" },
    label: t.map.legend.walkedLabel,
    meaning: t.map.legend.walked,
  },
  {
    key: "ahead",
    style: { background: "var(--color-rule)" },
    label: t.map.legend.aheadLabel,
    meaning: t.map.legend.ahead,
  },
  {
    key: "warmup",
    style: {
      backgroundImage:
        "repeating-linear-gradient(to right, var(--color-signal) 0 5px, transparent 5px 10px)",
    },
    label: t.rail.addedAfterConfusion,
    meaning: t.map.legend.branchWarmUp,
  },
  {
    key: "optional",
    style: {
      backgroundImage:
        "repeating-linear-gradient(to right, var(--color-rule) 0 5px, transparent 5px 10px)",
    },
    label: t.map.legend.optionalLabel,
    meaning: t.map.legend.branchOptional,
  },
];

function Row({
  marker, label, meaning,
}: {
  marker: React.ReactNode;
  label: string;
  meaning: string;
}) {
  return (
    <li className="grid grid-cols-[calc(24rem/16)_minmax(0,1fr)] items-start gap-2.5">
      {/* The marker column is fixed so every row's text starts on one line, and
          it is centred so a 15px pin and a 28px rule share an axis. */}
      <span className="flex h-[calc(20rem/16)] items-center justify-center">{marker}</span>
      <span className="flex min-w-0 flex-col">
        <span className="text-aside text-chalk [overflow-wrap:anywhere]">{label}</span>
        <span className="text-meta text-graphite [overflow-wrap:anywhere]">{meaning}</span>
      </span>
    </li>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2.5">
      <span className="font-mono text-micro uppercase tracking-[0.16em] text-graphite">
        {title}
      </span>
      <ul className="flex flex-col gap-2.5">{children}</ul>
    </div>
  );
}

export default function MapLegend() {
  return (
    <details
      // Left at its default `display`. `w-fit` on the summary keeps the control
      // to its own width, which is the only reason a `flex` wrapper was tempting
      // here — and one less override on an element whose open/closed rendering
      // the browser owns.
      className="group"
    >
      <summary
        /**
         * The tour aims HERE, at the summary, and not at the `<details>` around
         * it — which is the opposite of what `Disclosure` does, for a reason that
         * is the mirror image of its own. A `<details>` is a block: closed, its
         * box is the full width of the column and 25px tall, so a spotlight on it
         * draws a band across mostly empty page with the control at one end. The
         * summary is the control, at every size, in both states. `Disclosure`
         * aims outward because its content escapes the summary's rect; this step
         * is read-only, so nothing has to be reachable through the hole.
         */
        data-tour="map-legend"
        title={t.map.legend.hint}
        className="flex w-fit cursor-pointer list-none items-center gap-1.5 rounded-field border border-rule px-2 py-1 font-mono text-micro uppercase tracking-[0.13em] text-graphite transition hover:border-signal-dim hover:text-signal"
      >
        <svg
          aria-hidden
          viewBox="0 0 10 10"
          className="h-2.5 w-2.5 shrink-0 fill-none stroke-current stroke-[1.5] transition-transform group-open:rotate-90"
        >
          <path d="M3.5 1.5 L7 5 L3.5 8.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {t.map.legend.open}
      </summary>

      <div className="mt-3 grid gap-x-8 gap-y-6 rounded-card border border-rule bg-slab px-4 py-4 sm:grid-cols-2">
        <Group title={t.map.legend.stopGroup}>
          {PINS.map((row) => (
            <Row
              key={row.key}
              label={row.label}
              meaning={row.meaning}
              marker={
                <StatePin
                  understanding={row.pin.understanding}
                  attempted={row.pin.attempted}
                  visited={row.pin.visited}
                  isCurrent={row.pin.isCurrent ?? false}
                  role="map"
                />
              }
            />
          ))}
        </Group>

        <Group title={t.map.legend.routeGroup}>
          {LINES.map((row) => (
            <Row
              key={row.key}
              label={row.label}
              meaning={row.meaning}
              marker={
                <span
                  aria-hidden
                  className="h-px w-[calc(24rem/16)]"
                  style={row.style}
                />
              }
            />
          ))}
        </Group>
      </div>
    </details>
  );
}
