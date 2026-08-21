"use client";

import { parseBlocks, parseInline, type Block, type Inline } from "@/lib/markdown";
import ProseCode from "@/components/ui/ProseCode";

/**
 * Model-authored prose, set the way the design system sets prose.
 *
 * Every long-form string a learner reads came out of a model that was asked for
 * markdown, and until this existed the frontend printed the markdown. So the
 * emphasis a teaching agent put on the one clause that matters arrived as a pair
 * of asterisks, and every identifier arrived wrapped in backticks — the two
 * devices that carry the most meaning in a code lesson were the two that read as
 * noise. This renders them.
 *
 * ── What the styling is for ───────────────────────────────────────────────────
 *
 * Nothing here invents a scale. Emphasis moves UP THE EXISTING LADDER — the
 * palette's `paper → chalk` step, which is the same step the app already uses to
 * mean "this line matters more than the one above it" — rather than reaching for
 * a colour. Accent stays out of prose entirely: `signal` means "you are here" and
 * a bolded phrase is not a location.
 *
 * INLINE CODE IS THE ONE EXCEPTION TO QUIET. An identifier in a sentence is the
 * thing the sentence is about, and it gets the chip treatment — mono, `chalk`,
 * on `trench` inside a hairline — because in this product the difference between
 * prose about code and the code itself is the distinction the learner is being
 * taught to make. It nests on `trench` for the same reason the composer does.
 *
 * HEADINGS ARE CAPPED BELOW THE STOP TITLE. A lesson's `##` cannot outweigh the
 * `text-head` serif title of the stop it lives inside, so level 1–2 lands one
 * step below at `text-lede`, 3 at body weight, and 4+ becomes the mono eyebrow
 * the rest of the app uses for a label. A model that opens with `# Overview`
 * therefore cannot produce two competing page titles.
 *
 * ── Two entry points ──────────────────────────────────────────────────────────
 *
 * `Prose` renders blocks and owns its own column: paragraphs, lists, quotes,
 * fences, each capped at `.measure`. Use it wherever a `<p className="measure
 * whitespace-pre-wrap">` used to be.
 *
 * `InlineProse` renders spans only and no wrapper at all, for the call sites that
 * hold one line inside an element whose classes they already chose — the pinned
 * objective, a gap's claim, the verdict headline. Those are single lines by
 * contract, so giving them block layout would be inventing structure the string
 * does not have, and it would break the `line-clamp` the brief depends on.
 *
 * LEARNER-WRITTEN TEXT IS NOT PROSE. An attempt's answer and a check's answer are
 * rendered as they were typed, `whitespace-pre-wrap`, everywhere. Interpreting a
 * learner's asterisk as emphasis silently rewrites what they said, and the one
 * place their own words appear is the one place fidelity beats polish.
 */

type Size = "lede" | "body" | "aside" | "meta";
/**
 * `inherit` takes its colour from the element around it and emphasises by weight
 * alone. It exists for the verdict headline, whose colour is the classification —
 * a bolded phrase there must not repaint itself `chalk` and lose the verdict.
 */
type Tone = "chalk" | "paper" | "graphite" | "inherit";

const TEXT: Record<Size, string> = {
  lede: "text-lede",
  body: "text-body",
  aside: "text-aside",
  meta: "text-meta",
};

/** Air between blocks, proportional to the line height of the size it separates. */
const GAP: Record<Size, string> = {
  lede: "gap-4",
  body: "gap-4",
  aside: "gap-3",
  meta: "gap-2",
};

/** Spelled out rather than interpolated: Tailwind only sees literal class names. */
const COLOR: Record<Tone, string> = {
  chalk: "text-chalk",
  paper: "text-paper",
  graphite: "text-graphite",
  inherit: "",
};

/**
 * Where emphasis goes from each tone: one step up the ladder, never a colour.
 * `chalk` is already the top, so bold there is weight alone.
 */
const EMPHASIS: Record<Tone, string> = {
  chalk: "font-medium text-chalk",
  paper: "font-medium text-chalk",
  graphite: "font-medium text-paper",
  inherit: "font-medium",
};

export default function Prose({
  text,
  size = "body",
  tone = "paper",
  className = "",
}: {
  text: string | null | undefined;
  size?: Size;
  tone?: Tone;
  /** Layout belonging to the surrounding flow, not to the prose. */
  className?: string;
}) {
  if (!text?.trim()) return null;
  const blocks = parseBlocks(text);
  const emphasis = EMPHASIS[tone];

  return (
    <div className={`flex flex-col ${GAP[size]} ${TEXT[size]} ${COLOR[tone]} ${className}`}>
      {blocks.map((block, i) => (
        <BlockNode key={i} block={block} emphasis={emphasis} />
      ))}
    </div>
  );
}

/** Spans with no wrapper, for a line whose element the caller already owns. */
export function InlineProse({
  text,
  tone = "paper",
}: {
  text: string | null | undefined;
  tone?: Tone;
}) {
  if (!text) return null;
  return <Spans nodes={parseInline(text)} emphasis={EMPHASIS[tone]} />;
}

function BlockNode({ block, emphasis }: { block: Block; emphasis: string }) {
  switch (block.kind) {
    case "paragraph":
      return (
        <p className="measure">
          <Spans nodes={block.content} emphasis={emphasis} />
        </p>
      );

    case "heading":
      return <Heading block={block} emphasis={emphasis} />;

    case "quote":
      // The same shape `why_now` already uses: a rule down the inline edge, not a
      // tinted box. A callout is for something the system is saying; a quote is
      // still the lesson's own voice, one step aside.
      return (
        <blockquote className="measure border-s-2 border-rule ps-3 italic text-graphite">
          <Spans nodes={block.content} emphasis={emphasis} />
        </blockquote>
      );

    case "list":
      return <List block={block} emphasis={emphasis} />;

    case "fence":
      return <ProseCode code={block.code} lang={block.lang} />;

    case "rule":
      return <hr className="border-0 border-t border-rule" />;
  }
}

function Heading({
  block,
  emphasis,
}: {
  block: Extract<Block, { kind: "heading" }>;
  emphasis: string;
}) {
  const spans = <Spans nodes={block.content} emphasis={emphasis} />;

  // Deep levels become the app's label eyebrow rather than smaller prose: past
  // three levels a model is naming a section, not titling one.
  if (block.level >= 4) {
    return (
      <div className="mt-1 flex items-center gap-2.5 first:mt-0">
        <span className="font-mono text-micro uppercase tracking-[0.16em] text-graphite">
          {spans}
        </span>
        <span aria-hidden className="h-px flex-1 bg-rule" />
      </div>
    );
  }

  if (block.level === 3) {
    return <h4 className="measure mt-1 font-medium text-chalk first:mt-0">{spans}</h4>;
  }

  return (
    <h3 className="measure mt-1 font-display text-lede font-medium tracking-tight text-chalk first:mt-0">
      {spans}
    </h3>
  );
}

function List({
  block,
  emphasis,
}: {
  block: Extract<Block, { kind: "list" }>;
  emphasis: string;
}) {
  const Tag = block.ordered ? "ol" : "ul";

  // Numbering runs per depth, so an indented sub-step starts at 1 instead of
  // continuing its parent's count.
  const seen = new Map<number, number>();
  const numbers = block.items.map((item) => {
    const n = (seen.get(item.depth) ?? block.start - 1) + 1;
    seen.set(item.depth, n);
    return n;
  });

  return (
    <Tag className="measure flex flex-col gap-2">
      {block.items.map((item, i) => (
        <li
          key={i}
          className={`grid gap-x-2.5 ${block.ordered ? "grid-cols-[1.4em_1fr]" : "grid-cols-[0.7em_1fr]"}`}
          style={item.depth ? { paddingInlineStart: `${item.depth * 1.15}em` } : undefined}
        >
          {block.ordered ? (
            <span className="font-mono text-[0.85em] tabular-nums text-graphite">
              {numbers[i]}.
            </span>
          ) : (
            // A square, not a bullet: the palette is a survey instrument and a
            // tick mark belongs to it in a way a typographic dot does not. Held
            // at the first line's optical centre so a wrapped item still aligns.
            <span
              aria-hidden
              className="mt-[0.58em] h-[0.28em] w-[0.28em] justify-self-center rounded-[1px] bg-graphite"
            />
          )}
          <span className="min-w-0">
            <Spans nodes={item.content} emphasis={emphasis} />
          </span>
        </li>
      ))}
    </Tag>
  );
}

function Spans({ nodes, emphasis }: { nodes: Inline[]; emphasis: string }) {
  return (
    <>
      {nodes.map((node, i) => (
        <Span key={i} node={node} emphasis={emphasis} />
      ))}
    </>
  );
}

function Span({ node, emphasis }: { node: Inline; emphasis: string }) {
  switch (node.kind) {
    case "text":
      return <>{node.text}</>;

    case "code":
      return (
        // `0.9em`, not a step off the scale: this has to track whatever size the
        // prose around it is set at, and Geist Mono runs wide enough that a
        // matched size reads as larger than the sentence it sits in.
        <code className="rounded-chip border border-rule bg-trench px-[0.32em] py-[0.08em] font-mono text-[0.9em] text-chalk">
          {node.text}
        </code>
      );

    case "strong":
      return (
        <strong className={emphasis}>
          <Spans nodes={node.content} emphasis={emphasis} />
        </strong>
      );

    case "em":
      return (
        <em className="italic">
          <Spans nodes={node.content} emphasis={emphasis} />
        </em>
      );

    case "link":
      return (
        // The dashed underline the file citations already use, so a link out and
        // a link into the source read as the same kind of affordance.
        <a
          href={node.href}
          target="_blank"
          rel="noopener noreferrer"
          className="border-b border-dashed border-signal-dim text-signal transition hover:border-signal"
        >
          <Spans nodes={node.content} emphasis={emphasis} />
        </a>
      );
  }
}
