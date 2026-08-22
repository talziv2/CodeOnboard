import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { resetSession, sessionStart } from "@/lib/api";

/**
 * `Start over` and `Rebuild learning path` are two different requests.
 *
 * They were one, and the one they were was the expensive one: `Start over` called
 * `/session/start` with `force_new`, which re-ran the whole pipeline and returned a
 * DIFFERENT route. This file pins the distinction at the wire, because it is the
 * layer where the two could quietly become the same call again — and because the
 * cheap one's whole promise is what it does NOT do.
 */

// The API is reached through the Next.js rewrite now (multi-user.md D-2), so the
// browser only ever calls its own origin and the auth cookie is first-party.
// This was `http://localhost:8000`, which was `NEXT_PUBLIC_API_URL`'s default.
const BASE = "/api";

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ session_id: "s1", graph: {}, discarded: {} }),
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("resetSession", () => {
  test("posts to the session's own reset endpoint", async () => {
    await resetSession("abc123");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/session/abc123/reset`);
    expect(init.method).toBe("POST");
  });

  test("sends no body — the session id in the path is the whole request", async () => {
    await resetSession("abc123");

    expect(fetchMock.mock.calls[0][1].body).toBeUndefined();
  });

  test("never touches /session/start", async () => {
    // The regression that matters: a reset must not be able to trigger the
    // pipeline. If this URL ever changes to /session/start, the two-to-four
    // minute wait is back and `Start over` returns a different route again.
    await resetSession("abc123");

    expect(fetchMock.mock.calls[0][0]).not.toContain("/session/start");
  });

  test("encodes the session id", async () => {
    await resetSession("a/b?c");

    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/session/a%2Fb%3Fc/reset`);
  });

  test("surfaces the backend's refusal rather than swallowing it", async () => {
    // 409 `no_plan_snapshot`: a session written before the plan existed. The UI
    // needs to be able to say so, which it cannot do if this resolves.
    fetchMock.mockResolvedValue({
      ok: false,
      status: 409,
      text: async () => JSON.stringify({ detail: "no_plan_snapshot" }),
    });

    await expect(resetSession("abc123")).rejects.toThrow("no_plan_snapshot");
  });
});

describe("the rebuild is still the expensive call", () => {
  test("sessionStart with force_new is what runs the pipeline", async () => {
    await sessionStart("https://github.com/psf/requests", { primary_goal: "x" }, true, "run-1");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/session/start`);
    expect(JSON.parse(init.body)).toMatchObject({
      force_new: true,
      progress_id: "run-1",
    });
  });

  test("its wait can be abandoned, and an abort is not a server failure", async () => {
    const controller = new AbortController();
    fetchMock.mockRejectedValue(
      new DOMException("The operation was aborted.", "AbortError")
    );

    await expect(
      sessionStart("https://github.com/psf/requests", {}, true, "run-1", controller.signal)
    ).rejects.toThrow(/aborted/);
  });
});
