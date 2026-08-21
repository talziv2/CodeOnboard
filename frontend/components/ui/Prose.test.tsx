import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import Prose, { InlineProse } from "@/components/ui/Prose";

/**
 * What reaches the screen.
 *
 * The parser has its own tests; these assert the two things a reader of the app
 * would check by looking at it. THE SYNTAX IS GONE — no `**`, no backticks, no
 * `##` anywhere in the rendered text — and the meaning arrived, as real elements
 * a screen reader can announce as emphasis and code rather than as chalk-coloured
 * spans that merely look bold.
 *
 * The negative assertion is the important one. A renderer that emitted `<strong>`
 * AND left the asterisks in would pass every positive check here.
 */

/** The whole rendered text, which is what the learner reads. */
const text = (el: HTMLElement) => el.textContent ?? "";

describe("Prose", () => {
  test("bold becomes emphasis and its delimiters disappear", () => {
    const { container } = render(<Prose text="**Anchor 1:** nodes are hashed" />);
    expect(container.querySelector("strong")?.textContent).toBe("Anchor 1:");
    expect(text(container)).toBe("Anchor 1: nodes are hashed");
    expect(text(container)).not.toContain("*");
  });

  test("an identifier becomes a code element, not backticks", () => {
    const { container } = render(<Prose text="call `astar_search(problem)` first" />);
    const code = container.querySelector("code");
    expect(code?.textContent).toBe("astar_search(problem)");
    expect(text(container)).not.toContain("`");
  });

  test("a heading renders as a heading, capped below the stop title", () => {
    const { container } = render(<Prose text={"## What it owns\n\nprose"} />);
    // Level 2 is an `h3`: the stop's own title is the `h2` on the page, and a
    // lesson's heading may not compete with it.
    expect(container.querySelector("h3")?.textContent).toBe("What it owns");
    expect(text(container)).not.toContain("#");
  });

  test("a bulleted list renders list items, no asterisks or hyphens left over", () => {
    const { container } = render(
      <Prose text={"- states are hashed\n- states are compared"} />
    );
    const items = container.querySelectorAll("li");
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toBe("states are hashed");
    expect(container.querySelector("ul")).not.toBeNull();
  });

  /**
   * Numbering runs per depth. A sub-step continuing its parent's count — "1, 2,
   * 3" where the 3 is nested under the 2 — is the kind of wrong that reads as a
   * missing step rather than as a styling bug.
   */
  test("nested ordered items restart their numbering", () => {
    const { container } = render(
      <Prose text={"1. first\n2. second\n  1. detail\n3. third"} />
    );
    const numbers = [...container.querySelectorAll("li > span:first-child")].map(
      (s) => s.textContent
    );
    expect(numbers).toEqual(["1.", "2.", "1.", "3."]);
  });

  test("an ordered list starting at 3 renders 3", () => {
    const { container } = render(<Prose text={"3. third\n4. fourth"} />);
    expect(container.querySelector("li > span:first-child")?.textContent).toBe("3.");
  });

  test("a fence renders as a pre block with its lines intact", () => {
    const { container } = render(
      <Prose text={"```python\ndef f(x):\n    return x\n```"} />
    );
    const pre = container.querySelector("pre");
    expect(pre).not.toBeNull();
    expect(pre?.textContent).toContain("def f(x):");
    expect(text(container)).not.toContain("```");
  });

  test("a link is rendered as an anchor to its target", () => {
    render(<Prose text="see [the docs](https://example.com/x)" />);
    const link = screen.getByRole("link", { name: "the docs" });
    expect(link.getAttribute("href")).toBe("https://example.com/x");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  test("plain prose renders as one paragraph and reads identically", () => {
    const body = "The Session object owns connection reuse, cookies and defaults.";
    const { container } = render(<Prose text={body} />);
    expect(container.querySelectorAll("p")).toHaveLength(1);
    expect(text(container)).toBe(body);
  });

  test("nothing renders for empty or absent text", () => {
    expect(render(<Prose text="" />).container.textContent).toBe("");
    expect(render(<Prose text={null} />).container.textContent).toBe("");
    expect(render(<Prose text={"   \n  "} />).container.textContent).toBe("");
  });
});

describe("InlineProse", () => {
  /**
   * No block wrapper, ever. The call sites are elements whose classes the caller
   * chose — the brief's `line-clamp-2` objective, a gap's struck-through claim —
   * and a `<p>` or a flex column inside them would break the clamp and the
   * strike.
   */
  test("emits spans only — no paragraph, no list, no column", () => {
    const { container } = render(
      <span>
        <InlineProse text="a `state` must be **hashable**" />
      </span>
    );
    expect(container.querySelector("p")).toBeNull();
    expect(container.querySelector("div")).toBeNull();
    expect(container.querySelector("code")?.textContent).toBe("state");
    expect(container.querySelector("strong")?.textContent).toBe("hashable");
    expect(text(container)).toBe("a state must be hashable");
  });

  test("the inherit tone emphasises by weight and sets no colour", () => {
    const { container } = render(<InlineProse text="**cleared**" tone="inherit" />);
    const strong = container.querySelector("strong");
    expect(strong?.className).toContain("font-medium");
    // The verdict's colour is an inline style on the element above; a bolded
    // clause repainting itself `chalk` would drop the classification.
    expect(strong?.className).not.toContain("text-chalk");
  });
});
