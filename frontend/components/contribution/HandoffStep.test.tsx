import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { t } from "@/lib/strings";

/**
 * The handoff surface — the last thing a learner reads before the work moves.
 *
 * Three claims are asserted here, and all three are about honesty rather than
 * layout:
 *
 *   THE TWO HALVES STAY APART. "About the code" and "About you" are separate
 *   headed blocks. A reader who merges them makes the claim D8 exists to
 *   prevent — that demonstrating eleven concepts is a fact about the patch.
 *
 *   THE REVISION IS ON SCREEN. Every file and symbol shown is true at ONE
 *   commit; against a different checkout the whole panel is confidently wrong,
 *   which is worse than empty.
 *
 *   NOTHING CLAIMS CORRECTNESS. Not the suggested command, not the boundary,
 *   not the concept count. `strings.ts` bans the vocabulary; this checks the
 *   rendered page.
 */
const api = vi.hoisted(() => ({ getHandoff: vi.fn() }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  ...api,
}));

import HandoffStep from "@/components/contribution/HandoffStep";

const HANDOFF = {
  context: {
    repository: {
      url: "https://github.com/psf/requests",
      commit: "e8d2c015eecda8273612dd4562425e00cd164ba5",
      verify: "Run `git rev-parse HEAD`",
    },
    task: "Add get_all(name) to RequestsCookieJar.",
    change_boundary: {
      target: [{ file: "src/requests/cookies.py", symbol: "RequestsCookieJar" }],
      must_not_change: [{ file: "src/requests/cookies.py", symbol: "RequestsCookieJar.get" }],
      existing_tests: [{ file: "tests/test_requests.py", symbol: "TestRequests" }],
      edge_cases: [{ case: "a cookie whose value is None" }],
      conventions: [],
    },
    contracts: [{ file: "src/requests/cookies.py", contract: "get() returns one value or raises" }],
    recommended_validation: "pytest tests/test_requests.py -q",
    learner: {
      ready: true,
      required: 11,
      demonstrated: 11,
      demonstrated_concepts: ["Explain how _find_no_duplicates filters"],
      not_taught: [{ name: "adapters", reason: "transport" }],
      started_unready: false,
      means: "Demonstrated means they answered a question. Not a certification.",
    },
  },
  setup: {
    server_name: "codeonboard",
    deep_link: "claude-cli://open?cwd=C:/personal/codeonboard-workspace/requests&q=I%27m%20ready",
    workspace: "C:/personal/codeonboard-workspace/requests",
    repo_slug: "psf/requests",
    mcp_json: {
      mcpServers: {
        codeonboard: {
          type: "stdio",
          command: "uv",
          args: ["run", "--directory", "C:/personal/CodeOnboard", "python", "-m", "backend.mcp_server"],
          env: { CODEONBOARD_SESSION: "73a2248c", CODEONBOARD_USER: "u1" },
        },
      },
    },
  },
};

describe("the handoff surface", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getHandoff.mockResolvedValue(HANDOFF);
  });

  const open = async () => {
    render(<HandoffStep sessionId="s1" onFallback={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByText(t.contribution.handoffHeading)).toBeTruthy()
    );
  };

  test("shows what travels about the code, and about the learner, separately", async () => {
    await open();
    expect(screen.getByText(t.contribution.handoffCodeHalf)).toBeTruthy();
    expect(screen.getByText(t.contribution.handoffLearnerHalf)).toBeTruthy();
    expect(screen.getByText("src/requests/cookies.py:RequestsCookieJar")).toBeTruthy();
    expect(screen.getByText(t.contribution.handoffDemonstrated(11))).toBeTruthy();
  });

  test("puts the pinned revision on screen with the reason it matters", async () => {
    await open();
    expect(screen.getByText("e8d2c015eecd")).toBeTruthy();
    expect(screen.getByText(t.contribution.handoffRevisionHint)).toBeTruthy();
  });

  test("what `demonstrated` means travels with the number", async () => {
    // Without it, "11 concepts demonstrated" reads as a certification.
    await open();
    expect(screen.getByText(HANDOFF.context.learner.means)).toBeTruthy();
  });

  test("names what the journey did not cover", async () => {
    await open();
    expect(screen.getByText(t.contribution.handoffNotTaught)).toBeTruthy();
    expect(screen.getByText("adapters")).toBeTruthy();
  });

  test("the suggested command is never described as run or passing", async () => {
    await open();
    expect(screen.getByText("pytest tests/test_requests.py -q")).toBeTruthy();
    expect(screen.getByText(t.contribution.handoffValidationHint)).toBeTruthy();
    const page = document.body.textContent ?? "";
    for (const word of ["passing", "verified", "is correct", "tests pass"]) {
      expect(page.toLowerCase()).not.toContain(word);
    }
  });

  test("it does not promise the agent will refuse to write the change", async () => {
    // Guidance, not enforcement. A learner told otherwise, who then watches
    // Claude implement it, was misled by us rather than by Claude.
    await open();
    expect(screen.getByText(t.contribution.handoffAgentRole)).toBeTruthy();
    expect(t.contribution.handoffAgentRole).toContain("not a guarantee");
  });

  test("the action comes BEFORE the summary it refers to", async () => {
    // Eleven objectives and five boundary sections sit between the heading and
    // the bottom of this panel. A learner who has decided to go should not have
    // to scroll past all of it to find the control that takes them there.
    await open();
    const link = screen.getByRole("link", { name: t.contribution.handoffOpen });
    const summary = screen.getByText(t.contribution.handoffWhatTravels);
    // DOCUMENT_POSITION_FOLLOWING: the summary comes after the link.
    expect(link.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING)
      .toBeTruthy();
    // ...and the copy agrees about which way round they are.
    expect(t.contribution.handoffAfter).toContain("below");
  });

  test("the whole action is one control that opens the editor", async () => {
    // The product step is "open my editor on this contribution". Copying JSON is
    // plumbing, and a flow whose first instruction is "save this file" has made
    // our plumbing the learner's problem.
    await open();
    const link = screen.getByRole("link", { name: t.contribution.handoffOpen });
    expect(link.getAttribute("href")).toBe(HANDOFF.setup.deep_link);
    // AN ABSOLUTE PATH, never a repository slug. `repo=` resolves only against
    // clones Claude Code has already opened and, when it cannot, opens somewhere
    // else rather than failing — measured: it landed in the home directory and
    // the server was simply absent.
    expect(link.getAttribute("href")).toContain("cwd=");
    expect(link.getAttribute("href")).not.toContain("repo=");
  });

  test("the destination is on screen, so a wrong one is visible", async () => {
    await open();
    expect(
      screen.getByText(t.contribution.handoffOpenIn(HANDOFF.setup.workspace))
    ).toBeTruthy();
  });

  test("with no workspace configured there is no button at all", async () => {
    // DI-8 at the launch control: a link that silently opens the wrong directory
    // is worse than one that is not there, and this is the exact failure that
    // shipped — Claude Code opened, and /mcp was empty.
    api.getHandoff.mockResolvedValue({
      ...HANDOFF,
      setup: { ...HANDOFF.setup, deep_link: null, workspace: null },
    });
    await open();
    expect(screen.queryByRole("link", { name: t.contribution.handoffOpen })).toBeNull();
    expect(screen.getByText(t.contribution.handoffNoWorkspace)).toBeTruthy();
  });

  test("nothing mechanical is a required step", async () => {
    await open();
    // Folded away, not removed: a `<details>` that starts closed. The learner
    // never has to open it; the person reproducing this on another machine can.
    const details = document.querySelector("details");
    expect(details).toBeTruthy();
    expect((details as HTMLDetailsElement).open).toBe(false);
    expect(details!.contains(screen.getByText(t.contribution.handoffStep1))).toBe(true);
    expect(details!.contains(document.querySelector("pre")!)).toBe(true);
    // And the one thing that is NOT folded away is the action.
    expect(screen.getByRole("link", { name: t.contribution.handoffOpen })).toBeTruthy();
  });

  test("the config is still there for whoever has to reproduce it", async () => {
    await open();
    await userEvent.click(screen.getByText(t.contribution.handoffSetupLabel));
    const pre = document.querySelector("pre")?.textContent ?? "";
    expect(pre).toContain("CODEONBOARD_SESSION");
    expect(pre).toContain("73a2248c");
    expect(pre).toContain("--directory");
  });

  test("a session with no boundary is refused, not shown an empty panel", async () => {
    // DI-8. A confident layout wrapped around nothing is worse than an error.
    api.getHandoff.mockRejectedValue(new Error("no_change_boundary"));
    render(<HandoffStep sessionId="s1" onFallback={vi.fn()} />);
    await waitFor(() =>
      expect(screen.queryByText(t.contribution.handoffHeading)).toBeNull()
    );
    expect(screen.getByRole("button", { name: t.contribution.handoffFallback })).toBeTruthy();
  });

  test("the old in-app steps stay reachable while this is being verified", async () => {
    const onFallback = vi.fn();
    render(<HandoffStep sessionId="s1" onFallback={onFallback} />);
    await waitFor(() =>
      expect(screen.getByText(t.contribution.handoffHeading)).toBeTruthy()
    );
    await userEvent.click(
      screen.getByRole("button", { name: t.contribution.handoffFallback })
    );
    expect(onFallback).toHaveBeenCalled();
  });
});
