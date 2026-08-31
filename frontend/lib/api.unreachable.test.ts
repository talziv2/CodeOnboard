import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { login } from "@/lib/api";
import { errorText, t } from "@/lib/strings";

/**
 * The Next.js `/api/*` rewrite makes a dead backend look like a successful
 * request: the browser reaches Next, Next fails to reach FastAPI, and the
 * learner gets a 500 whose body is the bare string "Internal Server Error".
 *
 * That string was rendered verbatim under the password field, where it was
 * indistinguishable from a rejected password. These tests pin the translation
 * at the wire, and pin the two ways it must NOT over-trigger: FastAPI's own
 * JSON errors keep their `detail`, and a non-JSON 4xx is not a dead backend.
 */

function respond(status: number, body: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      text: async () => body,
      json: async () => JSON.parse(body),
    }),
  );
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

describe("a non-JSON 5xx is the proxy failing to reach the backend", () => {
  test("the bare proxy text becomes the server_unreachable slug", async () => {
    respond(500, "Internal Server Error");

    await expect(login("a@b.co", "pw")).rejects.toThrow("server_unreachable");
  });

  test("the slug renders as wording we wrote, not as the proxy's", async () => {
    respond(500, "Internal Server Error");

    // The regression this file exists for: the login form calls
    // `errorText(err.message)`, so an untranslated message reaches the learner.
    const err = await login("a@b.co", "pw").catch((e: Error) => e);

    expect(errorText((err as Error).message)).toBe(t.errors.server_unreachable);
    expect(errorText((err as Error).message)).not.toBe("Internal Server Error");
  });

  test("502 and 503 are the same failure", async () => {
    for (const status of [502, 503, 504]) {
      respond(status, "Bad Gateway");
      await expect(login("a@b.co", "pw")).rejects.toThrow("server_unreachable");
    }
  });
});

describe("what it must not swallow", () => {
  test("a JSON 500 from FastAPI keeps its own detail", async () => {
    // FastAPI answers every error it handles with a JSON `detail`. A real
    // backend error must still say what it said, or this fix would hide the
    // pipeline's own failures behind "check the backend is running".
    respond(500, JSON.stringify({ detail: "pipeline_failed" }));

    await expect(login("a@b.co", "pw")).rejects.toThrow("pipeline_failed");
  });

  test("a non-JSON 404 is not a dead backend", async () => {
    respond(404, "Not Found");

    await expect(login("a@b.co", "pw")).rejects.toThrow("Not Found");
  });

  test("a wrong password still reads as a wrong password", async () => {
    // The symptom that started this: the real 401 and a dead backend rendered
    // identically. 401 never reaches `fail()` -- `send()` throws
    // NotAuthenticatedError first -- so this pins that they stay different.
    respond(401, JSON.stringify({ detail: "Email or password is incorrect." }));

    await expect(login("a@b.co", "pw")).rejects.toThrow("not_authenticated");
  });
});
