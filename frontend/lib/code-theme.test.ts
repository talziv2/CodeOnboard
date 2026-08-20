import { describe, expect, test } from "vitest";
import { CODE_THEME_DARK, CODE_THEME_LIGHT } from "@/lib/code-theme";

/**
 * Every syntax colour clears 4.5:1 against the pane it is drawn on.
 *
 * The source pane was the last place in the app with real contrast failures — five
 * colours, two dark and three light, between 3.67 and 4.38. They survived several
 * audits because the audits scoped themselves to the lesson UI and excluded `.tok`
 * spans by class, which is reasonable when the palette is a known exception and
 * useless once it is meant to be fixed.
 *
 * A unit test rather than a browser sweep, because the values are the whole of the
 * question: the theme is authored here, both variants are registered at once, and
 * the pane emits a CSS-variable pair per token, so what renders is exactly what is
 * written in this file. A DOM audit could only re-derive the same arithmetic after
 * paying for a browser and a highlighted file to look at.
 *
 * WHY THE ORDERING IS ASSERTED TOO. Comments and punctuation are *supposed* to
 * recede, and the cheapest way to pass a contrast floor is to flatten everything
 * toward the foreground — which would pass this test and destroy the thing the
 * palette is for. The ordering assertions are what make the floor a constraint on
 * the design rather than a replacement for it.
 */

const BG = { dark: "#0c1318", light: "#dbe5ec" };

function luminance(hex: string): number {
  const h = hex.replace("#", "");
  const channel = (i: number) => {
    const c = parseInt(h.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(0) + 0.7152 * channel(2) + 0.0722 * channel(4);
}

function ratio(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)];
  const [hi, lo] = x > y ? [x, y] : [y, x];
  return (hi + 0.05) / (lo + 0.05);
}

/** Every distinct foreground the theme can paint a token with. */
function foregrounds(theme: typeof CODE_THEME_DARK): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const rule of theme.settings ?? []) {
    const fg = rule.settings?.foreground;
    if (!fg) continue;
    const scopes = rule.scope
      ? Array.isArray(rule.scope)
        ? rule.scope
        : [rule.scope]
      : ["<default>"];
    out.set(fg, [...(out.get(fg) ?? []), ...scopes]);
  }
  return out;
}

describe.each([
  ["dark", CODE_THEME_DARK, BG.dark],
  ["light", CODE_THEME_LIGHT, BG.light],
])("%s theme", (name, theme, bg) => {
  test("the declared background is the one the pane actually paints", () => {
    // The floor is meaningless if measured against the wrong ground, and this is
    // the value `globals.css` sets on the pane (`--color-trench`).
    expect(theme.colors?.["editor.background"]?.toLowerCase()).toBe(bg);
  });

  test("every token colour clears 4.5:1", () => {
    const failures: string[] = [];
    for (const [fg, scopes] of foregrounds(theme)) {
      const r = ratio(fg, bg);
      if (r < 4.5) failures.push(`${fg} at ${r.toFixed(2)} — ${scopes[0]}`);
    }
    expect(failures, failures.join("; ")).toEqual([]);
  });

  test("no token is painted in signal cyan", () => {
    // The pane's own rule, stated in the theme's docstring: signal marks "you are
    // here" and nothing else, so spending it on syntax would stop the highlighted
    // band reading as special.
    for (const fg of foregrounds(theme).keys()) {
      expect(fg.toLowerCase()).not.toBe("#5bc8e8");
    }
  });
});

describe("the recession order survives the floor", () => {
  // Passing a contrast floor by flattening everything toward the foreground would
  // satisfy the test above and lose the palette. These say which colours are meant
  // to be quieter than which, in the order the original palette established.
  const at = (theme: typeof CODE_THEME_DARK, scope: string, bg: string) => {
    for (const rule of theme.settings ?? []) {
      const scopes = Array.isArray(rule.scope) ? rule.scope : [rule.scope];
      if (rule.settings?.foreground && scopes.includes(scope)) {
        return ratio(rule.settings.foreground, bg);
      }
    }
    throw new Error(`no rule for ${scope}`);
  };

  test("dark: comments recede furthest, then punctuation, then operators", () => {
    const comment = at(CODE_THEME_DARK, "comment", BG.dark);
    const punct = at(CODE_THEME_DARK, "punctuation", BG.dark);
    const operator = at(CODE_THEME_DARK, "keyword.operator", BG.dark);
    expect(comment).toBeLessThan(punct);
    expect(punct).toBeLessThan(operator);
  });

  test("light: the same order, in a narrower band", () => {
    // Light's ceiling is `base` at 6.83, so the three cluster between 4.5 and 4.75.
    // Ordered, close, and legible — which is the trade the palette comments record.
    const comment = at(CODE_THEME_LIGHT, "comment", BG.light);
    const punct = at(CODE_THEME_LIGHT, "punctuation", BG.light);
    const operator = at(CODE_THEME_LIGHT, "keyword.operator", BG.light);
    expect(comment).toBeLessThan(punct);
    expect(punct).toBeLessThan(operator);
  });

  test("string punctuation stays quieter than the string it quotes", () => {
    for (const [theme, bg] of [
      [CODE_THEME_DARK, BG.dark],
      [CODE_THEME_LIGHT, BG.light],
    ] as const) {
      expect(at(theme, "punctuation.definition.string", bg)).toBeLessThan(
        at(theme, "string", bg)
      );
    }
  });
});
