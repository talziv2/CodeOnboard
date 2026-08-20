// UX probe — paste this whole file into the browser console on any CodeOnboard page.
//
//   Windows:  type scripts\ux-probe.js | clip     (then paste into DevTools)
//   or just open the file and copy it.
//
// Measures the handful of things only a real rendered page can answer, each tied
// to a specific finding in docs/planning/phases/ui-baseline.md:
//
//   contrast   every visible text run vs its COMPOSITED background   (§10.1)
//   inputs     duplicate answer boxes / duplicate button labels      (§10.1b)
//   type       how many distinct font sizes, and their spread        (§10.4)
//   radius     the radius census                                     (§10.5)
//   header     overflow, and the width left for the goal statement   (§10.2)
//   scroll     workspace scroll height against the viewport          (§10.3)
//
// Note: transitions are disabled while it reads. A hidden/background tab freezes
// transitioned property values at their pre-transition state, which silently
// corrupts colour and opacity reads — this is how the baseline validation pass
// initially mis-measured selected states.
//
// SCOPE CEILING — deliberate. One file that reads an already-open page and prints
// pass/fail. It must never acquire a driver, launcher, fixtures, runner,
// assertion DSL, retries or reporters. If it starts wanting those, adopt
// Playwright instead of growing this. See ui-implementation.md §4.

(() => {
  const AA = 4.5;
  const MAX_SIZES = 9;

  const style = document.createElement("style");
  style.textContent = "*,*::before,*::after{transition:none !important;animation:none !important}";
  document.documentElement.appendChild(style);

  const lum = ([r, g, b]) => {
    const f = (v) => ((v /= 255) <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const ratio = (a, b) => {
    const x = lum(a), y = lum(b);
    return Math.round(((Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)) * 100) / 100;
  };
  // Resolve ANY CSS colour to sRGB by painting one pixel and reading it back.
  // Regex-scraping the computed string cannot work: Tailwind v4 emits `oklab()`
  // with negative components, so digit-scraping silently yields near-black and
  // invents contrast failures. The canvas handles every colour space the browser
  // supports, including ones added later.
  const cv = document.createElement("canvas");
  cv.width = cv.height = 1;
  const ctx = cv.getContext("2d", { willReadFrequently: true });
  const parse = (s) => {
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = "#000";
    ctx.fillStyle = s;             // invalid input leaves the reset value
    ctx.fillRect(0, 0, 1, 1);
    const d = ctx.getImageData(0, 0, 1, 1).data;
    return { rgb: [d[0], d[1], d[2]], a: d[3] / 255 };
  };
  // Composite an element's background over its ancestors. Taking the first opaque
  // ancestor instead produces false positives on tinted chips, which are fine.
  const bgOf = (el) => {
    let node = el, acc = null;
    while (node) {
      const { rgb, a } = parse(getComputedStyle(node).backgroundColor);
      if (a > 0) {
        acc = acc === null
          ? { rgb, a }
          : { rgb: acc.rgb.map((v, i) => acc.a * v + (1 - acc.a) * rgb[i]),
              a: acc.a + (1 - acc.a) * a };
        if (acc.a >= 0.999) return acc.rgb.map(Math.round);
      }
      node = node.parentElement;
    }
    return (acc ? acc.rgb : [255, 255, 255]).map(Math.round);
  };
  const visible = (el) => {
    const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    return cs.display !== "none" && cs.visibility !== "hidden" && cs.opacity !== "0"
      && r.width > 2 && r.height > 2;
  };

  const scope = [...document.querySelectorAll("main *, header *")];
  const texts = scope.filter(
    (el) => !el.closest("table") && visible(el)
      && [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())
  );

  const out = [];
  const say = (ok, label, detail) =>
    out.push((ok ? "PASS  " : "FAIL  ") + label + (detail ? "  — " + detail : ""));

  // 1. contrast
  //
  // Disabled controls are excluded and checked separately at 3:1 below. WCAG
  // 1.4.3 exempts inactive components from the 4.5:1 floor, and holding them to
  // it would make a correct disabled treatment permanently "fail" — which is how
  // a check stops being read.
  const isInactive = (el) => {
    const b = el.closest("button, input, textarea, select");
    return Boolean(b && b.disabled);
  };
  const bad = texts
    .filter((el) => !isInactive(el))
    .map((el) => {
      const cs = getComputedStyle(el);
      const fg = parse(cs.color), bg = bgOf(el);
      const eff = fg.a < 1 ? fg.rgb.map((v, i) => fg.a * v + (1 - fg.a) * bg[i]) : fg.rgb;
      return { r: ratio(eff, bg), fs: parseFloat(cs.fontSize), t: el.textContent.trim().slice(0, 44) };
    })
    .filter((x) => x.r < AA)
    .sort((a, b) => a.r - b.r);
  say(bad.length === 0, "contrast: " + texts.length + " text runs >= " + AA + ":1",
      bad.length ? bad.length + " below" : "");
  bad.slice(0, 12).forEach((x) => out.push("        " + x.r + ":1  " + x.fs + "px  \"" + x.t + "\""));

  // 2. duplicate inputs / labels
  const tas = [...document.querySelectorAll("main textarea")].filter(visible);
  say(tas.length <= 1, "answer inputs: " + tas.length,
      tas.length > 1 ? "more than one composer on screen" : "");
  // Buttons inside a repeated list legitimately share a label — three gap rows
  // each offering "Set aside" is correct. What is never correct is two controls
  // outside any list carrying one label and doing different things.
  const labels = [...document.querySelectorAll("main button")]
    .filter((b) => visible(b) && !b.closest("li"))
    .map((b) => b.textContent.trim()).filter(Boolean);
  const dupes = [...new Set(labels.filter((l, i) => labels.indexOf(l) !== i))];
  say(dupes.length === 0, "no ambiguous duplicate button labels", dupes.join(", "));

  // 3. focus and disabled
  //
  // Focus is checked by asking the browser what a control WOULD look like when
  // focus-visible applies, which cannot be read from a static style declaration.
  // Cheapest reliable proxy: every interactive element must be matched by the
  // global rule, i.e. no computed `outline-style: none` left over from an
  // element-level override.
  const interactive = [...document.querySelectorAll(
    "main a, main button, main input, main textarea, main select, main summary, main [tabindex]," +
    "header a, header button, header input, header select"
  )].filter(visible);
  const noRing = interactive.filter((el) => {
    if (el.hasAttribute("data-focus-exempt")) return false;
    const cs = getComputedStyle(el, ":focus-visible");
    return cs.outlineStyle === "none" || cs.outlineWidth === "0px";
  });
  say(noRing.length === 0, "focus ring on all " + interactive.length + " interactive elements",
      noRing.length ? noRing.length + " with no ring: "
        + noRing.slice(0, 4).map((e) => (e.textContent || e.tagName).trim().slice(0, 22)).join(" / ") : "");

  const disabled = interactive.filter((el) => el.disabled);
  const dimDisabled = disabled.filter((el) => {
    const cs = getComputedStyle(el);
    const fg = parse(cs.color), bg = bgOf(el);
    const eff = fg.a < 1 ? fg.rgb.map((v, i) => fg.a * v + (1 - fg.a) * bg[i]) : fg.rgb;
    // opacity is inherited by the whole subtree, so fold it in
    const o = parseFloat(cs.opacity);
    const shown = o < 1 ? eff.map((v, i) => o * v + (1 - o) * bg[i]) : eff;
    return ratio(shown, bg) < 3;
  });
  say(dimDisabled.length === 0, disabled.length + " disabled control(s) >= 3:1",
      dimDisabled.map((e) => e.textContent.trim().slice(0, 20) + " "
        + ratio(((c) => c)(parse(getComputedStyle(e).color).rgb), bgOf(e)) + ":1").join(", "));

  // 4. type scale
  const sizes = [...new Set(texts.map(
    (el) => Math.round(parseFloat(getComputedStyle(el).fontSize) * 10) / 10))]
    .sort((a, b) => a - b);
  const small = sizes.filter((s) => s <= 16);
  say(sizes.length <= MAX_SIZES, "distinct font sizes: " + sizes.length, sizes.join(" "));
  if (small.length) {
    out.push("        " + small.length + " of " + sizes.length + " are <=16px (band "
      + small[0] + "-" + small[small.length - 1] + "px)");
  }

  // 5. radius census
  const radii = {};
  scope.filter(visible).forEach((el) => {
    const r = getComputedStyle(el).borderRadius;
    if (r !== "0px") radii[r] = (radii[r] || 0) + 1;
  });
  out.push("INFO  radii: " + Object.entries(radii).sort((a, b) => b[1] - a[1])
    .map(([k, v]) => k + "x" + v).join("  "));

  // Geometry needs a laid-out page. A background or non-compositing tab reports
  // a zero-size viewport, which would turn every measurement below into a
  // meaningless failure — so say so instead of guessing.
  const laidOut = innerWidth > 200 && innerHeight > 200;
  if (!laidOut) {
    out.push("SKIP  geometry: viewport reports " + innerWidth + "x" + innerHeight
      + " — page is not laid out (background tab?). Colour checks above are still valid.");
  } else {
    // 6. header
    const h = document.querySelector("header");
    if (h) {
      const over = h.scrollWidth - h.clientWidth;
      say(over <= 0, "header fits at " + innerWidth + "px",
          over > 0 ? "overflows by " + over + "px" : "");
      const flex = [...h.children].find((c) => getComputedStyle(c).flexGrow !== "0");
      if (flex) {
        const w = Math.round(flex.getBoundingClientRect().width);
        say(w >= 240, "header content zone " + w + "px (>=240)");
      }
    }

    // 7. workspace scroll
    const sc = [...document.querySelectorAll("main .overflow-y-auto")].filter(visible)
      .sort((a, b) => b.scrollHeight - a.scrollHeight)[0];
    if (sc && sc.clientHeight > 200) {
      out.push("INFO  workspace scroll: " + sc.scrollHeight + "px in " + sc.clientHeight
        + "px = " + (Math.round((sc.scrollHeight / sc.clientHeight) * 10) / 10) + "x viewport");
    }
  }

  style.remove();
  const failing = out.filter((l) => l.startsWith("FAIL")).length;
  const report = out.join("\n") + "\n\n" + failing + " failing";
  console.log("\n" + report + "\n");
  // Also returned, so the report can be read by a caller that eval()s this file
  // rather than reading the console.
  return report;
})();
