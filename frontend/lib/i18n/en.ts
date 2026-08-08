/**
 * English is the source dictionary. `he.ts` is typed against `Dictionary`, so
 * adding a key here is a type error there until it is translated — the two
 * cannot drift apart silently.
 *
 * Values that take a runtime value are functions rather than templates with
 * placeholder tokens, so the argument list is type-checked at the call site.
 */
export const en = {
  appName: "CodeOnboard",
  tagline:
    "Build a real understanding of an unfamiliar codebase, one anchored concept at a time.",

  // --- language switcher ---
  language: {
    label: "Language",
    en: "English",
    he: "עברית",
  },

  // --- home: repo step ---
  home: {
    repoLabel: "Repository to read",
    repoPlaceholder: "https://github.com/psf/requests",
    recent: "Recent",
    checking: "Checking the repository…",
    start: "Start",
    repoUnreachable: "That repository couldn't be opened.",
    serverUnreachable: "Couldn't reach the server.",
    pipelineFailed: "Couldn't build your learning path.",
  },

  // --- home: pipeline progress ---
  starting: {
    label: "Reading the repository",
    phases: [
      "Cloning the repository",
      "Parsing files into concepts",
      "Indexing for retrieval",
      "Planning your route",
    ],
    elapsed: (seconds: number) =>
      `${seconds}s elapsed · usually about a minute on a small repo`,
  },

  // --- home: failure ---
  failed: {
    label: "Couldn't build your learning path",
    reassurance:
      "Your answers are saved, so retrying won't make you go through the questions again.",
    tryAgain: "Try again",
    differentRepo: "Use a different repository",
  },

  // --- goal interview ---
  goal: {
    starting: "Starting the interview…",
    progress: (index: number, total: number) => `Question ${index} of ${total}`,
    answerPlaceholder: "Your answer…",
    thinking: "Thinking…",
    continue: "Continue",
    enterHint: "↵ to continue",
    answerFailed: "Couldn't save that answer.",
  },

  // --- session shell ---
  session: {
    readiness: "Readiness",
    hideSource: "Hide source",
    showSource: "Show source",
    startingOver: "Starting over…",
    startOver: "Start over",
    tabLesson: "Lesson",
    tabMap: "Progress map",
    mapHint: (count: number) =>
      `${count} concepts · click any stop to go there · esc to return`,
    loading: "Loading session…",
    loadFailed: "Couldn't load this session.",
    retryLoad: "Try loading again",
    jumpFailed: "Couldn't move to that stop.",
    firstLesson: "Loading your first lesson…",
    // `depth` comes back from the Goal Agent as a fixed English enum so the
    // agents can reason over it; the label is chosen here.
    depth: {
      overview: "overview",
      moderate: "moderate",
      deep: "deep",
    } as Record<string, string>,
  },

  // --- route rail ---
  rail: {
    title: "Your route",
    openMap: "Open map",
    addedAfterConfusion: "added after confusion",
    markedWeak: "⚑ marked weak",
  },

  // --- lesson panel ---
  lesson: {
    writing: "Writing this lesson…",
    warmUpHeading: "Warm-up · added after confusion",
    stopOf: (position: number, total: number) => `Stop ${position} of ${total}`,
    lines: (start: number, end: number) => `lines ${start}–${end}`,
    recoveredLabel: "The warm-up worked",
    recoveredBody: "You got this one after studying",
    recoveredBodyEnd:
      "first. It stays marked as a rough patch, but you came back from it.",
    walkthrough: "Walkthrough",
    yourAnswers: (count: number) => `Your answers (${count})`,
    youWrote: "You wrote",
    feedback: "Feedback",
    checkUnderstanding: "Check your understanding",
    answerPlaceholder: "Write your answer…",
    grading: "Grading…",
    submit: "Submit",
    skipStop: "Skip this stop",
    submitHint: "⌘↵ to submit",
    loadingShort: "Loading…",
    nextStop: "Next stop →",
    buildWarmUp: "Build me a warm-up",
    startWarmUp: "Start the warm-up →",
    skipItMoveOn: "Skip it, move on",
    moveOnAnyway: "Move on anyway",
    finishEarly: "Finish session early",
    gradeFailed: "Couldn't grade that answer. Try again.",
    advanceFailed: "Couldn't move to the next stop.",
    warmUpFailed: "Couldn't build a warm-up for this one.",
    warmUpAdded:
      "We've added a shorter warm-up before this stop to build up to it.",
    warmUpExists:
      "You've already had a warm-up for this stop, so there isn't another one to add.",
    warmUpUnavailable:
      "We couldn't build a warm-up for this one, so it's your call how to continue.",
    verdict: {
      understood: "Understood",
      partial: "Partly there",
      confused: "Not yet",
      "off-topic": "Off topic",
    } as Record<string, string>,
    when: {
      justNow: "just now",
      minutes: (n: number) => `${n}m ago`,
      hours: (n: number) => `${n}h ago`,
    },
  },

  // --- completion ---
  completion: {
    tabSummary: "Summary",
    tabMap: "Your map",
    label: "Session complete",
    heading: (understood: number, total: number) =>
      `You understood ${understood} of ${total} concepts`,
    body:
      "Your map is saved. Come back to this repo and goal and you'll pick up exactly where you left off — including the stops still marked weak.",
    anotherPass: (count: number) => `Worth another pass (${count})`,
    newSession: "Start a new session",
    goHome: "Go home",
  },

  // --- map view ---
  map: {
    label: "What you understand so far",
    thisCodebase: "This codebase",
    conceptsUnderstood: (understood: number, total: number) =>
      `${understood} of ${total} concepts understood`,
    filesTouched: (count: number) =>
      `${count} file${count === 1 ? "" : "s"} touched`,
    markedWeak: (count: number) => `${count} marked weak`,
    readiness: "readiness",
    byKind: "By kind of understanding",
    topicsTouched: "Topics touched",
    whereInRepo: "Where in the repository",
    theRoute: "The route",
    unlocks: (title: string) => `· unlocks “${title}”`,
    understoodOfTotal: (understood: number, total: number) =>
      `${understood} of ${total} understood`,
  },

  // --- shared vocabularies ---
  // Keys match the concept-tag and understanding-state values the backend
  // emits. Those stay English on the wire; only the label is translated.
  tags: {
    architecture: "architecture",
    flow: "flow",
    extension_point: "extension point",
    risk: "risk",
    test_coverage: "test coverage",
    component: "component",
  } as Record<string, string>,

  states: {
    understood: "understood",
    partial: "partial",
    failed: "needs another pass",
    not_started: "not started",
  } as Record<string, string>,

  // --- backend error slugs ---
  // FastAPI raises these as `detail`; they reach the UI verbatim otherwise.
  errors: {
    session_not_found: "That session no longer exists.",
    node_not_found: "That stop isn't part of this session.",
    session_has_no_current_node: "This session has no current stop.",
    no_lesson_rendered_yet: "The lesson hasn't loaded yet — give it a moment.",
    invalid_path: "That file path isn't inside the repository.",
    file_not_found: "That file isn't in the repository.",
    no_graph: "The learning path couldn't be built for this repository.",
    synthesis_failed: "Couldn't make sense of those answers. Try rephrasing.",
  } as Record<string, string>,
};

// Deliberately not `as const`: the shape is the contract, the exact English
// wording is not. With literal types every Hebrew string would be a type error.
export type Dictionary = typeof en;
