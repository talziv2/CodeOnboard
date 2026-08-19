import "@testing-library/react";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Each test gets a clean document. Without this, the render-order assertions —
// "exactly one textarea", "one primary action" — would count leftovers from the
// previous test and pass or fail for the wrong reason.
afterEach(() => {
  cleanup();
});

// jsdom implements neither of these, and both are read during a normal render:
// `matchMedia` by the reduced-motion check in the code pane's scroll rule, and
// `scrollTo` by the same code path. Stubbed rather than mocked per-test so a
// component under test never fails on an unrelated browser API.
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

if (!Element.prototype.scrollTo) {
  Element.prototype.scrollTo = () => {};
}
