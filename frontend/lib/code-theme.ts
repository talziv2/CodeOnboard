/**
 * The two syntax themes for the source pane.
 *
 * These are TextMate themes in Shiki's shape, authored against the app's own
 * palette rather than borrowed from an editor: a stock theme would drag its own
 * colour language into a design where hue already means something.
 *
 * Two rules constrain every value here:
 *
 *  - **Signal cyan is never a syntax colour.** It marks "you are here" and
 *    nothing else (see `globals.css`), so the pane must not spend it on strings
 *    or keywords — the highlighted band and the current-line rule would stop
 *    reading as special.
 *  - **The hues come from the concept-tag family.** Architecture blue, flow
 *    teal, extension-point violet, brass and the synthesis amber already carry
 *    the app's chroma; reusing them keeps the pane inside the same instrument.
 *
 * Both themes are registered at once and every token is emitted as a *pair* of
 * CSS variables, so flipping the theme never re-tokenises anything — see
 * `lib/highlight.ts` and the `.tok` rules in `globals.css`.
 */
import type { ThemeRegistrationRaw } from "shiki/core";

export const DARK_THEME_NAME = "codeonboard-dark";
export const LIGHT_THEME_NAME = "codeonboard-light";

/** Scope lists are shared: only the colours differ between the two themes. */
interface Palette {
  base: string;
  comment: string;
  keyword: string;
  language: string;
  number: string;
  string: string;
  stringPunct: string;
  func: string;
  type: string;
  decorator: string;
  operator: string;
  punctuation: string;
  invalid: string;
}

const DARK: Palette = {
  base: "#9aabb6",
  // Comments recede, but they still have to be readable through the cold veil
  // in `globals.css` — this is set from that combined figure, not from how it
  // looks on its own.
  comment: "#60757f",
  keyword: "#c19ad6",
  language: "#d9a441",
  number: "#e0b088",
  string: "#7fbfae",
  stringPunct: "#5d9a8b",
  func: "#8fb6d9",
  type: "#dcc98a",
  decorator: "#b98db0",
  operator: "#7d8f9b",
  punctuation: "#6b7d88",
  invalid: "#d4634f",
};

/* Deeper and more saturated, not lighter: on a paper ground contrast comes from
   going darker, and a pastel would read as disabled code. */
const LIGHT: Palette = {
  base: "#2f4f5f",
  comment: "#5b7887",
  keyword: "#6e358f",
  language: "#7d5602",
  number: "#8a4310",
  string: "#0a6250",
  stringPunct: "#2b7566",
  func: "#155a8c",
  type: "#6b4f0a",
  decorator: "#8a3d7a",
  operator: "#4b6675",
  punctuation: "#5a7484",
  invalid: "#b1301a",
};

function build(name: string, type: "dark" | "light", p: Palette): ThemeRegistrationRaw {
  return {
    name,
    type,
    colors: {
      "editor.foreground": p.base,
      "editor.background": type === "dark" ? "#0c1318" : "#dbe5ec",
    },
    settings: [
      { settings: { foreground: p.base } },

      {
        scope: ["comment", "punctuation.definition.comment", "string.quoted.docstring"],
        settings: { foreground: p.comment, fontStyle: "italic" },
      },

      {
        scope: [
          "keyword",
          "storage",
          "storage.type",
          "storage.modifier",
          "keyword.control",
          "keyword.other",
        ],
        settings: { foreground: p.keyword },
      },
      // Symbolic operators are punctuation with a job; the *word* operators
      // (`and`, `in`, `is`, `not`) stay with the keywords they read as.
      { scope: ["keyword.operator"], settings: { foreground: p.operator } },
      {
        scope: [
          "keyword.operator.logical",
          "keyword.operator.word",
          "keyword.operator.expression",
          "keyword.operator.new",
        ],
        settings: { foreground: p.keyword },
      },

      {
        scope: [
          "constant.language",
          "variable.language",
          "variable.language.special",
          "support.type.builtin",
        ],
        settings: { foreground: p.language },
      },
      {
        scope: ["constant.numeric", "constant.character", "constant.other"],
        settings: { foreground: p.number },
      },

      { scope: ["string", "constant.character.escape"], settings: { foreground: p.string } },
      {
        scope: ["punctuation.definition.string", "storage.type.string"],
        settings: { foreground: p.stringPunct },
      },

      {
        scope: [
          "entity.name.function",
          "support.function",
          "meta.function-call.generic",
          "variable.function",
        ],
        settings: { foreground: p.func },
      },
      {
        scope: [
          "entity.name.type",
          "entity.name.class",
          "entity.other.inherited-class",
          "support.class",
          "support.type",
        ],
        settings: { foreground: p.type },
      },
      {
        scope: [
          "entity.name.function.decorator",
          "meta.function.decorator",
          "punctuation.definition.decorator",
        ],
        settings: { foreground: p.decorator },
      },

      {
        scope: ["punctuation", "meta.brace", "punctuation.separator", "punctuation.terminator"],
        settings: { foreground: p.punctuation },
      },

      { scope: ["variable", "variable.parameter", "meta.attribute"], settings: { foreground: p.base } },

      // Config and prose files land in this pane too — enough of a mapping that
      // a README or a pyproject.toml is not a wall of one colour.
      { scope: ["entity.name.tag", "support.type.property-name"], settings: { foreground: p.func } },
      { scope: ["markup.heading", "entity.name.section"], settings: { foreground: p.func, fontStyle: "bold" } },
      { scope: ["markup.bold"], settings: { fontStyle: "bold" } },
      { scope: ["markup.italic"], settings: { fontStyle: "italic" } },
      { scope: ["markup.inline.raw", "markup.fenced_code"], settings: { foreground: p.string } },
      { scope: ["markup.underline.link", "string.other.link"], settings: { foreground: p.decorator } },

      { scope: ["invalid", "invalid.illegal"], settings: { foreground: p.invalid } },
    ],
  };
}

export const CODE_THEME_DARK = build(DARK_THEME_NAME, "dark", DARK);
export const CODE_THEME_LIGHT = build(LIGHT_THEME_NAME, "light", LIGHT);
