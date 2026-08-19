import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { Question } from "@/lib/api";
import { t } from "@/lib/strings";

/**
 * The interview's interaction model.
 *
 * The load-bearing rule is that CHOOSING AND CONFIRMING ARE SEPARATE. Clicking an
 * option must not advance the interview, because the alternatives — a timed
 * auto-advance, or a double-click shortcut — both commit the user on an input they
 * did not intend as a commitment. Two tests pin the click behaviour, one asserts
 * no `dblclick` handler exists, and one walks the whole interview by keyboard.
 *
 * The other rule is that `/goal/back` stays the only way backwards. Stepping from
 * question 5 to question 2 is three calls to it, not one jump, because the server
 * owns what going back MEANS: crossing question 2 clears `goal_type`, and that is
 * what makes the follow-up questions recompute.
 *
 * Two later rules, from use: the answers are shown ONLY on the review step, never
 * beside a live question, and the last answer does not start the session — it opens
 * a gate that has to be confirmed. `onDone` firing early is the regression that
 * would cost a user a multi-minute pipeline run they never agreed to.
 */

const api = vi.hoisted(() => ({
  goalStart: vi.fn(),
  goalAnswer: vi.fn(),
  goalBack: vi.fn(),
}));
vi.mock("@/lib/api", () => api);

import GoalDialogue from "@/components/GoalDialogue";

// Mirrors the real vocabularies: these strings are parsed keys in
// `backend/agents/goal/questions.py`, not labels.
const FAMILIARITY = [
  "Starting fresh — never looked at it",
  "Skimmed the README or docs",
  "Looked at some code but still confused",
  "Used it before, now diving into the source",
];
const GOAL_TYPES = [
  "Use it in my own project",
  "Understand the architecture (layers, boundaries, design)",
  "Improve or extend the codebase safely",
  "Contribute code / open a PR",
  "Debug an issue I'm hitting",
  "Understand how it works (reading/learning)",
];

const q = (index: number, text: string, options: string[] | null, total = 6): Question => ({
  text,
  options,
  index,
  total,
});

const Q1 = q(1, "How familiar are you with this codebase?", FAMILIARITY);
const Q2 = q(2, "What brings you to this repo?", GOAL_TYPES);
const Q3 = q(3, "What specifically do you want to be able to do after this session?", null);

beforeEach(() => {
  vi.clearAllMocks();
  api.goalStart.mockResolvedValue({ session_id: "s1", question: Q1 });
});

const start = async () => {
  render(<GoalDialogue repoUrl="https://github.com/psf/requests" onDone={vi.fn()} />);
  await screen.findByText(Q1.text);
};

describe("choosing an option", () => {
  test("selects it without advancing the interview", async () => {
    await start();

    await userEvent.click(screen.getByRole("radio", { name: FAMILIARITY[1] }));

    expect(api.goalAnswer).not.toHaveBeenCalled();
    expect(screen.getByRole("radio", { name: FAMILIARITY[1] })).toHaveProperty(
      "ariaChecked",
      "true",
    );
    // Still on the same question.
    expect(screen.getByText(Q1.text)).toBeTruthy();
  });

  test("a second click moves the selection rather than submitting twice", async () => {
    await start();

    await userEvent.click(screen.getByRole("radio", { name: FAMILIARITY[1] }));
    await userEvent.click(screen.getByRole("radio", { name: FAMILIARITY[3] }));

    expect(api.goalAnswer).not.toHaveBeenCalled();
    expect(screen.getByRole("radio", { name: FAMILIARITY[3] })).toHaveProperty(
      "ariaChecked",
      "true",
    );
    expect(screen.getByRole("radio", { name: FAMILIARITY[1] })).toHaveProperty(
      "ariaChecked",
      "false",
    );
  });

  test("no option carries a double-click handler", async () => {
    await start();
    // A dblclick on a selected option must be inert: two clicks select twice.
    const option = screen.getByRole("radio", { name: FAMILIARITY[0] });
    await userEvent.dblClick(option);
    expect(api.goalAnswer).not.toHaveBeenCalled();
  });

  test("Continue is dead until something is chosen, and says why", async () => {
    await start();

    expect(screen.getByRole("button", { name: t.goal.continue })).toHaveProperty("disabled", true);
    expect(screen.getByText(t.goal.answerRequired)).toBeTruthy();

    await userEvent.click(screen.getByRole("radio", { name: FAMILIARITY[0] }));

    expect(screen.getByRole("button", { name: t.goal.continue })).toHaveProperty("disabled", false);
    expect(screen.getByText(t.goal.optionHint)).toBeTruthy();
  });
});

describe("the keyboard", () => {
  test("arrow keys move the selection", async () => {
    await start();

    // From nothing chosen, ArrowDown starts at the top of the list.
    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getByRole("radio", { name: FAMILIARITY[0] })).toHaveProperty(
      "ariaChecked",
      "true",
    );

    await userEvent.keyboard("{ArrowDown}{ArrowDown}");
    expect(screen.getByRole("radio", { name: FAMILIARITY[2] })).toHaveProperty(
      "ariaChecked",
      "true",
    );

    await userEvent.keyboard("{ArrowUp}");
    expect(screen.getByRole("radio", { name: FAMILIARITY[1] })).toHaveProperty(
      "ariaChecked",
      "true",
    );
  });

  test("the selection wraps at both ends", async () => {
    await start();

    await userEvent.keyboard("{ArrowUp}");
    expect(screen.getByRole("radio", { name: FAMILIARITY[3] })).toHaveProperty(
      "ariaChecked",
      "true",
    );

    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getByRole("radio", { name: FAMILIARITY[0] })).toHaveProperty(
      "ariaChecked",
      "true",
    );
  });

  test("Enter confirms the selection, and only then", async () => {
    api.goalAnswer.mockResolvedValue({ done: false, question: Q2 });
    await start();

    // Enter with nothing chosen must not submit an empty answer.
    await userEvent.keyboard("{Enter}");
    expect(api.goalAnswer).not.toHaveBeenCalled();

    await userEvent.keyboard("{ArrowDown}{Enter}");
    await waitFor(() => expect(api.goalAnswer).toHaveBeenCalledWith("s1", FAMILIARITY[0]));
    await screen.findByText(Q2.text);
  });

  test("the whole interview is completable without a pointer", async () => {
    const onDone = vi.fn();
    api.goalAnswer
      .mockResolvedValueOnce({ done: false, question: Q2 })
      .mockResolvedValueOnce({ done: false, question: Q3 })
      .mockResolvedValueOnce({ done: true, goal: { primary_goal: "trace a request" } });

    render(<GoalDialogue repoUrl="https://github.com/psf/requests" onDone={onDone} />);
    await screen.findByText(Q1.text);

    await userEvent.keyboard("{ArrowDown}{Enter}");        // Q1, first option
    await screen.findByText(Q2.text);
    await userEvent.keyboard("{ArrowUp}{Enter}");          // Q2, last option
    await screen.findByText(Q3.text);
    await userEvent.keyboard("trace a request{Enter}");    // Q3, free text

    // The keyboard path ends at the gate, not in the pipeline.
    await screen.findByText(t.goal.reviewTitle);
    expect(onDone).not.toHaveBeenCalled();
    expect(api.goalAnswer).toHaveBeenNthCalledWith(2, "s1", GOAL_TYPES[5]);
    expect(api.goalAnswer).toHaveBeenNthCalledWith(3, "s1", "trace a request");

    await userEvent.click(screen.getByRole("button", { name: t.goal.startSession }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });
});

describe("the review gate", () => {
  /** Answer Q1 -> Q2 -> Q3, then finish, landing on the review step. */
  const walkToReview = async () => {
    api.goalAnswer
      .mockResolvedValueOnce({ done: false, question: Q2 })
      .mockResolvedValueOnce({ done: false, question: Q3 })
      .mockResolvedValueOnce({ done: true, goal: { primary_goal: "trace a request" } });
    await start();
    await userEvent.keyboard("{ArrowDown}{ArrowDown}{Enter}"); // Q1 -> FAMILIARITY[1]
    await screen.findByText(Q2.text);
    await userEvent.keyboard("{ArrowDown}{Enter}");            // Q2 -> GOAL_TYPES[0]
    await screen.findByText(Q3.text);
    await userEvent.type(screen.getByRole("textbox"), "trace a request{Enter}");
    await screen.findByText(t.goal.reviewTitle);
  };

  test("no answers are shown while the interview is running", async () => {
    api.goalAnswer.mockResolvedValue({ done: false, question: Q2 });
    await start();

    expect(screen.queryByText(t.goal.answers)).toBeNull();

    await userEvent.click(screen.getByRole("radio", { name: FAMILIARITY[1] }));
    await userEvent.click(screen.getByRole("button", { name: t.goal.continue }));
    await screen.findByText(Q2.text);

    // The answer to Q1 must not be on screen beside Q2.
    expect(screen.queryByText(t.goal.answers)).toBeNull();
    expect(screen.queryByText(Q1.text)).toBeNull();
    expect(screen.queryByText(FAMILIARITY[1])).toBeNull();
  });

  test("the last answer opens the gate instead of starting the session", async () => {
    const onDone = vi.fn();
    api.goalAnswer
      .mockResolvedValueOnce({ done: false, question: Q2 })
      .mockResolvedValueOnce({ done: false, question: Q3 })
      .mockResolvedValueOnce({ done: true, goal: { primary_goal: "trace a request" } });

    render(<GoalDialogue repoUrl="https://github.com/psf/requests" onDone={onDone} />);
    await screen.findByText(Q1.text);
    await userEvent.keyboard("{ArrowDown}{Enter}");
    await screen.findByText(Q2.text);
    await userEvent.keyboard("{ArrowDown}{Enter}");
    await screen.findByText(Q3.text);
    await userEvent.type(screen.getByRole("textbox"), "trace a request{Enter}");

    await screen.findByText(t.goal.reviewTitle);
    // The whole point: nothing has started.
    expect(onDone).not.toHaveBeenCalled();
  });

  test("every question and answer is shown back, in order", async () => {
    await walkToReview();

    expect(screen.getByText(t.goal.answers)).toBeTruthy();
    for (const text of [Q1.text, Q2.text, Q3.text]) {
      expect(screen.getByText(text)).toBeTruthy();
    }
    expect(screen.getByText(FAMILIARITY[1])).toBeTruthy();
    expect(screen.getByText(GOAL_TYPES[0])).toBeTruthy();
    expect(screen.getByText("trace a request")).toBeTruthy();
  });

  test("starting is what calls onDone, with the goal the backend built", async () => {
    const onDone = vi.fn();
    api.goalAnswer
      .mockResolvedValueOnce({ done: false, question: Q2 })
      .mockResolvedValueOnce({ done: false, question: Q3 })
      .mockResolvedValueOnce({ done: true, goal: { primary_goal: "trace a request" } });
    render(<GoalDialogue repoUrl="https://github.com/psf/requests" onDone={onDone} />);
    await screen.findByText(Q1.text);
    await userEvent.keyboard("{ArrowDown}{Enter}");
    await screen.findByText(Q2.text);
    await userEvent.keyboard("{ArrowDown}{Enter}");
    await screen.findByText(Q3.text);
    await userEvent.type(screen.getByRole("textbox"), "trace a request{Enter}");
    await screen.findByText(t.goal.reviewTitle);

    await userEvent.click(screen.getByRole("button", { name: t.goal.startSession }));

    expect(onDone).toHaveBeenCalledWith("s1", { primary_goal: "trace a request" });
  });

  test("Back reopens the last question, with its answer intact", async () => {
    await walkToReview();
    api.goalBack.mockResolvedValueOnce({ question: Q3, answer: "trace a request" });

    await userEvent.click(screen.getByRole("button", { name: t.goal.back }));

    await screen.findByText(Q3.text);
    // One call: from the review, the last question is the only one to un-answer.
    expect(api.goalBack).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("textbox")).toHaveProperty("value", "trace a request");
    // And the summary is gone, because the session it described no longer exists.
    expect(screen.queryByText(t.goal.reviewTitle)).toBeNull();
    expect(screen.queryByText(t.goal.answers)).toBeNull();
  });

  test("Change on an earlier row unwinds all the way to it", async () => {
    await walkToReview();
    api.goalBack
      .mockResolvedValueOnce({ question: Q3, answer: "trace a request" })
      .mockResolvedValueOnce({ question: Q2, answer: GOAL_TYPES[0] })
      .mockResolvedValueOnce({ question: Q1, answer: FAMILIARITY[1] });

    await userEvent.click(screen.getByRole("button", { name: t.goal.editAnswer(Q1.text) }));

    await screen.findByRole("radio", { name: FAMILIARITY[1] });
    // Three answers on the server, so three calls to reopen the first question.
    expect(api.goalBack).toHaveBeenCalledTimes(3);
    expect(screen.getByRole("radio", { name: FAMILIARITY[1] })).toHaveProperty(
      "ariaChecked",
      "true",
    );
    expect(screen.queryByText(t.goal.reviewTitle)).toBeNull();
  });

  test("an answer the backend rejects never reaches the gate", async () => {
    api.goalAnswer.mockRejectedValue(new Error("invalid_goal_type_option"));
    await start();

    await userEvent.click(screen.getByRole("radio", { name: FAMILIARITY[1] }));
    await userEvent.click(screen.getByRole("button", { name: t.goal.continue }));

    await waitFor(() => expect(screen.getByText(t.errors.invalid_goal_type_option)).toBeTruthy());
    expect(screen.queryByText(t.goal.reviewTitle)).toBeNull();
  });

  test("going back past question 2 lets the follow-ups change", async () => {
    // The backend clears goal_type on the way back past Q2; the visible consequence
    // is that `total` and the later questions can differ afterwards.
    const Q2_SEVEN = q(2, Q2.text, GOAL_TYPES, 7);
    api.goalAnswer
      .mockResolvedValueOnce({ done: false, question: Q2 })
      .mockResolvedValueOnce({ done: false, question: Q3 });
    api.goalBack
      .mockResolvedValueOnce({ question: Q2, answer: GOAL_TYPES[0] })
      .mockResolvedValueOnce({ question: Q1, answer: FAMILIARITY[0] });

    await start();
    await userEvent.keyboard("{ArrowDown}{Enter}");
    await screen.findByText(Q2.text);
    await userEvent.keyboard("{ArrowDown}{Enter}");
    await screen.findByText(Q3.text);
    expect(screen.getByText(t.goal.progress(3, 6))).toBeTruthy();

    // Mid-interview at question 3: two answers held, so two calls to reach Q1.
    await userEvent.click(screen.getByRole("button", { name: t.goal.back }));
    await screen.findByText(Q2.text);
    await userEvent.click(screen.getByRole("button", { name: t.goal.back }));
    await screen.findByText(Q1.text);
    expect(api.goalBack).toHaveBeenCalledTimes(2);

    api.goalAnswer.mockResolvedValueOnce({ done: false, question: Q2_SEVEN });
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(screen.getByText(t.goal.progress(2, 7))).toBeTruthy());
  });

  test("Back is absent on the first question and present after it", async () => {
    api.goalAnswer.mockResolvedValue({ done: false, question: Q2 });
    await start();

    expect(screen.queryByRole("button", { name: t.goal.back })).toBeNull();

    await userEvent.keyboard("{ArrowDown}{Enter}");
    await screen.findByText(Q2.text);
    expect(screen.getByRole("button", { name: t.goal.back })).toBeTruthy();
  });
});

describe("a selection you have not confirmed yet", () => {
  test("survives going back and returning to the question", async () => {
    api.goalAnswer
      .mockResolvedValueOnce({ done: false, question: Q2 })   // Q1 confirmed
      .mockResolvedValueOnce({ done: false, question: Q2 });  // Q1 re-confirmed -> Q2 again
    api.goalBack.mockResolvedValueOnce({ question: Q1, answer: FAMILIARITY[1] });

    await start();
    // Confirm Q1 so there is somewhere to go back to.
    await userEvent.click(screen.getByRole("radio", { name: FAMILIARITY[1] }));
    await userEvent.click(screen.getByRole("button", { name: t.goal.continue }));
    await screen.findByText(Q2.text);

    // Choose on Q2 WITHOUT confirming, then step back and come forward again.
    await userEvent.click(screen.getByRole("radio", { name: GOAL_TYPES[2] }));
    await userEvent.click(screen.getByRole("button", { name: t.goal.back }));
    await screen.findByText(Q1.text);
    await userEvent.click(screen.getByRole("button", { name: t.goal.continue }));
    await screen.findByText(Q2.text);

    expect(screen.getByRole("radio", { name: GOAL_TYPES[2] })).toHaveProperty(
      "ariaChecked",
      "true",
    );
  });

  test("free text survives the same round trip", async () => {
    api.goalAnswer
      .mockResolvedValueOnce({ done: false, question: Q2 })
      .mockResolvedValueOnce({ done: false, question: Q3 })
      .mockResolvedValueOnce({ done: false, question: Q3 });
    api.goalBack.mockResolvedValueOnce({ question: Q2, answer: GOAL_TYPES[0] });

    await start();
    await userEvent.keyboard("{ArrowDown}{Enter}");
    await screen.findByText(Q2.text);
    await userEvent.keyboard("{ArrowDown}{Enter}");
    await screen.findByText(Q3.text);

    await userEvent.type(screen.getByRole("textbox"), "trace a redirect");
    await userEvent.click(screen.getByRole("button", { name: t.goal.back }));
    await screen.findByText(Q2.text);
    await userEvent.click(screen.getByRole("button", { name: t.goal.continue }));
    await screen.findByText(Q3.text);

    expect(screen.getByRole("textbox")).toHaveProperty("value", "trace a redirect");
  });

  test("a stale draft is not restored onto a different follow-up question", async () => {
    // Q6 differs by goal type. A draft recorded against one follow-up must not
    // reappear on another, because they are different questions.
    const FOLLOWUP_A = q(6, "Is there a part of the system you're most curious about?", null);
    const FOLLOWUP_B = q(6, "What error or unexpected behavior are you seeing?", null, 7);
    api.goalAnswer
      .mockResolvedValueOnce({ done: false, question: FOLLOWUP_A })
      .mockResolvedValueOnce({ done: false, question: FOLLOWUP_B });
    api.goalBack.mockResolvedValueOnce({ question: Q1, answer: FAMILIARITY[0] });

    await start();
    await userEvent.keyboard("{ArrowDown}{Enter}");
    await screen.findByText(FOLLOWUP_A.text);
    await userEvent.type(screen.getByRole("textbox"), "the adapter layer");

    await userEvent.click(screen.getByRole("button", { name: t.goal.back }));
    await screen.findByText(Q1.text);
    await userEvent.click(screen.getByRole("button", { name: t.goal.continue }));
    await screen.findByText(FOLLOWUP_B.text);

    expect(screen.getByRole("textbox")).toHaveProperty("value", "");
  });
});

describe("when the interview has expired underneath the review", () => {
  const reachReview = async () => {
    api.goalAnswer
      .mockResolvedValueOnce({ done: false, question: Q2 })
      .mockResolvedValueOnce({ done: false, question: Q3 })
      .mockResolvedValueOnce({ done: true, goal: { primary_goal: "trace a request" } });
    await start();
    await userEvent.keyboard("{ArrowDown}{Enter}");
    await screen.findByText(Q2.text);
    await userEvent.keyboard("{ArrowDown}{Enter}");
    await screen.findByText(Q3.text);
    await userEvent.type(screen.getByRole("textbox"), "trace a request{Enter}");
    await screen.findByText(t.goal.reviewTitle);
  };

  test("the gate stays usable and says starting still works", async () => {
    await reachReview();
    // The goal dialogue lives in memory on the server: a restart takes it.
    api.goalBack.mockRejectedValue(new Error("session_not_found"));

    await userEvent.click(screen.getByRole("button", { name: t.goal.back }));

    await waitFor(() => expect(screen.getByText(t.goal.editExpired)).toBeTruthy());
    // Still on the review, and starting is still offered — /session/start does not
    // need the interview, only the goal, which is already in hand.
    expect(screen.getByText(t.goal.reviewTitle)).toBeTruthy();
    expect(screen.getByRole("button", { name: t.goal.startSession })).toBeTruthy();
  });

  test("the ways backwards are removed rather than left to fail again", async () => {
    await reachReview();
    api.goalBack.mockRejectedValue(new Error("session_not_found"));

    await userEvent.click(screen.getByRole("button", { name: t.goal.back }));
    await waitFor(() => expect(screen.getByText(t.goal.editExpired)).toBeTruthy());

    expect(screen.queryByRole("button", { name: t.goal.back })).toBeNull();
    expect(screen.queryByRole("button", { name: t.goal.editAnswer(Q1.text) })).toBeNull();
  });

  test("starting still hands over the goal the backend built", async () => {
    const onDone = vi.fn();
    api.goalAnswer
      .mockResolvedValueOnce({ done: false, question: Q2 })
      .mockResolvedValueOnce({ done: false, question: Q3 })
      .mockResolvedValueOnce({ done: true, goal: { primary_goal: "trace a request" } });
    render(<GoalDialogue repoUrl="https://github.com/psf/requests" onDone={onDone} />);
    await screen.findByText(Q1.text);
    await userEvent.keyboard("{ArrowDown}{Enter}");
    await screen.findByText(Q2.text);
    await userEvent.keyboard("{ArrowDown}{Enter}");
    await screen.findByText(Q3.text);
    await userEvent.type(screen.getByRole("textbox"), "trace a request{Enter}");
    await screen.findByText(t.goal.reviewTitle);
    api.goalBack.mockRejectedValue(new Error("session_not_found"));
    await userEvent.click(screen.getByRole("button", { name: t.goal.back }));
    await waitFor(() => expect(screen.getByText(t.goal.editExpired)).toBeTruthy());

    await userEvent.click(screen.getByRole("button", { name: t.goal.startSession }));

    expect(onDone).toHaveBeenCalledWith("s1", { primary_goal: "trace a request" });
  });

  test("mid-interview it says to start over, because there is no goal yet", async () => {
    api.goalAnswer.mockResolvedValue({ done: false, question: Q2 });
    await start();
    await userEvent.keyboard("{ArrowDown}{Enter}");
    await screen.findByText(Q2.text);
    api.goalBack.mockRejectedValue(new Error("session_not_found"));

    await userEvent.click(screen.getByRole("button", { name: t.goal.back }));

    await waitFor(() => expect(screen.getByText(t.goal.sessionExpired)).toBeTruthy());
    expect(screen.queryByText(t.goal.editExpired)).toBeNull();
  });
});
