import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  usePathname: () => "/session/abc",
  useSearchParams: () => new URLSearchParams(""),
}));

const me = vi.fn();
const login = vi.fn();
const logout = vi.fn();
let unauthenticatedHandler: (() => void) | null = null;

vi.mock("@/lib/api", () => ({
  me: (...a: unknown[]) => me(...a),
  login: (...a: unknown[]) => login(...a),
  register: vi.fn(),
  logout: (...a: unknown[]) => logout(...a),
  logoutEverywhere: vi.fn(),
  setUnauthenticatedHandler: (h: (() => void) | null) => { unauthenticatedHandler = h; },
  NotAuthenticatedError: class extends Error {},
}));

import { AuthProvider, useAuth } from "@/lib/auth";

function Probe() {
  const { status, user } = useAuth();
  return <div data-testid="probe">{status}:{user?.email ?? "-"}</div>;
}

const renderProbe = () =>
  render(<AuthProvider><Probe /></AuthProvider>);

describe("AuthProvider", () => {
  beforeEach(() => { replace.mockClear(); me.mockReset(); login.mockReset(); logout.mockReset(); });
  afterEach(() => { unauthenticatedHandler = null; });

  it("starts in loading, so no page flashes its signed-out branch", async () => {
    let resolve!: (v: unknown) => void;
    me.mockReturnValue(new Promise((r) => { resolve = r; }));

    renderProbe();

    expect(screen.getByTestId("probe").textContent).toBe("loading:-");
    resolve(null);
    await waitFor(() => expect(screen.getByTestId("probe").textContent).toBe("anonymous:-"));
  });

  it("reports the signed-in user after one call to /auth/me", async () => {
    me.mockResolvedValue({ user_id: "u1", email: "a@b.co", display_name: null });

    renderProbe();

    await waitFor(() =>
      expect(screen.getByTestId("probe").textContent).toBe("authenticated:a@b.co"));
    expect(me).toHaveBeenCalledTimes(1);
  });

  it("treats an unreachable server as anonymous rather than crashing", async () => {
    // NOT the same as signed out in meaning, but it is the only safe render:
    // the alternative is an error boundary on every page when the backend
    // restarts.
    me.mockRejectedValue(new Error("server_unreachable"));

    renderProbe();

    await waitFor(() =>
      expect(screen.getByTestId("probe").textContent).toBe("anonymous:-"));
  });

  it("redirects to /login with ?next= when any call 401s", async () => {
    me.mockResolvedValue({ user_id: "u1", email: "a@b.co", display_name: null });
    renderProbe();
    await waitFor(() => expect(unauthenticatedHandler).not.toBeNull());

    unauthenticatedHandler!();

    // The learner comes back to the lesson they were on, not to the front door.
    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith("/login?next=%2Fsession%2Fabc"));
  });
});

describe("AuthForm redirect target", () => {
  it("refuses an absolute ?next=, which would be an open redirect", async () => {
    // A link to /login?next=https://evil.example would send someone who had
    // just typed their password to a lookalike asking for it again.
    const { destinationFor } = await import("@/lib/auth-redirect");
    expect(destinationFor("https://evil.example")).toBe("/");
    expect(destinationFor("//evil.example")).toBe("/");
    expect(destinationFor("/session/abc")).toBe("/session/abc");
    expect(destinationFor(null)).toBe("/");
  });
});
