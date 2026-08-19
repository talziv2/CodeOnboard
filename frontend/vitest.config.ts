import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/**
 * Test config for the frontend.
 *
 * Deliberately narrow. This covers the two things where UI regressions actually
 * bite: pure functions that derive what the learner sees (route/section layout,
 * lesson phase), and render-order invariants that the redesign depends on — one
 * answer input per phase, primary action never stranded below a long explanation,
 * superseded state collapsed.
 *
 * It is not a route-level or browser-level harness. Contrast and geometry are
 * measured by `scripts/ux-probe.mjs` against a real page, and end-to-end journeys
 * are the checklist in `docs/planning/phases/evidence/ux-journeys.md`.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./test/setup.ts"],
    include: ["{app,components,lib,test}/**/*.test.{ts,tsx}"],
    css: false,
  },
  resolve: {
    // Mirrors the `@/*` → `./*` alias in tsconfig.json, so tests import modules
    // by the same path the components do.
    alias: {
      "@": fileURLToPath(new URL("./", import.meta.url)),
    },
  },
});
