/**
 * The app's buttons, at exactly their current visual language.
 *
 * Three weights, and only one of them is filled. `primary` is a solid `signal`
 * fill; `secondary` is an outline; `chrome` and `ghost` are quieter still. The
 * rule that makes it work is that exactly one primary is visible per state — if a
 * state seems to need two, the state model is wrong rather than the button.
 *
 * The 15% `signal` tint that `primary` used to be is not gone from the product: it
 * is now unambiguously the SELECTED/ACTIVE treatment — a chosen interview option,
 * the active dock/float mode, a profile dial — while solid means "this is the
 * action". Those two were previously indistinguishable.
 *
 * VARIANT carries colour, font family and weight. SIZE carries padding and font
 * size. They are split that way because the real call sites vary independently —
 * the session header's chrome buttons are the secondary colours in mono, and the
 * gap list's "Set aside" is the secondary colours at the chrome size in sans.
 *
 * Deliberately absent: disabled and focus. Both come from root rules in
 * `globals.css` — the `:focus-visible` ring and the `--color-muted` treatment —
 * so there is nothing here to duplicate or to let drift.
 *
 * `className` is for LAYOUT only: `shrink-0`, `ms-auto`, `mt-1`, `w-fit`. It is
 * appended, but Tailwind resolves conflicts by stylesheet order rather than class
 * order, so it cannot reliably override a variant's own padding or colour. Wanting
 * to is the signal that a new size is needed, not an override.
 */
type Variant = "primary" | "secondary" | "chrome" | "ghost";
type Size = "xs" | "sm" | "md" | "lg" | "block";

const VARIANT: Record<Variant, string> = {
  // SOLID. Until F3c this was a 15% tint, which meant no action anywhere looked
  // like *the* action — the strongest CTA on any screen sat at the same weight as
  // a chip. Measured: ink on signal is 9.91:1 dark and 6.73:1 light, against
  // 7.53 / 5.35 for the tint it replaces (and 4.44 in light before D3 deepened
  // the token). The border is kept, in `signal` so it is invisible, purely so the
  // box geometry is unchanged from the outlined version.
  primary:
    "rounded-field border border-signal bg-signal font-medium text-ink transition hover:bg-signal/90",
  // `paper`, not `graphite`. Beside a solid primary, graphite read as unavailable
  // rather than as the quieter of two live choices. Measured on every surface a
  // button lands on: 8.94–10.97 dark, 7.41–9.31 light.
  secondary:
    "rounded-field border border-rule text-paper transition hover:border-signal-dim hover:text-signal",
  // The secondary colours in mono. Session furniture rather than lesson actions.
  chrome:
    "rounded-field border border-rule font-mono text-graphite transition hover:border-signal-dim hover:text-signal",
  // No border, no background, no padding — so it also carries its own type size,
  // which is why `ghost` takes no `size`.
  ghost: "font-mono text-micro text-graphite transition hover:text-signal",
};

const SIZE: Record<Size, string> = {
  xs: "px-2 py-1 text-micro",
  sm: "px-3 py-1.5 text-micro",
  md: "px-4 py-2 text-aside",
  lg: "px-5 py-2.5 text-aside",
  // No `w-full`: the one site is a flex-column child and already stretches, so
  // adding it would be a change dressed up as a default.
  block: "py-3 text-aside",
};

export default function Button({
  variant,
  size,
  className = "",
  ...rest
}: {
  variant: Variant;
  /** Omitted for `ghost`, which has no padding of its own. */
  size?: Size;
} & React.ComponentPropsWithoutRef<"button">) {
  const classes = [VARIANT[variant], size ? SIZE[size] : "", className]
    .filter(Boolean)
    .join(" ");
  return <button className={classes} {...rest} />;
}
