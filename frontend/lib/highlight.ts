/**
 * Syntax highlighting for the source pane.
 *
 * Everything here is lazy on purpose. Shiki, its regex engine and each grammar
 * are pulled in by dynamic `import()` the first time a file is actually opened,
 * so a session that never opens the pane never downloads any of it.
 *
 * The output is *tokens*, not HTML: the pane renders its own table so it can
 * keep line numbers, the highlighted band and the gutter rule. We only want the
 * colours.
 *
 * Colours are emitted as a pair of CSS variables per token (`--code-light` /
 * `--code-dark`) rather than a single resolved colour. That is what lets the
 * theme flip without re-tokenising a thousand-line file — the CSS in
 * `globals.css` picks the side, and this module stays theme-blind like every
 * other component.
 */
import { CODE_THEME_DARK, CODE_THEME_LIGHT, DARK_THEME_NAME, LIGHT_THEME_NAME } from "./code-theme";
import type { HighlighterCore } from "shiki/core";

/** One styled run of text. `style` holds the CSS custom properties, if any. */
export interface CodeToken {
  content: string;
  style?: Record<string, string>;
}

/**
 * Past this, tokenising and rendering a span per token costs more than the
 * colour is worth, and the pane falls back to plain text. Generated or vendored
 * files are the ones that hit it; a file a lesson anchors into never does.
 */
export const MAX_HIGHLIGHT_LINES = 5000;

/* Only grammars a target repository actually contains. Each is its own chunk,
   fetched on first sight of the extension and never again. */
const GRAMMARS: Record<string, () => Promise<{ default: unknown }>> = {
  python: () => import("@shikijs/langs/python"),
  markdown: () => import("@shikijs/langs/markdown"),
  json: () => import("@shikijs/langs/json"),
  yaml: () => import("@shikijs/langs/yaml"),
  toml: () => import("@shikijs/langs/toml"),
  ini: () => import("@shikijs/langs/ini"),
  shellscript: () => import("@shikijs/langs/shellscript"),
  javascript: () => import("@shikijs/langs/javascript"),
  typescript: () => import("@shikijs/langs/typescript"),
  html: () => import("@shikijs/langs/html"),
  css: () => import("@shikijs/langs/css"),
  xml: () => import("@shikijs/langs/xml"),
};

const BY_EXTENSION: Record<string, keyof typeof GRAMMARS> = {
  py: "python", pyi: "python", pyx: "python",
  md: "markdown", markdown: "markdown",
  json: "json",
  yml: "yaml", yaml: "yaml",
  toml: "toml",
  ini: "ini", cfg: "ini",
  sh: "shellscript", bash: "shellscript", zsh: "shellscript",
  js: "javascript", mjs: "javascript", cjs: "javascript", jsx: "javascript",
  ts: "typescript", mts: "typescript", cts: "typescript", tsx: "typescript",
  html: "html", htm: "html",
  css: "css",
  xml: "xml", svg: "xml",
};

/** The grammar for a repository path, or null when we have none for it. */
export function langForPath(path: string): string | null {
  const name = path.split("/").pop() ?? path;
  const dot = name.lastIndexOf(".");
  if (dot <= 0) return null;
  return BY_EXTENSION[name.slice(dot + 1).toLowerCase()] ?? null;
}

let highlighter: Promise<HighlighterCore> | null = null;
const loaded = new Set<string>();

function core(): Promise<HighlighterCore> {
  highlighter ??= (async () => {
    const [{ createHighlighterCore }, { createJavaScriptRegexEngine }] = await Promise.all([
      import("shiki/core"),
      import("@shikijs/engine-javascript"),
    ]);
    return createHighlighterCore({
      themes: [CODE_THEME_LIGHT, CODE_THEME_DARK],
      langs: [],
      // The JavaScript engine keeps us off the WASM binary, which would need
      // serving and would dwarf every grammar here. `forgiving` drops the few
      // Oniguruma constructs it can't compile instead of throwing — a rule that
      // silently doesn't match is a colour we lose, not a pane that fails.
      engine: createJavaScriptRegexEngine({ forgiving: true }),
    });
  })();
  return highlighter;
}

/**
 * Tokenise `code` as `lang`. One array per line, matching `code.split("\n")`.
 *
 * Throws if the grammar or the engine can't be fetched; the caller falls back
 * to plain text, which is exactly what the pane rendered before this existed.
 */
export async function tokenize(code: string, lang: string): Promise<CodeToken[][]> {
  const hl = await core();

  if (!loaded.has(lang)) {
    const grammar = GRAMMARS[lang];
    if (!grammar) throw new Error(`no grammar for ${lang}`);
    await hl.loadLanguage((await grammar()).default as never);
    loaded.add(lang);
  }

  const { tokens } = hl.codeToTokens(code, {
    lang,
    themes: { light: LIGHT_THEME_NAME, dark: DARK_THEME_NAME },
    // No resolved colour at all, only the variable pair — the theme is chosen
    // in CSS, at paint time.
    defaultColor: false,
    cssVariablePrefix: "--code-",
  });

  return tokens.map((line) =>
    line.map((token) => ({ content: token.content, style: token.htmlStyle }))
  );
}
