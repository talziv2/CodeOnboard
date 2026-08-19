/**
 * The app's buttons, at exactly their current visual language.
 *
 * This is an extraction, not a redesign. The two treatments below are the ones
 * already in use, unchanged: there is still no solid primary, `signal` is still a
 * 15% tint, and the radius is still `rounded`. Whether a primary action should
 * actually look like one is a question for the visual pass.
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
  primary:
    "rounded-field border border-signal-dim bg-signal/15 font-medium text-signal transition hover:bg-signal/25",
  secondary:
    "rounded-field border border-rule text-graphite transition hover:border-signal-dim hover:text-signal",
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
