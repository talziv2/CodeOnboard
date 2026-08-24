/**
 * The sign-in form, and specifically what it offers.
 *
 * These exist because of a real defect: the Google button rendered on a server
 * with no Google credentials, and clicking it navigated the browser onto
 * `{"detail":"google_not_configured"}` — a raw JSON object on a blank tab with
 * no way back to the app.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

let search = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/login",
  useSearchParams: () => new URLSearchParams(search),
}));

const listProviders = vi.fn();
vi.mock("@/lib/api", () => ({
  GOOGLE_START: "/api/auth/google/start",
  linkGoogle: vi.fn(),
  listProviders: (...a: unknown[]) => listProviders(...a),
}));

vi.mock("@/lib/auth", () => ({
  NEXT_PARAM: "next",
  useAuth: () => ({ signIn: vi.fn(), signUp: vi.fn(), refresh: vi.fn() }),
}));

import AuthForm from "@/components/auth/AuthForm";
import { t } from "@/lib/strings";

const googleButton = () => screen.queryByText(t.auth.google);

describe("AuthForm and the Google button", () => {
  beforeEach(() => { search = ""; listProviders.mockReset(); });

  it("offers Google when the server has it configured", async () => {
    listProviders.mockResolvedValue({ password: true, google: true });

    render(<AuthForm mode="login" />);

    await waitFor(() => expect(googleButton()).toBeTruthy());
    expect(googleButton()?.closest("a")?.getAttribute("href"))
      .toBe("/api/auth/google/start");
  });

  it("does not offer Google when the server has no credentials", async () => {
    listProviders.mockResolvedValue({ password: true, google: false });

    render(<AuthForm mode="login" />);

    await waitFor(() => expect(listProviders).toHaveBeenCalled());
    expect(googleButton()).toBeNull();
  });

  it("does not offer Google before the answer arrives", () => {
    // A button that appears and then vanishes is its own small defect: it is
    // long enough to click.
    listProviders.mockReturnValue(new Promise(() => {}));

    render(<AuthForm mode="login" />);

    expect(googleButton()).toBeNull();
  });

  it("does not offer Google when the question cannot be asked", async () => {
    listProviders.mockRejectedValue(new Error("network"));

    render(<AuthForm mode="login" />);

    await waitFor(() => expect(listProviders).toHaveBeenCalled());
    expect(googleButton()).toBeNull();
  });

  it("still shows the email form when Google is unavailable", async () => {
    listProviders.mockResolvedValue({ password: true, google: false });

    render(<AuthForm mode="login" />);

    await waitFor(() => expect(listProviders).toHaveBeenCalled());
    expect(screen.getByLabelText(t.auth.emailLabel)).toBeTruthy();
    expect(screen.getByLabelText(t.auth.passwordLabel)).toBeTruthy();
  });

  it("explains itself when the click got through anyway", async () => {
    // The redirect target of an unconfigured `/auth/google/start`: a stale tab,
    // a bookmark, or a typed URL still has to land somewhere readable.
    search = "error=google_not_configured";
    listProviders.mockResolvedValue({ password: true, google: false });

    render(<AuthForm mode="login" />);

    expect(screen.getByRole("alert").textContent)
      .toContain("isn't set up on this server");
  });
});
