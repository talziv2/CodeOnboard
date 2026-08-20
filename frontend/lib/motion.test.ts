import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, test } from "vitest";

/**
 * X1's probe: what `prefers-reduced-motion` actually removes.
 *
 * A source test rather than a rendered one, because the claim is about a stylesheet
 * rule and nothing else — the media query either names the right properties or it
 * does not, and a jsdom render cannot evaluate a media query at all.
 *
 * The rule this replaces was the common recipe: `transition-duration: 0.01ms` on
 * everything. That is too broad. `prefers-reduced-motion` exists for vestibular
 * discomfort, which comes from things travelling and resizing, not from a colour
 * settling — and zeroing every transition also removed the crossfades that carry
 * meaning here, so state changed with no indication that it had. Calmer would have
 * been fine; abrupt is not the same thing.
 */

const css = readFileSync(join(process.cwd(), "app", "globals.css"), "utf8");

/** The reduced-motion block, and nothing around it. */
function reducedMotionBlock(): string {
  const start = css.indexOf("@media (prefers-reduced-motion: reduce)");
  expect(start, "the reduced-motion block has gone missing").toBeGreaterThan(-1);
  // Walk braces so a nested rule inside the query does not end the slice early.
  let depth = 0;
  for (let i = css.indexOf("{", start); i < css.length; i++) {
    if (css[i] === "{") depth++;
    else if (css[i] === "}" && --depth === 0) return css.slice(start, i + 1);
  }
  throw new Error("unbalanced braces in the reduced-motion block");
}

describe("reduced motion drops movement", () => {
  const block = reducedMotionBlock();

  test("animations are off entirely", () => {
    expect(block).toMatch(/animation:\s*none\s*!important/);
  });

  test("the transition allowlist names no property that moves or resizes", () => {
    const allowed = block.match(/transition-property:\s*([^;]+);/)?.[1] ?? "";
    for (const moving of [
      "transform",
      "translate",
      "scale",
      "rotate",
      "height",
      "width",
      "margin",
      "padding",
      "inset",
      "top",
      "left",
      "grid-template-rows",
      "all",
    ]) {
      expect(allowed, `${moving} still transitions under reduced motion`).not.toContain(moving);
    }
  });

  test("opacity survives, because a fade is not movement", () => {
    const allowed = block.match(/transition-property:\s*([^;]+);/)?.[1] ?? "";
    expect(allowed).toContain("opacity");
  });

  test("colour feedback survives too — hover and focus still respond", () => {
    const allowed = block.match(/transition-property:\s*([^;]+);/)?.[1] ?? "";
    expect(allowed).toContain("color");
    expect(allowed).toContain("background-color");
    expect(allowed).toContain("border-color");
  });

  test("what survives is capped at 100ms", () => {
    // Long enough to read as a change rather than a flicker, short enough that
    // nobody is waiting for it.
    const ms = Number(block.match(/transition-duration:\s*(\d+)ms\s*!important/)?.[1]);
    expect(ms).toBeGreaterThan(0);
    expect(ms).toBeLessThanOrEqual(100);
  });

  test("smooth scrolling becomes instant rather than being left animated", () => {
    // The source pane scrolls when a citation is clicked. That is motion the
    // learner asked for, so it still happens — it just stops travelling.
    expect(block).toMatch(/scroll-behavior:\s*auto\s*!important/);
  });
});

describe("the motion vocabulary is tokens, not literals", () => {
  test("the four durations exist and are ordered", () => {
    const value = (name: string) =>
      Number(css.match(new RegExp(`--motion-${name}:\\s*(\\d+)ms`))?.[1]);
    const [micro, state, layout, route] = [
      value("micro"),
      value("state"),
      value("layout"),
      value("route"),
    ];
    for (const v of [micro, state, layout, route]) expect(v).toBeGreaterThan(0);
    // Ordered by how much moves: a hover is not a panel, and a panel is not the
    // rail's pin travelling the length of the route.
    expect(micro).toBeLessThan(state);
    expect(state).toBeLessThan(layout);
    expect(layout).toBeLessThan(route);
  });
});
