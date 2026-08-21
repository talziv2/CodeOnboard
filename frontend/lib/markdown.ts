/**
 * The markdown the lesson is actually written in — parsed, not printed.
 *
 * `backend/agents/teaching/agent.py` promises markdown for `setup` and `reveal`,
 * and the models deliver it: `**Anchor 1:**`, `` `astar_search(problem)` ``,
 * numbered steps, the occasional fenced snippet. The frontend rendered all of it
 * as `whitespace-pre-wrap` text, so the learner read the syntax instead of the
 * emphasis — asterisks around a heading, backticks around every identifier. That
 * is the defect this module exists to fix. It is not a general markdown engine and
 * must not become one; it is the subset a teaching agent writes.
 *
 * THIS PARSER IS PURE AND RETURNS DATA, never HTML. Nothing here builds a string
 * that a component then trusts, so `dangerouslySetInnerHTML` never enters the
 * picture and model output cannot inject markup. `components/ui/Prose.tsx` turns
 * these nodes into elements.
 *
 * Three subset decisions are load-bearing:
 *
 * `_` IS NEVER EMPHASIS. Only `*` and `**`. This is a Python-teaching product:
 * `line_start`, `astar_search`, `__init__` and `_read_source_lines` are the
 * vocabulary, and CommonMark's word-boundary rules for `_` are subtle enough that
 * the first identifier to straddle them would silently italicise half a sentence.
 * Refusing the delimiter outright is one rule a reader of this file can hold.
 *
 * A SOFT NEWLINE JOINS WITH A SPACE, the standard behaviour, rather than becoming
 * a `<br>`. The old `pre-wrap` rendering made every newline a break, which was
 * indistinguishable from correct only because the models separate paragraphs with
 * a blank line. Where one hard-wraps mid-sentence instead, the standard rule gives
 * clean prose and the pre-wrap rule gives a ragged column.
 *
 * AN UNCLOSED DELIMITER IS LITERAL TEXT. A lone `*` or an unterminated backtick
 * renders as itself. Prose that half-parses is worse than prose that does not:
 * the failure has to be visible as a stray character, not as the rest of the
 * paragraph turning into code.
 */

/** One styled run inside a line of prose. */
export type Inline =
  | { kind: "text"; text: string }
  | { kind: "code"; text: string }
  | { kind: "strong"; content: Inline[] }
  | { kind: "em"; content: Inline[] }
  | { kind: "link"; href: string; content: Inline[] };

/**
 * A list row. `depth` is indentation in nesting levels, kept as a number rather
 * than as a nested list: a tree would need the renderer to recurse, and one flat
 * pass with an indent is the whole of what a teaching agent's nesting needs.
 */
export interface ListItem {
  content: Inline[];
  depth: number;
}

export type Block =
  | { kind: "paragraph"; content: Inline[] }
  | { kind: "heading"; level: number; content: Inline[] }
  | { kind: "quote"; content: Inline[] }
  | { kind: "list"; ordered: boolean; start: number; items: ListItem[] }
  | { kind: "fence"; lang: string | null; code: string }
  | { kind: "rule" };

/**
 * Schemes a link may use. Everything else — `javascript:`, `data:` — falls back
 * to literal text, because the label and target both come from a model and a
 * link is the one inline node that does something when clicked.
 */
const SAFE_HREF = /^(?:https?:\/\/|mailto:|\/|#)/i;

/** Characters a backslash may escape. Matches CommonMark's punctuation set, trimmed. */
const ESCAPABLE = "\\`*_[]()#+-.!>~|";

// ── inline ───────────────────────────────────────────────────────────────────

/**
 * Parse one run of prose into styled spans.
 *
 * Exported on its own because several call sites hold a single line that is
 * already inside an element they own — a gap's claim, the verdict headline, the
 * pinned objective — and want the emphasis without a block wrapper.
 */
export function parseInline(src: string): Inline[] {
  const out: Inline[] = [];
  let text = "";
  const flush = () => {
    if (text) out.push({ kind: "text", text });
    text = "";
  };

  let i = 0;
  while (i < src.length) {
    const ch = src[i];

    if (ch === "\\" && i + 1 < src.length && ESCAPABLE.includes(src[i + 1])) {
      text += src[i + 1];
      i += 2;
      continue;
    }

    // Code first, and therefore strongest: a backtick run protects everything
    // inside it, which is what lets a lesson quote `**kwargs` without the
    // asterisks becoming emphasis.
    if (ch === "`") {
      let n = 0;
      while (src[i + n] === "`") n++;
      const fence = "`".repeat(n);
      const close = src.indexOf(fence, i + n);
      if (close !== -1) {
        flush();
        let code = src.slice(i + n, close);
        // One padding space on each side is a delimiter, not content — that is
        // how ``` ` ``` writes a literal backtick.
        if (code.length > 2 && code.startsWith(" ") && code.endsWith(" ") && code.trim()) {
          code = code.slice(1, -1);
        }
        out.push({ kind: "code", text: code });
        i = close + n;
        continue;
      }
      text += fence;
      i += n;
      continue;
    }

    if (ch === "*") {
      const strong = src.startsWith("**", i);
      const delim = strong ? "**" : "*";
      const end = closingDelimiter(src, i + delim.length, delim);
      if (end !== -1) {
        flush();
        const content = parseInline(src.slice(i + delim.length, end));
        out.push(strong ? { kind: "strong", content } : { kind: "em", content });
        i = end + delim.length;
        continue;
      }
      text += ch;
      i += 1;
      continue;
    }

    if (ch === "[") {
      const link = matchLink(src, i);
      if (link) {
        flush();
        out.push(link.node);
        i = link.next;
        continue;
      }
    }

    text += ch;
    i += 1;
  }

  flush();
  return out;
}

/**
 * Where `delim` closes the run that opened at `from`, or -1 if it never does.
 *
 * The two guards are the ones that keep ordinary prose out of emphasis: content
 * may not begin or end with whitespace (so `2 * 3 * 4` stays arithmetic), and a
 * single `*` skips over a `**` run rather than eating half of it.
 */
function closingDelimiter(src: string, from: number, delim: string): number {
  if (from >= src.length || /\s/.test(src[from])) return -1;

  let i = from;
  while (i < src.length) {
    const at = src.indexOf(delim, i);
    if (at === -1 || at === from) return -1;
    if (delim === "*" && src[at + 1] === "*") {
      i = at + 2;
      continue;
    }
    if (/\s/.test(src[at - 1])) {
      i = at + delim.length;
      continue;
    }
    return at;
  }
  return -1;
}

/** `[label](href)` at `i`, with balanced brackets in the label. */
function matchLink(src: string, i: number): { node: Inline; next: number } | null {
  let depth = 0;
  let j = i;
  for (; j < src.length; j++) {
    if (src[j] === "\\") {
      j += 1;
      continue;
    }
    if (src[j] === "[") depth += 1;
    else if (src[j] === "]") {
      depth -= 1;
      if (depth === 0) break;
    }
  }
  if (j >= src.length || src[j + 1] !== "(") return null;

  const close = src.indexOf(")", j + 2);
  if (close === -1) return null;

  // A title after the target (`(url "title")`) is dropped; nothing displays it.
  const href = src.slice(j + 2, close).trim().split(/\s+/)[0] ?? "";
  if (!SAFE_HREF.test(href)) return null;

  return {
    node: { kind: "link", href, content: parseInline(src.slice(i + 1, j)) },
    next: close + 1,
  };
}

// ── blocks ───────────────────────────────────────────────────────────────────

const FENCE = /^ {0,3}(`{3,}|~{3,})\s*([^\s`]*)/;
const HEADING = /^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
const RULE = /^ {0,3}(?:-{3,}|\*{3,}|_{3,})\s*$/;
const BULLET = /^(\s*)[-*+]\s+(.*)$/;
const ORDERED = /^(\s*)(\d{1,9})[.)]\s+(.*)$/;
const QUOTE = /^ {0,3}>\s?(.*)$/;

/** Two spaces of indent per nesting level, which is what models emit. */
const INDENT_PER_LEVEL = 2;

/** Deepest nesting rendered. Beyond this the indent costs more than it says. */
const MAX_DEPTH = 3;

/**
 * Parse a markdown document into blocks.
 *
 * One forward pass with a small accumulator per open block. The only non-obvious
 * rule is that a single blank line between two list items of the same kind does
 * NOT start a second list — models write loose lists constantly, and splitting
 * them restarts the numbering at 1 partway down a set of steps.
 */
export function parseBlocks(src: string): Block[] {
  const blocks: Block[] = [];
  const lines = (src ?? "").replace(/\r\n?/g, "\n").split("\n");

  // Open accumulators. At most one is non-empty at a time.
  let para: string[] = [];
  let quote: string[] = [];
  let list: { ordered: boolean; start: number; items: ListItem[] } | null = null;
  let blank = false;

  const closeParagraph = () => {
    if (para.length) blocks.push({ kind: "paragraph", content: parseInline(para.join(" ")) });
    para = [];
  };
  const closeQuote = () => {
    if (quote.length) blocks.push({ kind: "quote", content: parseInline(quote.join(" ")) });
    quote = [];
  };
  const closeList = () => {
    if (list) blocks.push({ kind: "list", ...list });
    list = null;
  };
  const closeAll = () => {
    closeParagraph();
    closeQuote();
    closeList();
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (!line.trim()) {
      closeParagraph();
      closeQuote();
      // The list stays open across ONE blank line; the next non-item closes it.
      blank = true;
      continue;
    }

    const fence = FENCE.exec(line);
    if (fence) {
      closeAll();
      const marker = fence[1][0].repeat(3);
      const code: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].trimStart().startsWith(marker)) {
        code.push(lines[i]);
        i += 1;
      }
      blocks.push({ kind: "fence", lang: fence[2] || null, code: code.join("\n") });
      blank = false;
      continue;
    }

    if (RULE.test(line)) {
      closeAll();
      blocks.push({ kind: "rule" });
      blank = false;
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      closeAll();
      blocks.push({
        kind: "heading",
        level: heading[1].length,
        content: parseInline(heading[2]),
      });
      blank = false;
      continue;
    }

    const quoted = QUOTE.exec(line);
    if (quoted) {
      closeParagraph();
      closeList();
      quote.push(quoted[1]);
      blank = false;
      continue;
    }

    const ordered = ORDERED.exec(line);
    const bullet = ordered ? null : BULLET.exec(line);
    if (ordered || bullet) {
      closeParagraph();
      closeQuote();
      const indent = (ordered ?? bullet!)[1].length;
      const depth = Math.min(Math.floor(indent / INDENT_PER_LEVEL), MAX_DEPTH);
      const body = ordered ? ordered[3] : bullet![2];
      const isOrdered = Boolean(ordered);

      // A different kind of list is a different list, blank line or not.
      if (list && list.ordered !== isOrdered) closeList();
      list ??= {
        ordered: isOrdered,
        start: ordered ? Number(ordered[2]) : 1,
        items: [],
      };
      list.items.push({ content: parseInline(body), depth });
      blank = false;
      continue;
    }

    // Plain prose. Inside an open list with no blank line before it, this is the
    // continuation of the last item rather than a new paragraph.
    if (list && !blank) {
      const last = list.items[list.items.length - 1];
      list.items[list.items.length - 1] = {
        ...last,
        content: [...last.content, { kind: "text", text: " " }, ...parseInline(line.trim())],
      };
      continue;
    }

    closeList();
    closeQuote();
    para.push(line.trim());
    blank = false;
  }

  closeAll();
  return blocks;
}

/**
 * Whether a string carries any markup this module would render differently from
 * plain text.
 *
 * Used by nothing on the render path — parsing is cheap enough that no call site
 * needs to guard — but it is what the tests assert the "plain prose is untouched"
 * property with, and it is the honest way to answer "does this need Prose?".
 */
export function hasMarkup(src: string): boolean {
  const blocks = parseBlocks(src);
  if (blocks.length !== 1) return true;
  const only = blocks[0];
  if (only.kind !== "paragraph") return true;
  return only.content.some((node) => node.kind !== "text");
}
