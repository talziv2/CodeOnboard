import { describe, expect, test } from "vitest";
import { hasMarkup, parseBlocks, parseInline, type Block, type Inline } from "@/lib/markdown";

/**
 * The markdown subset, and the two properties that actually matter.
 *
 * A parser is easy to test into a false sense of safety by feeding it the markdown
 * you had in mind. The cases that earn their place here are the ones where a
 * parser is more dangerous than no parser at all: prose that must come through
 * UNTOUCHED. `astar_search`, `__init__`, `2 * 3 * 4` — the vocabulary of a Python
 * lesson is full of characters CommonMark treats as delimiters, and the failure
 * mode is not a stray asterisk, it is half a paragraph silently turning italic.
 * That is the first half of this file.
 *
 * The second half is the markup the models actually write, which is where the
 * complaint came from: `**Anchor 1:**` and backticked identifiers in a question.
 */

/** The rendered text of an inline tree, delimiters and all, for round-trip checks. */
function flatten(nodes: Inline[]): string {
  return nodes
    .map((n) => {
      switch (n.kind) {
        case "text":
          return n.text;
        case "code":
          return n.text;
        default:
          return flatten(n.content);
      }
    })
    .join("");
}

const kinds = (nodes: Inline[]) => nodes.map((n) => n.kind);
const blockKinds = (blocks: Block[]) => blocks.map((b) => b.kind);

describe("prose that must survive untouched", () => {
  // The reason `_` is not an emphasis delimiter at all. Every one of these is a
  // real identifier from this codebase or its target repos.
  test.each([
    "line_start and line_end are derived",
    "resolve the __init__ re-exports",
    "call _read_source_lines(repo_path, file, start, end)",
    "astar_search(problem) builds a tree of Node objects",
    "goal_type is understand_component here",
  ])("underscores are never emphasis: %s", (src) => {
    const nodes = parseInline(src);
    expect(kinds(nodes)).toEqual(["text"]);
    expect(flatten(nodes)).toBe(src);
  });

  test("arithmetic is not emphasis — a delimiter needs non-space content", () => {
    const nodes = parseInline("the cost is 2 * 3 * 4 per line");
    expect(kinds(nodes)).toEqual(["text"]);
    expect(flatten(nodes)).toBe("the cost is 2 * 3 * 4 per line");
  });

  test("an unclosed delimiter is literal, not an open run to the end of the line", () => {
    expect(flatten(parseInline("a * b and nothing closes it"))).toBe(
      "a * b and nothing closes it"
    );
    expect(flatten(parseInline("an `unterminated span"))).toBe("an `unterminated span");
    expect(kinds(parseInline("an `unterminated span"))).toEqual(["text"]);
  });

  test("a code span protects the asterisks inside it", () => {
    const nodes = parseInline("pass them as `**kwargs` to the adapter");
    expect(kinds(nodes)).toEqual(["text", "code", "text"]);
    expect(nodes[1]).toEqual({ kind: "code", text: "**kwargs" });
  });

  test("plain prose reports no markup at all", () => {
    expect(hasMarkup("The Session object owns connection reuse and cookies.")).toBe(false);
    expect(hasMarkup("Nodes are stored and looked up by hashing their state.")).toBe(false);
  });

  test("a backslash escape yields the character, not the delimiter", () => {
    expect(flatten(parseInline("a literal \\*star\\* here"))).toBe("a literal *star* here");
    expect(kinds(parseInline("a literal \\*star\\* here"))).toEqual(["text"]);
  });
});

describe("the markup the models write", () => {
  test("the reported case: a bolded lead and a backticked call", () => {
    const nodes = parseInline("**Anchor 1:** `astar_search(problem)` builds the tree");
    expect(kinds(nodes)).toEqual(["strong", "text", "code", "text"]);
    expect(flatten([nodes[0]])).toBe("Anchor 1:");
    expect(nodes[2]).toEqual({ kind: "code", text: "astar_search(problem)" });
  });

  test("bold and italic nest and recurse", () => {
    const nodes = parseInline("**bold with *inner* emphasis**");
    expect(kinds(nodes)).toEqual(["strong"]);
    const inner = (nodes[0] as Extract<Inline, { kind: "strong" }>).content;
    expect(kinds(inner)).toEqual(["text", "em", "text"]);
  });

  test("a safe link parses; an unsafe scheme stays text", () => {
    const ok = parseInline("see [the docs](https://example.com/x) for more");
    expect(kinds(ok)).toEqual(["text", "link", "text"]);
    expect((ok[1] as Extract<Inline, { kind: "link" }>).href).toBe("https://example.com/x");

    const bad = parseInline("see [the docs](javascript:alert(1)) for more");
    expect(bad.every((n) => n.kind === "text")).toBe(true);
    expect(flatten(bad)).toBe("see [the docs](javascript:alert(1)) for more");
  });
});

describe("blocks", () => {
  test("a blank line separates paragraphs; a soft newline joins with a space", () => {
    const blocks = parseBlocks(
      "Nodes are stored and looked up\nby hashing their state.\n\nGoal testing compares it."
    );
    expect(blockKinds(blocks)).toEqual(["paragraph", "paragraph"]);
    expect(flatten((blocks[0] as Extract<Block, { kind: "paragraph" }>).content)).toBe(
      "Nodes are stored and looked up by hashing their state."
    );
  });

  test("headings carry their level", () => {
    const blocks = parseBlocks("## What it owns\n\nprose\n\n#### A label");
    expect(blocks[0]).toMatchObject({ kind: "heading", level: 2 });
    expect(blocks[2]).toMatchObject({ kind: "heading", level: 4 });
  });

  test("a fence keeps its lines verbatim and reports its language", () => {
    const blocks = parseBlocks("before\n\n```python\ndef f(x):\n    return x * 2\n```\n\nafter");
    expect(blockKinds(blocks)).toEqual(["paragraph", "fence", "paragraph"]);
    expect(blocks[1]).toEqual({
      kind: "fence",
      lang: "python",
      code: "def f(x):\n    return x * 2",
    });
  });

  test("bullets become one list, and indentation becomes depth", () => {
    const blocks = parseBlocks("- first\n- second\n  - nested\n- third");
    expect(blockKinds(blocks)).toEqual(["list"]);
    const list = blocks[0] as Extract<Block, { kind: "list" }>;
    expect(list.ordered).toBe(false);
    expect(list.items.map((i) => i.depth)).toEqual([0, 0, 1, 0]);
    expect(list.items.map((i) => flatten(i.content))).toEqual([
      "first",
      "second",
      "nested",
      "third",
    ]);
  });

  test("an ordered list keeps its start number", () => {
    const list = parseBlocks("3. third\n4. fourth")[0] as Extract<Block, { kind: "list" }>;
    expect(list.ordered).toBe(true);
    expect(list.start).toBe(3);
  });

  /**
   * The loose-list case, and the reason it is a rule rather than an accident. A
   * model writing three numbered steps with a blank line between each is common,
   * and treating that as three lists restarts the numbering at 1 twice — so a set
   * of steps reads as "1. 1. 1." partway down the lesson.
   */
  test("one blank line between items does not start a second list", () => {
    const blocks = parseBlocks("1. first\n\n2. second\n\n3. third");
    expect(blockKinds(blocks)).toEqual(["list"]);
    expect((blocks[0] as Extract<Block, { kind: "list" }>).items).toHaveLength(3);
  });

  test("a different marker kind does start a second list", () => {
    expect(blockKinds(parseBlocks("- bullet\n1. number"))).toEqual(["list", "list"]);
  });

  test("an unindented line after an item continues that item", () => {
    const list = parseBlocks("- the claim\n  spilling onto a second line\n- next")[0] as Extract<
      Block,
      { kind: "list" }
    >;
    expect(list.items).toHaveLength(2);
    expect(flatten(list.items[0].content)).toBe("the claim spilling onto a second line");
  });

  test("quotes and rules", () => {
    expect(blockKinds(parseBlocks("> an aside\n\n---\n\nafter"))).toEqual([
      "quote",
      "rule",
      "paragraph",
    ]);
  });

  test("empty and whitespace-only input yields no blocks", () => {
    expect(parseBlocks("")).toEqual([]);
    expect(parseBlocks("\n\n  \n")).toEqual([]);
  });

  test("CRLF is normalised, so a Windows-authored lesson parses the same", () => {
    expect(blockKinds(parseBlocks("one\r\n\r\ntwo"))).toEqual(["paragraph", "paragraph"]);
  });
});
