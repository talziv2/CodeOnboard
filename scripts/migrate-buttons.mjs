// One-shot migration helper for F2c. Not part of the app.
//
// Rewrites <button className="…"> to <Button variant size> ONLY where the class
// list is an exact superset of a variant+size pair. Whatever is left over after
// subtracting those classes is preserved on `className`, so layout utilities like
// `shrink-0` and `ms-auto` cannot be silently dropped — and anything left over
// that is NOT layout aborts the site, so unrecognised drift is reported rather
// than normalised away.
//
//   node scripts/migrate-buttons.mjs <combo> <file...>        # apply
//   node scripts/migrate-buttons.mjs --dry <combo> <file...>  # report only

import { readFileSync, writeFileSync } from "node:fs";

const VARIANT = {
  primary: "rounded border border-signal-dim bg-signal/15 font-medium text-signal transition hover:bg-signal/25",
  secondary: "rounded border border-rule text-graphite transition hover:border-signal-dim hover:text-signal",
  chrome: "rounded border border-rule font-mono text-graphite transition hover:border-signal-dim hover:text-signal",
  ghost: "font-mono text-[calc(10.5rem/16)] text-graphite transition hover:text-signal",
};
const SIZE = {
  xs: "px-2 py-1 text-[calc(10.5rem/16)]",
  sm: "px-3 py-1.5 text-[calc(10.5rem/16)]",
  md: "px-4 py-2 text-[calc(13rem/16)]",
  lg: "px-5 py-2.5 text-[calc(13.5rem/16)]",
  block: "py-3 text-[calc(13.5rem/16)]",
};

// Utilities that are about where a button sits, not what it looks like. Anything
// outside this set that survives the subtraction means the site is not an exact
// match and must be looked at by hand.
const LAYOUT = /^(shrink-0|grow|w-fit|w-full|ms-auto|me-auto|mx-auto|mt-[\d.]+|mb-[\d.]+|ms-[\d.]+|me-[\d.]+|self-\w+|block|flex|inline-flex|items-\w+|justify-\w+|gap-[\d.]+|min-w-0|max-w-\w+|truncate|text-start|text-center|relative|z-\d+)$/;

const args = process.argv.slice(2);
const dry = args[0] === "--dry";
const combo = args[dry ? 1 : 0];
const files = args.slice(dry ? 2 : 1);
const [vName, sName] = combo.split(".");
const want = new Set([...VARIANT[vName].split(" "), ...(sName ? SIZE[sName].split(" ") : [])]);

/** End index of the opening tag, respecting quotes and {} expressions. */
function endOfOpenTag(s, i) {
  let depth = 0, q = null;
  for (let j = i; j < s.length; j++) {
    const c = s[j];
    if (q) { if (c === q && s[j - 1] !== "\\") q = null; continue; }
    if (c === '"' || c === "'" || c === "`") { q = c; continue; }
    if (c === "{") depth++;
    else if (c === "}") depth--;
    else if (c === ">" && depth === 0) return j;
  }
  return -1;
}

let migrated = 0, skipped = [];
for (const file of files) {
  let s = readFileSync(file, "utf8");
  let out = "", cursor = 0, changed = false;

  for (let i = s.indexOf("<button", cursor); i !== -1; i = s.indexOf("<button", cursor)) {
    const end = endOfOpenTag(s, i);
    if (end === -1) break;
    const tag = s.slice(i, end + 1);
    const line = s.slice(0, i).split("\n").length;

    const m = tag.match(/\sclassName="([^"]*)"/);
    if (!m) { out += s.slice(cursor, end + 1); cursor = end + 1; continue; }

    const tokens = m[1].split(/\s+/).filter(Boolean);
    const have = new Set(tokens);
    const missing = [...want].filter((w) => !have.has(w));
    const leftover = tokens.filter((tk) => !want.has(tk));
    const notLayout = leftover.filter((tk) => !LAYOUT.test(tk));

    if (missing.length || notLayout.length) {
      if (missing.length === 0) {
        skipped.push(`${file}:${line}  UNRECOGNISED: ${notLayout.join(" ")}`);
      }
      out += s.slice(cursor, end + 1); cursor = end + 1; continue;
    }

    // rewrite: drop className, add variant/size, keep layout leftovers
    let newTag = tag.replace(/\sclassName="[^"]*"/, "");
    newTag = newTag.replace(/^<button/, "<Button");
    const props = [`variant="${vName}"`, sName ? `size="${sName}"` : null,
                   leftover.length ? `className="${leftover.join(" ")}"` : null]
      .filter(Boolean).join(" ");
    newTag = newTag.replace(/^<Button/, `<Button ${props}`);

    // pair the closing tag — buttons never nest
    const close = s.indexOf("</button>", end);
    if (close === -1) { out += s.slice(cursor, end + 1); cursor = end + 1; continue; }

    out += s.slice(cursor, i) + newTag + s.slice(end + 1, close) + "</Button>";
    cursor = close + "</button>".length;
    migrated++; changed = true;
    console.log(`  ${file}:${line}${leftover.length ? "  kept: " + leftover.join(" ") : ""}`);
  }
  out += s.slice(cursor);
  if (changed && !dry) writeFileSync(file, out, "utf8");
}

console.log(`\n${dry ? "would migrate" : "migrated"} ${migrated} site(s) as ${combo}`);
if (skipped.length) {
  console.log("\nNOT migrated — class list is a superset but carries non-layout classes:");
  skipped.forEach((x) => console.log("  " + x));
}
