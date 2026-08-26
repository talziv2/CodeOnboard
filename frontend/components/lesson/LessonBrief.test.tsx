import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import LessonBrief from "@/components/lesson/LessonBrief";
import { node } from "@/test/factories";
import { t } from "@/lib/strings";

/**
 * WHICH STOP THIS IS — and, when it is not one, saying so.
 *
 * `buildRoute` gives a non-station the number of the stop it PRECEDES rather
 * than one of its own, which is only safe while every caller checks before
 * printing it. This one did not: it guarded on `isPrerequisite` alone, so an
 * `optional` unit announced "Stop 3 of 13" over the very number the next
 * required stop legitimately holds. Two stops, one number, and nothing on
 * screen to say which was the real one.
 */
const brief = (over: Parameters<typeof node>[1], position = 3) =>
  render(
    <LessonBrief
      node={node("n2", { title: "Pool keys", ...over })}
      position={position}
      total={13}
      isPrerequisite={false}
      onFileClick={vi.fn()}
    />
  );

describe("the position line", () => {
  test("an ordinary stop names its place on the walk", () => {
    brief({});
    expect(screen.getByText(t.lesson.stopOf(3, 13))).toBeTruthy();
  });

  test("an optional unit says it is off the walk instead of borrowing a number", () => {
    brief({ priority: "optional" });
    expect(screen.getByText(t.map.stop.offRoute)).toBeTruthy();
    expect(screen.queryByText(t.lesson.stopOf(3, 13))).toBeNull();
  });

  test("a warm-up still reads as a warm-up, not as off the walk", () => {
    render(
      <LessonBrief
        node={node("p1", { title: "Warm-up" })}
        position={3}
        total={13}
        isPrerequisite
        onFileClick={vi.fn()}
      />
    );
    expect(screen.getByText(t.lesson.warmUpHeading)).toBeTruthy();
    expect(screen.queryByText(t.lesson.stopOf(3, 13))).toBeNull();
  });
});
