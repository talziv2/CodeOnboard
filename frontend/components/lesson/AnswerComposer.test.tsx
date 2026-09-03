import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import AnswerComposer from "@/components/lesson/AnswerComposer";
import { t } from "@/lib/strings";

/**
 * The learner picks the INPUT, not the marking.
 *
 * When a lesson ships `choices`, the composer offers a four-option radio group
 * and a link to the textarea instead. Both leave through the same
 * `onAnswerChange` / `onSubmit` — there is no "correct" option here, and the
 * single-composer invariant (one `answer` state, one writer) still holds. A
 * lesson without `choices` renders exactly as it always did.
 */

const CHOICES = [
  "The mutated PreparedRequest",
  "A brand-new Session",
  "None — it mutates in place",
  "The raw response bytes",
];

function setup(props: Partial<React.ComponentProps<typeof AnswerComposer>> = {}) {
  const onAnswerChange = vi.fn();
  const onSubmit = vi.fn();
  const onSkip = vi.fn();
  const utils = render(
    <AnswerComposer
      prompt="What does `__call__` return?"
      answer=""
      onAnswerChange={onAnswerChange}
      onSubmit={onSubmit}
      onSkip={onSkip}
      loading={false}
      error={null}
      {...props}
    />,
  );
  const submit = () =>
    screen.getByRole("button", { name: t.lesson.submit }) as HTMLButtonElement;
  return { onAnswerChange, onSubmit, onSkip, submit, ...utils };
}

describe("without choices", () => {
  test("renders the textarea and no mode toggle", () => {
    setup();
    expect(screen.queryByPlaceholderText(t.lesson.answerPlaceholder)).not.toBeNull();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.queryByText(t.lesson.chooseFromOptions)).toBeNull();
    expect(screen.queryByText(t.lesson.writeOwnAnswer)).toBeNull();
  });
});

describe("with choices", () => {
  test("renders one radio per option and starts in choose mode", () => {
    setup({ choices: CHOICES });
    expect(screen.getAllByRole("radio")).toHaveLength(4);
    expect(screen.queryByPlaceholderText(t.lesson.answerPlaceholder)).toBeNull();
  });

  test("selecting an option reports that option's text as the answer", async () => {
    const { onAnswerChange } = setup({ choices: CHOICES });
    await userEvent.click(screen.getByText(CHOICES[0]));
    expect(onAnswerChange).toHaveBeenCalledWith(CHOICES[0]);
  });

  test("the selected option checks its radio and enables Submit", () => {
    const { submit } = setup({ choices: CHOICES, answer: CHOICES[2] });
    expect((screen.getByRole("radio", { name: CHOICES[2] }) as HTMLInputElement).checked).toBe(true);
    expect(submit().disabled).toBe(false);
  });

  test("Submit is disabled until an option is picked", () => {
    const { submit } = setup({ choices: CHOICES });
    expect(submit().disabled).toBe(true);
  });

  test("switching to write mode clears the answer and shows the textarea", async () => {
    const { onAnswerChange } = setup({ choices: CHOICES, answer: CHOICES[0] });
    await userEvent.click(screen.getByText(t.lesson.writeOwnAnswer));
    expect(onAnswerChange).toHaveBeenCalledWith("");
    expect(screen.queryByPlaceholderText(t.lesson.answerPlaceholder)).not.toBeNull();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.queryByText(t.lesson.chooseFromOptions)).not.toBeNull();
  });

  test("switching back to choose mode also clears the answer", async () => {
    const { onAnswerChange } = setup({ choices: CHOICES });
    await userEvent.click(screen.getByText(t.lesson.writeOwnAnswer));
    onAnswerChange.mockClear();
    await userEvent.click(screen.getByText(t.lesson.chooseFromOptions));
    expect(onAnswerChange).toHaveBeenCalledWith("");
    expect(screen.getAllByRole("radio")).toHaveLength(4);
  });
});
