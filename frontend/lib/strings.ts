/**
 * Every piece of UI copy, in one place. The app is English-only; this exists so
 * wording lives apart from layout, not to support switching languages.
 *
 * Values that take a runtime value are functions rather than templates with
 * placeholder tokens, so the argument list is type-checked at the call site.
 */
export const t = {
  appName: "CodeOnboard",
  tagline:
    "Build a real understanding of an unfamiliar codebase, one anchored concept at a time.",

  // --- home: repo step ---
  home: {
    repoLabel: "Repository to read",
    repoPlaceholder: "https://github.com/psf/requests",
    recent: "Recent",
    checking: "Checking the repository…",
    start: "Start",
    // Sets the expectation BEFORE the wait exists, which is a different
    // experience from discovering it. Two numbers were considered and both were
    // refused: "two to four minutes" (the concept's original wording) is
    // unmeasured — we have no distribution across repository sizes or cached
    // versus cold runs — and "five short questions" is wrong, which is worse than
    // vague. `questions.py` asks 5 core questions plus 1 follow-up for five of
    // the goal types and 2 for `improve_existing_system` and `debug_issue`, so
    // the real count is six or seven and is not known until Q2 is answered.
    // Six-or-seven is the honest span; the wait is described by its shape.
    expectation:
      "Six or seven short questions, then a few minutes while we read the repository — longer for large ones.",
    repoUnreachable: "That repository couldn't be opened.",
    serverUnreachable: "Couldn't reach the server.",
    pipelineFailed: "Couldn't build your learning path.",
  },

  // --- home: pipeline progress ---
  //
  // The stage list, the stage the run is in, and every activity line below are
  // REAL: the backend reports each transition and each exploration tool call as
  // it happens (backend/pipeline/progress.py), and the client polls it while
  // /session/start blocks. Keys come from the backend; all wording is here.
  //
  // The one thing that is not measured is a percentage. The bar is drawn from
  // stages completed, and `hints` fills the gaps where nothing streams — the
  // planning call is a single opaque request, so there is genuinely nothing to
  // report until it returns. Rotating a description of the work is honest;
  // inventing a number that creeps toward 100% is not.
  starting: {
    label: "Reading the repository",
    // Keyed on backend stage keys: clone + parse (Layer A), survey the
    // repository (Layer B), read the docs, investigate the goal (Layer C), then
    // plan. There is no indexing step — nothing is embedded or stored for
    // retrieval.
    stages: {
      clone: "Cloning the repository",
      structure: "Mapping the code structure",
      survey: "Surveying the architecture",
      documentation: "Reading the documentation",
      investigation: "Investigating your goal",
      plan: "Planning your route",
    } as Record<string, string>,
    // What the exploration is doing right now, keyed on the tool it called.
    // `target` is a path, a symbol or a pattern — whatever that tool was aimed at.
    activity: {
      read_file: (target: string) => `Reading ${target}`,
      search_code: (target: string) => `Searching for ${target}`,
      symbols: (target: string) => `Outlining ${target}`,
      list_files: (target: string) => `Listing ${target}`,
      neighbors: (target: string) => `Tracing what touches ${target}`,
      propose_anchor: (target: string) => `Verifying ${target}`,
    } as Record<string, (target: string) => string>,
    // Fallback when a tool is reported that this list doesn't know — a new
    // primitive should read as unfamiliar, not as nothing happening.
    activityUnknown: (target: string) => (target ? `Looking at ${target}` : "Looking around"),
    // Shown while a stage is running but has nothing to stream: no tool calls
    // (the survey came from cache) or none possible (the planning call is one
    // opaque request). Rotated so the screen isn't frozen; each line describes
    // work the stage is actually doing.
    hints: {
      clone: ["Fetching a shallow clone — history isn't needed"],
      structure: [
        "Parsing every Python file into a syntax tree",
        "Indexing symbols with their exact line ranges",
        "Resolving imports between modules",
      ],
      survey: [
        "Accounting for every subsystem in the repository",
        "Finding the entry points and core abstractions",
        "Checking each citation resolves to real code",
      ],
      documentation: ["Collecting the README and module docstrings"],
      investigation: [
        "Following the paths your goal turns on",
        "Reading the code behind each claim",
        "Verifying every citation against the repository",
      ],
      plan: [
        "Choosing what you need to learn, and in what order",
        "Cutting the curriculum to a journey that fits your goal",
        "Anchoring each stop to verified code",
      ],
    } as Record<string, string[]>,
    lookups: (count: number) =>
      `${count} lookup${count === 1 ? "" : "s"} so far`,
    elapsed: (seconds: number) =>
      `${seconds}s elapsed · usually two to four minutes`,
    // Past the span the line above promises, that line stops being reassurance and
    // starts being a thing the screen is getting wrong. Measured runs land around
    // 2m40s, so five minutes is outside normal rather than at its edge.
    elapsedLong: (seconds: number) =>
      `${Math.floor(seconds / 60)}m ${seconds % 60}s elapsed · taking longer than usual`,
    // The files the exploration has actually opened, accumulated from activity the
    // backend already streams and the screen currently shows once and discards.
    //
    // Named for exactly what it is: `read_file` targets. A list called "explored"
    // that quietly folded in search patterns and symbol names would be a list the
    // learner cannot check against their own repository, which is the only thing
    // this list is for.
    filesRead: (count: number) => (count === 1 ? "1 file read" : `${count} files read`),
    // The goal, kept on screen through the wait — the synthesised version rather
    // than the raw transcript, because the review gate already showed the answers
    // and the learner confirmed them. This is what they confirmed.
    goalHeading: "What you asked for",
  },

  // --- home: failure ---
  failed: {
    label: "Couldn't build your learning path",
    reassurance:
      "Your answers are saved, so retrying won't make you go through the questions again.",
    tryAgain: "Try again",
    differentRepo: "Use a different repository",
  },

  // --- display settings ---
  settings: {
    open: "Display settings",
    title: "Display",
    theme: "Theme",
    themes: {
      system: "System",
      light: "Light",
      dark: "Dark",
    } as Record<string, string>,
    textSize: "Text size",
    // Shown inside the size buttons themselves, so they double as a preview.
    textSizes: {
      small: "S",
      medium: "M",
      large: "L",
      xlarge: "XL",
    } as Record<string, string>,
    textSizeNames: {
      small: "Small",
      medium: "Medium",
      large: "Large",
      xlarge: "Extra large",
    } as Record<string, string>,
    close: "Close",
    note: "Saved on this device.",
  },

  // --- goal interview ---
  goal: {
    starting: "Starting the interview…",
    progress: (index: number, total: number) => `Question ${index} of ${total}`,
    answerPlaceholder: "Your answer…",
    thinking: "Thinking…",
    continue: "Continue",
    back: "Back",
    enterHint: "↵ to continue",
    // The options list is driven by the keyboard, so it says so — and it says
    // what the two keys DO, because selecting and confirming are separate here
    // and a hint that blurred them would undo the point of separating them.
    optionHint: "↑↓ to choose · ↵ to continue",
    // Shown only on the review step, never beside a live question: a running
    // transcript turned every question into a re-read of everything already said.
    answers: "Your answers",
    reviewLabel: "Before we start",
    reviewTitle: "Ready to start?",
    // Says what the answers are FOR, which is why reviewing them is worth a beat.
    // No duration here either — the landing already set that expectation honestly,
    // and repeating it as a number is where invented figures creep back in.
    reviewNote:
      "These answers decide what gets read and what gets taught. Change anything that looks wrong — nothing starts until you say so.",
    startSession: "Let's start",
    // Two different dead ends, and they are not the same dead end. On the review
    // step the goal is already in hand, so the session can still start — only
    // editing is lost. Mid-interview there is no goal yet, so there is nothing to
    // do but begin again. Reachable in normal use: the goal dialogue lives in
    // memory, so a backend restart or the retention cap can take it.
    editExpired:
      "These answers can no longer be changed — the interview behind them has expired. You can still start with them as they are, or reload to answer again.",
    sessionExpired: "The interview has expired. Reload the page to answer again.",
    edit: "Change",
    editAnswer: (question: string) => `Change your answer to: ${question}`,
    answerFailed: "Couldn't save that answer.",
    backFailed: "Couldn't go back to the previous question.",
    // Every question is required: the interview's answers are the only input the
    // whole pipeline has, so there is nothing sensible to infer from a skipped
    // one. (Six or seven of them, not five — `total` on the wire is documented as
    // a lower bound until `goal_type` is known, because two goal types add a
    // second follow-up.)
    answerRequired: "Answer to continue",
  },

  // --- session shell ---
  session: {
    // Two measures, never one (learning-graph.md §5.4). "Readiness" alone read
    // 0% for someone who walked the whole journey without answering anything.
    // "Goal readiness" is retired as a learner-facing label: it sounds like a
    // calibrated prediction of readiness, and this measure is demonstrated
    // coverage of the required set (M3a.3, Model A′).
    demonstrated: "Demonstrated",
    goalReadiness: "Goal readiness",
    // "Stops taken", not "Journey": the number is a COUNT of stops settled, and
    // the lesson header beside it shows a POSITION ("Stop 9 of 13"). Labelled
    // "Journey 13/13" the two read as a contradiction — verified in the browser
    // on a session where all 13 stops are visited but the learner is back on
    // stop 9, which is a legitimate state and looked like a bug.
    journey: "Stops taken",
    journeyCount: (settled: number, total: number) => `${settled}/${total}`,
    readiness: "Readiness",
    hideSource: "Hide source",
    showSource: "Show source",
    startingOver: "Starting over…",
    startOver: "Start over",
    // The session-level actions, behind one control. Named for what they act on
    // rather than what they look like: "⋯" is not a word.
    menu: "Session actions",
    menuTitle: "Session",
    finish: "Finish session",
    // The only confirmed action here, and the confirmation says what survives
    // rather than asking "are you sure" — the real question is whether the work
    // already done is lost, and it is not.
    finishConfirm:
      "End the journey here? Everything you have answered is kept, and you'll see the summary of what you covered.",
    finishYes: "Finish it",
    finishNo: "Keep going",
    // The rail's own toggle (UI note 4). Says which way it goes rather than
    // naming the thing — "Route" alone would read as a link to the map.
    hideRail: "Hide route",
    showRail: "Show route",
    tabLesson: "Lesson",
    tabMap: "Progress map",
    /**
     * The one bar's labels, keyed by tab.
     *
     * `Understanding` was chosen over `Practice`, `Questions` and `Demonstrate`.
     * `Practice` implies drills, and a stop asks once — the answer is evidence that
     * moves goal readiness, not a repetition. `Questions` is narrower than what the
     * surface holds (verdicts, gaps, previous answers, what was resolved).
     * `Understanding` matches the header's own `Demonstrated` measure and the
     * `understanding_state` vocabulary already on the wire.
     *
     * `Map` rather than `Progress map` here: in a three-tab bar the qualifier is
     * the longest word on the bar and earns nothing, and the two-tab bar keeps
     * `tabMap` above so nothing changes for `next`.
     */
    tab: {
      lesson: "Lesson",
      understanding: "Understanding",
      map: "Map",
      // The half of the old Map tab that was never a map: the measures, the
      // outcome bands, the patterns, the breakdowns and the session log.
      // `Analysis` over `Progress`, which the session header already reports at
      // all times, and over `Insights`, which promises interpretation this layer
      // does not do — everything in it is a count over evidence the learner can
      // open.
      analysis: "Analysis",
    } as Record<string, string>,
    /**
     * The two modes, and the switch that holds them.
     *
     * Verbs for what the learner is DOING, not nouns for what is on screen: the
     * tabs already name the views, and a switch labelled with two more nouns
     * would read as four peer destinations again — which is the arrangement it
     * replaces. `Route` over `Navigate` because the product's own vocabulary is
     * route, stop, rail, journey, and over `Map` because the map is one of the
     * two tabs inside it.
     */
    mode: {
      learn: "Learn",
      route: "Route",
    } as Record<string, string>,
    // Names the group for a screen reader, which otherwise hears two unexplained
    // toggles ahead of the tabs.
    modeLabel: "What you're doing",
    tabChanged: (label: string) => `${label} has changed since you last looked`,
    // "go there" until stops opened a card instead of jumping. The hint has to
    // describe what the click actually does, or it promises a navigation the
    // learner then has to take a second step to get.
    mapHint: (count: number) =>
      `${count} concepts · click any stop to read it · esc to return`,
    loading: "Loading session…",
    loadFailed: "Couldn't load this session.",
    retryLoad: "Try loading again",
    jumpFailed: "Couldn't move to that stop.",
    firstLesson: "Loading your first lesson…",
    // `depth` comes back from the Goal Agent as a fixed enum so the agents can
    // reason over it; the label is chosen here.
    depth: {
      overview: "overview",
      moderate: "moderate",
      deep: "deep",
    } as Record<string, string>,
  },

  // --- welcome page ---
  //
  // Shown once the pipeline has built a path, before the first lesson. Two
  // halves: what this repository is (written by the Briefing Agent from the
  // survey and the README) and who the system thinks the reader is (derived
  // from the interview answers alone — no model involved).
  welcome: {
    label: "Before you start",
    // In the session header, where it is a way back rather than a first visit.
    headerLink: "Briefing",
    heading: "This repository, and you",
    briefingLabel: "What you're about to read",
    // Said plainly rather than hidden, because the difference is real: one
    // paragraph was written against this profile, the other is the repository's
    // generic architecture summary.
    personalized: "Written for your profile",
    generic: "General summary — couldn't be tailored this time",
    notesLabel: "Worth knowing",
    unavailable:
      "There wasn't enough grounded material to describe this repository, so " +
      "there's nothing here rather than a guess. Your route is still ready.",
    loading: "Writing your briefing…",
    failed: "Couldn't write the briefing — your route is still ready.",
    // --- the profile card ---
    profileLabel: "Your learner profile",
    profileNote: "Built from your answers. Every lesson is pitched against it.",
    goalLabel: "Goal",
    focusLabel: "Focus",
    familiarityLabel: "Starting point",
    depthLabel: "Depth",
    backgroundLabel: "You already know",
    // The way out of a profile the learner disagrees with (P4). `Start over` in
    // the session menu re-runs the pipeline with the SAME answers, which is the one
    // thing someone who dislikes their profile does not want.
    changeAnswers: "Change",
    changeAnswersHint: "Answer the questions again for this repository",
    routeLabel: "Your route",
    routeCount: (stops: number, areas: number) =>
      areas > 0
        ? `${stops} stops across ${areas} ${areas === 1 ? "chapter" : "chapters"}`
        : `${stops} ${stops === 1 ? "stop" : "stops"}`,
    // Per chapter, in the route overview (P4).
    routeStops: (n: number) => (n === 1 ? "1 stop" : `${n} stops`),
    // A pre-B3 graph has no chapters, so `splitJourney` returns one unnamed
    // section. It still has a route; it just has nothing to call the parts.
    routeUngrouped: "The route",
    // Said on the briefing because the counts above exclude them, and a learner who
    // later finds extra stops in the rail should have been told they existed.
    routeOptional: (n: number) =>
      n === 1
        ? "1 more stop is optional — off the default walk, still reachable"
        : `${n} more stops are optional — off the default walk, still reachable`,
    begin: "Start learning",
    // The primary names where it goes (P4). "Start learning" labels a door; this
    // labels the room behind it, which is the difference between being asked to
    // commit and being told what to.
    beginNamed: (title: string) => `Start: ${title}`,
    // The interview answers are fixed strings and fixed keys; these are the
    // short forms that fit on a card. An unrecognised value falls back to
    // itself, so a new option shows up as its own wording rather than blank.
    familiarity: {
      "Starting fresh — never looked at it": "New to it",
      "Skimmed the README or docs": "Read the docs",
      "Looked at some code but still confused": "Some code, still fuzzy",
      "Used it before, now diving into the source": "Used it, now reading it",
    } as Record<string, string>,
    goalType: {
      use_library: "Using it in your own project",
      understand_system: "Reading it to understand it",
      understand_component: "Diving into one component",
      understand_architecture: "Understanding the architecture",
      contribute_code: "Contributing code",
      improve_existing_system: "Changing it safely",
      debug_issue: "Debugging an issue",
    } as Record<string, string>,
    codeDepth: {
      map: "The map",
      working: "Working knowledge",
      implementation: "The internals",
    } as Record<string, string>,
    // The goal-type follow-ups. Only one goal_type fills each of these, so the
    // card shows whichever are present rather than reserving room for all.
    followups: {
      change_target: "The change you want to make",
      risk_tolerance: "How safety-critical it is",
      contribution_context: "What you're contributing",
      error_description: "The error you're hitting",
      tried_so_far: "What you've tried",
    } as Record<string, string>,
  },

  // --- the first-run tour ---
  //
  // WORDING RULE: every step says what the thing is FOR, never what it is called.
  // "This is the route rail" teaches a name the learner will never need; "your
  // journey, and nothing in it is locked" teaches the one fact that changes how
  // they use it. A tour that narrates the furniture is a tour people skip.
  //
  // Gated steps carry a `cue` as well as a `body`. The cue is the instruction, and
  // it is shown only while the step is actually waiting — walking back through the
  // tour re-reads the same steps without re-arming them (see `lib/tour.ts`), and a
  // step that still said "click it" with a `Next` button beside it would be giving
  // two different instructions at once.
  tour: {
    /** The bubble's own chrome. */
    step: (n: number, total: number) => `${n} of ${total}`,
    next: "Next",
    back: "Back",
    skip: "Skip tour",
    done: "Got it",
    close: "Close the tour",
    /** Announced when a step opens, for anyone not seeing the spotlight move. */
    announce: (n: number, total: number, title: string) => `Tour step ${n} of ${total}: ${title}`,
    replay: "Replay the tour",

    steps: {
      intro: {
        title: "A quick tour",
        body:
          "Three parts to this screen: your route down the side, the lesson in the middle, and the code beside it. About a minute to walk through them.",
        action: "Show me",
      },
      rail: {
        title: "Your route",
        body:
          "Every stop on the journey, grouped into chapters. The one in cyan is where you are, and nothing is locked — click any stop to go there, or a chapter heading to read what it covers.",
      },
      brief: {
        title: "What this stop is for",
        body:
          "The objective is the claim you should be able to make when you're done. It isn't a summary — it's the standard your answer gets marked against. It stays pinned here while you scroll.",
      },
      code: {
        title: "Anchored to real code",
        body:
          "Every lesson points at actual lines in the repository, never at an invented example.",
        cue: "Open one to see it.",
      },
      source: {
        title: "The code, beside the lesson",
        body:
          "It stays open next to what you're reading — dock it, float it, drag it wider, or close it. When it's closed, “Show source” up on the bar brings it back.",
      },
      understanding: {
        title: "Where you answer",
        body:
          "The lesson is what to read; this is the other half. The question lives here, along with your verdict, your earlier answers, and anything you got wrong — which stays on the record until you clear it by answering a fresh question about it.",
        cue: "Open it.",
      },
      composer: {
        title: "How a stop counts",
        body:
          "Answer in your own words and submit — ⌘↵ works too. It's marked against the objective still pinned above, and the verdict is what moves your progress. Skipping is allowed; it just doesn't count as demonstrated.",
      },
      route: {
        title: "Stepping back",
        body:
          "Learn is this one stop. Route is the whole journey — where you've been, and how it's going.",
        cue: "Switch to Route.",
      },
      map: {
        title: "The journey, whole",
        body:
          "Every stop and how they connect; click one to go and read it. The Analysis tab beside it is the evidence behind your progress — what you've demonstrated, what's still open, and everything the session has changed.",
      },
      back: {
        title: "And back again",
        body: "Learn brings you back to exactly the stop you left.",
        cue: "Switch to Learn.",
      },
      progress: {
        title: "Two numbers, two claims",
        body:
          "The first is objectives you've actually demonstrated. The second is stops you've dealt with. They're different things, and only the first one is about what you understand. The ⋯ menu holds the rest — make the route shorter or deeper, reread the briefing, or finish early.",
      },
    } as Record<string, { title: string; body: string; cue?: string; action?: string }>,

    /** The closing line, on the last step. */
    finished: "You can replay this from the ⋯ menu any time.",
  },

  // --- source pane ---
  source: {
    dock: "Dock to the side",
    float: "Float in a window",
    window: "Source",
    resize: "Drag to resize the source pane",
  },

  // --- route rail ---
  rail: {
    /** Tooltip suffix naming what is still unresolved on a stop. */
    unresolved: "unresolved",
    unresolvedCount: (count: number) =>
      count === 1 ? "◇ 1 unresolved" : `◇ ${count} unresolved`,
    unresolvedHint: "Named misconceptions still open here",
    setAside: "◦ set aside",
    setAsideHint: "You chose to stop being asked about this",
    title: "Your route",
    /**
     * The briefing, at the head of the route.
     *
     * A DESTINATION, NOT A STOP. Nothing is demonstrated there, it carries no
     * understanding state, and it sits before the walk rather than in it — so it is
     * drawn as a bordered box in sentence case, which is neither the rail's stop
     * (pin + connector) nor its chapter heading (tracked uppercase mono).
     *
     * The hint is the welcome page's own heading, verbatim, so the row and the page
     * it opens say the same thing.
     */
    briefing: "Briefing",
    briefingHint: "This repository, and you",
    close: "Close the route",
    openMap: "Open map",
    addedAfterConfusion: "added after confusion",
    optionalStops: (count: number) =>
      count === 1 ? "1 optional stop" : `${count} optional stops`,
    hideOptional: "Hide optional",
    // The rail carries no permanent legend any more: a pin's meaning is on the
    // pin, as its accessible name, and the map keeps the full key. The word
    // itself is the shared understanding vocabulary — never the model's raw
    // `partial` / `not_started`, and never the retired "marked weak".
    stopState: (state: string) => `— ${state}`,
    // Both live on the section heading row, which is two controls rather than
    // one: the chevron collapses, the title opens the chapter overview.
    collapseSection: (title: string) => `Collapse ${title}`,
    expandSection: (title: string) => `Expand ${title}`,
    openSection: (title: string) => `Open the overview of ${title}`,
    sectionProgress: (settled: number, total: number) => `${settled}/${total}`,
    youAreHere: "you are here",
  },

  // --- section (chapter) overview ---
  // A chapter introduction, not a lesson: it says what this stage of the route
  // is for and what the learner should be able to claim at the end of it. Every
  // line is derived from the curriculum the Planner already wrote — the area's
  // own `why`, and the objectives of the units inside it.
  section: {
    label: "Section overview",
    chapterOf: (index: number, total: number) => `Chapter ${index} of ${total}`,
    purpose: "What this section is about",
    whyNow: "Why now",
    opensRoute: "This is where your route begins, so nothing is assumed yet.",
    followsOn: (previous: string) =>
      `It follows on from “${previous}”, and builds on what you took from it.`,
    followsUnfinished: (previous: string, settled: number, total: number) =>
      `It follows on from “${previous}”, where ${settled} of ${total} stops are behind you.`,
    byTheEnd: "By the end you should be able to say",
    lessons: "Lessons in this section",
    progress: (settled: number, total: number) =>
      `${settled} of ${total} stops taken`,
    allTaken: "Every stop here is behind you.",
    continue: (title: string) => `Continue: ${title}`,
    startHere: (title: string) => `Start here: ${title}`,
    close: "Close overview",
    reopenHint: "Reopen this from the section heading in the route at any time.",
  },

  // --- scope control ---
  scope: {
    label: (count: number) => `${count} stops`,
    shorter: "Make it shorter",
    deeper: "Go deeper",
    working: "Adjusting…",
    // The stop count is NOT repeated here: the header beside it already shows
    // the live number, and the backend's own count treats a remedial warm-up as
    // a station where the rail treats it as a detour. One source of truth.
    shortened: (count: number) =>
      count === 1 ? "1 moved to optional" : `${count} moved to optional`,
    deepened: (count: number) =>
      count === 1 ? "1 added back" : `${count} added back`,
    nothingShorter: "Everything left is required",
    nothingDeeper: "Nothing further in this journey",
    failed: "Couldn't adjust the journey.",
  },

  // --- the session log (A1) ---
  //
  // One sentence per thing the system did, each naming the stop it was about where
  // the graph still knows it. The consequence line says these once, at the moment
  // they happen, inside the verdict card; this is the record for a learner who was
  // reading something else, or who came back tomorrow.
  log: {
    label: "What changed",
    empty: "Nothing has changed your route yet.",
    // The rail's mark. Cleared by looking at the rail, because looking is what
    // makes "you have not seen this" false.
    routeChanged: (count: number) =>
      count === 1 ? "1 change to your route" : `${count} changes to your route`,
    // ONE SIGNATURE for every kind, so the component can index by kind instead of
    // switching on it — a switch in a render body is a decision nobody can test.
    // Some ignore `subject`; that is cheaper than two shapes.
    kinds: {
      // The only one the system does unprompted, so it says why. The others were
      // asked for, and a learner does not need telling why they did something.
      prune_ahead: (count, subject) =>
        `${count === 1 ? "1 later stop" : `${count} later stops`} became optional` +
        (subject ? ` after you demonstrated ${subject}` : ""),
      scope_shorter: (count) =>
        count === 1
          ? "You made the journey shorter — 1 stop moved to optional"
          : `You made the journey shorter — ${count} stops moved to optional`,
      scope_deeper: (count) =>
        count === 1
          ? "You asked for more depth — 1 stop added back"
          : `You asked for more depth — ${count} stops added back`,
      remediation_inserted: (_count, subject) =>
        subject ? `A warm-up was added before ${subject}` : "A warm-up was added",
      // Gap lifecycle, rendered from the gaps themselves and never as journey
      // events: extending the frozen kind set from a screen would be a
      // learning-engine decision made in the wrong place.
      gap_opened: (_count, subject) =>
        subject ? `A misconception was named on ${subject}` : "A misconception was named",
      gap_closed: (_count, subject) =>
        subject ? `You cleared a misconception on ${subject}` : "You cleared a misconception",
      // Phrased as the learner's own act, because it was one. The log is a record
      // of what happened to this journey, and "you moved" belongs in it beside
      // "the system moved something" — the omission was what made jumping the one
      // navigation act with no trace.
      jumped: (_count, subject) =>
        subject ? `You jumped to ${subject}` : "You jumped to another stop",
    } as Record<string, (count: number, subject: string | null) => string>,
  },

  // --- lesson panel ---
  lesson: {
    writing: "Writing this lesson…",
    warmUpHeading: "Warm-up · added after confusion",
    // --- the arrival notice, on a stop the learner jumped to ---
    //
    // WORDING RULE: it reports MOVEMENT and never judges it. Jumping is allowed —
    // no stop is locked and dependencies are not enforced — so nothing here may
    // read as a reprimand or as a warning that something will go wrong. What it
    // exists to fix is that departing from the route used to be silent, so the
    // rail's order looked decorative.
    //
    // Composed from a place phrase rather than written out per case: three
    // movements (ahead / back / unknown) times two places (a numbered station and
    // a stop the rail does not number) is six sentences to keep in step, and they
    // drifted the moment one of them was edited.
    arrival: {
      label: "Off the route",
      place: (position: number, total: number) => `stop ${position} of ${total}`,
      // A warm-up or an `optional` unit. The rail counts neither, so quoting a
      // number would promise a position it does not show.
      placeAside: "a stop off the default walk",
      ahead: (place: string, passed: number) =>
        passed === 0
          ? `You jumped ahead to ${place}.`
          : `You jumped ahead to ${place}, passing ${passed === 1 ? "1 stop" : `${passed} stops`}.`,
      // "Already taken" is a claim about evidence, so it is said only where the
      // stop was actually visited — jumping back to something never reached is
      // perfectly possible.
      back: (place: string, revisited: boolean) =>
        revisited
          ? `You came back to ${place} — already taken.`
          : `You went back to ${place}.`,
      // Said when the stop they left is no longer in the graph. Reports where they
      // are and stops there, rather than guessing which way they came.
      here: (place: string) => `You jumped to ${place}.`,
      returnTo: (title: string) => `Return to “${title}”`,
      returning: "Going back…",
      dismiss: "Stay here",
    },
    stopOf: (position: number, total: number) => `Stop ${position} of ${total}`,
    lines: (start: number, end: number) => `lines ${start}–${end}`,
    recoveredLabel: "The warm-up worked",
    recoveredBody: "You got this one after studying",
    recoveredBodyEnd:
      "first. It stays marked as a rough patch, but you came back from it.",
    // "Try again" re-showed the question the learner had just been given the
    // answer to. The replacement asks a NEW question about the same
    // misconception, so the label has to promise a check rather than a retry.
    verifyCta: "Check my understanding",
    verifyCtaBusy: "Writing a question…",
    verificationHeading: "A different angle on the same idea",
    verificationHelp:
      "Answering this is the only thing that clears the gap — moving on leaves it open.",
    // The result of a check. A verification carries NO classification — it is
    // evidence about specific beliefs, not a re-grade of the objective — so the
    // headline has to come from what actually closed. Three outcomes, and the
    // wording never claims the objective was reassessed.
    checkCleared: "Cleared",
    checkPartly: "Partly cleared",
    checkOpen: "Still open",
    checkClosedLabel: "What this closed",
    // Said when a check closes everything and the stop STILL is not credited.
    //
    // Observed in S0's J4: the learner failed a stop, verified the gap that caused
    // it, saw "Cleared" and watched the unresolved counter disappear — and goal
    // readiness did not move, because a verification is evidence about a belief and
    // the stop's credit is judged on the answer to its question (M7,
    // `verification.py`). Nothing on screen said so, which made the gauge look
    // broken rather than strict.
    //
    // States the fact and its reason, and promises no route: re-answering the same
    // question after the explanation has been shown is the memory test §18.7
    // removed, and a fresh question about the OBJECTIVE is a mechanism the system
    // does not yet have.
    checkClearedNotCredited:
      "That's closed. This stop still isn't counted as demonstrated — that's judged on your answer to its own question, not on the check.",
    checkNothingClosed:
      "That did not settle it. You can try a different angle, or carry on and come back.",
    checkAnother: "Check another",
    // The outstanding-gaps list: the most honest surface in the product. Named,
    // never counted, because "what you still do not know" is only useful specific.
    // The brief's counters. Named by what they are, not by a bare number: "2" in
    // a pinned header says nothing, and the point of the counter is to say that
    // something is still open without listing it again.
    // The key point — the one condensation in the flow (§2). Three levels, best
    // available first: the Grader's own headline if B1 ever ships it, otherwise the
    // verdict word plus the leading gap's claim, otherwise the verdict word alone.
    //
    // Framed as an assumption the learner is CARRYING, not as a correction we
    // computed: the gap claim is a statement of the misconception, and dressing it
    // up as "actually, X" would assert a correction nothing produced.
    keyPoint: (verdict: string, claim: string) => `${verdict} — you're working from: ${claim}`,
    // The same ladder, for an answer that REACHED the objective while something
    // detected earlier is still unverified. The "you're working from" frame is
    // false here: it told a learner who had just correctly refuted a
    // misconception that they were carrying it. What is true is that the answer
    // landed and the earlier belief has not been checked — which is also the
    // one action worth offering, so the sentence and the button agree.
    keyPointUnverified: (verdict: string, count: number) =>
      count === 1
        ? `${verdict} — one thing you said earlier still needs checking`
        : `${verdict} — ${count} things you said earlier still need checking`,
    // One consequence line, replacing three separate notices that all described the
    // same event (§3a question 2). Ordered by how much it changed the journey.
    consequenceRetaught: "This stop has been rewritten to answer that.",
    consequencePruned: (count: number) =>
      count === 1 ? "One later stop is no longer needed." : `${count} later stops are no longer needed.`,
    consequenceWarmUpAdded: "A warm-up has been added before this stop.",
    consequenceWarmUpExists: "There is already a warm-up before this stop.",
    consequenceWarmUpUnavailable: "No warm-up could be built for this.",
    briefGaps: (count: number) => (count === 1 ? "1 unresolved" : `${count} unresolved`),
    briefAttempts: (count: number) =>
      count === 1 ? "1 answer" : `${count} answers`,
    gapsHeading: "What you got wrong here",
    gapsHelp:
      "Each one stays on the record. Clear it by answering a fresh question about it — it then reads as resolved rather than disappearing.",
    /** The ledger's own tally: resolved over total, never a bare count of debt. */
    gapsTally: (resolved: number, total: number) =>
      `${resolved} of ${total} resolved`,
    /** Per-gap actions and status. */
    gapSolve: "Clear this",
    gapSolveBusy: "Writing a question…",
    gapStatusOpen: "Unresolved",
    gapStatusVerified: "Resolved",
    gapStatusWaived: "Set aside",
    gapSettledHeading: "Settled",
    /** Shown on a resolved gap: what closed it, and that only an answer could. */
    gapResolvedNote: "You answered a check on this correctly.",
    gapWaivedNote: "You chose to stop being asked. It can still be cleared.",
    /** The system stopped offering; the learner can still ask. */
    gapAskedTwice: "Asked twice already — you can still try again.",
    gapBlocking: "Holding this stop back",
    gapNonBlocking: "Worth knowing",
    gapWaived: "You set this aside",
    gapVerified: "Checked and cleared",
    gapExhausted: "No more checks offered here",
    waiveOne: "Set aside",
    notNow: "Not now",
    waiveAll: "Set all aside",
    gapResolved: "Cleared",
    gapStillOpen: "Still open",
    // The M7 case the drawer could not previously explain.
    pendingVerification:
      "Your last answer reached the objective — this stop counts as demonstrated once the check below is cleared.",
    walkthrough: "Walkthrough",
    setup: "Before you answer",
    // The question, once a verdict has superseded it — a label for re-reading, not
    // for answering. Understanding in FEEDBACK showed a verdict and no sign of what
    // had been asked, which made "shown about what?" unanswerable on the one
    // surface built to answer it.
    questionAsked: "The question you answered",
    // R3's third mitigation. Counted, because the number is the whole point: it
    // says how many times this stop has been rewritten for you, which is a fact
    // about your own history with it.
    earlierExplanations: (count: number) =>
      count === 1 ? "Earlier explanation (1)" : `Earlier explanations (${count})`,
    earlierVersion: (n: number) => `Version ${n}`,
    earlierBecause: "Replaced after you answered:",
    // Shown on Lesson when the material changed because of the last answer. The
    // consequence line says it on the Understanding side at the moment it happens;
    // this is what makes the claim good for a learner who arrives later, and it is
    // why it reads from the attempt history rather than from the live result.
    newMaterialLabel: "Rewritten",
    newMaterialBody: "This stop was rewritten after your last answer.",
    // The control on the consequence line. Deliberately not "Go to Lesson": it
    // names what the learner would DO there, and the tab it lands on is visible.
    readIt: "Read it",
    hint: "A way in",
    followup: "One more, from another angle",
    retaught: "Rewritten around what you said",
    tryAgain: "Try again",
    pruned: (count: number) =>
      count === 1
        ? "You're ahead — 1 stop moved to optional"
        : `You're ahead — ${count} stops moved to optional`,
    reveal: "What's actually happening",
    takeaway: "Take away",
    ownership: "Yours to hold",
    tracePath: "This path crosses several places",
    /** Same list, one place. "…crosses several places" would be a lie at n=1. */
    codeLocation: "Where this lives in the code",
    anchorStep: (index: number, total: number) => `Step ${index} of ${total}`,
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
    // Two measures, and neither gates the other (§18.16.3). "Journey complete"
    // beside "92% verified" is the intended final state, not a contradiction.
    journeyComplete: "Journey complete",
    journeyIncomplete: (open: number) =>
      open === 1 ? "1 stop still open" : `${open} stops still open`,
    verifiedUnderstanding: "Verified understanding",
    waivedHeading: "What you chose not to check",
    waivedHelp: "These stay on the record. You can check any of them now.",
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
    // `label` now heads the Analysis tab; the map keeps `routeLabel`. The split
    // is why they differ: one names evidence, the other names a place.
    label: "What you understand so far",
    routeLabel: "The route through this repository",
    thisCodebase: "This codebase",
    conceptsUnderstood: (understood: number, total: number) =>
      `${understood} of ${total} concepts understood`,
    filesTouched: (count: number) =>
      `${count} file${count === 1 ? "" : "s"} touched`,
    readiness: "goal readiness",
    // The headline is a claim about the GOAL, so it is stated over the required
    // set rather than over every node on screen.
    coreDemonstrated: (understood: number, total: number) =>
      `${understood} of ${total} required objectives demonstrated`,
    stopsTaken: (settled: number, total: number) =>
      `${settled} of ${total} stops taken`,
    // Remedial work is reported rather than folded into a percentage (OQ-2).
    detoursTaken: (count: number) =>
      `${count} warm-up${count === 1 ? "" : "s"} taken`,
    skippedStops: (count: number) => `${count} skipped`,
    // --- understanding profile (M3a.1) ---
    // Wording rule: every label describes ANSWERS and UNITS, never the learner.
    // "3 objectives need work" is a fact; "you are weak at flows" is a claim
    // about a person that this evidence cannot support.
    understanding: {
      strength: "Demonstrated",
      recovered: "Worked through",
      unresolved: "Needs work",
      insufficient: "Not yet assessed",
    } as Record<string, string>,
    // The learner's own decision about remediation — a second dimension, never
    // a replacement for what the evidence shows.
    disposition: {
      continued: "you chose to move on",
      waived: "you chose not to pursue this",
      skipped: "skipped",
      asserted: "you marked this understood",
    } as Record<string, string>,
    // --- patterns (M3a.2) ---
    //
    // WORDING RULE, and the reason the backend returns numbers rather than
    // prose: a pattern describes ANSWERS, never the learner. "Flow objectives
    // needed a second answer more often" is a count. "You struggle with flows"
    // is a claim about a person that this evidence cannot carry, and belongs to
    // an L3 layer that does not exist.
    //
    // The area sentence in particular reports the aggregate and stops there. It
    // must not say "you still need to work on this": a waived objective counts
    // as not demonstrated — that is the truth about evidence — but the learner
    // has already declined to pursue it, and the pattern layer does not overrule
    // that decision.
    patterns: "What the evidence shows",
    patternsEmpty: "Not enough evidence to identify a pattern yet.",
    evidenceRef: (index: number, total: number) =>
      `Open the evidence for answer ${index} of ${total} behind this observation`,
    patternEvidence: (count: number) =>
      `${count} answer${count === 1 ? "" : "s"} behind this`,
    pattern: {
      kind_contrast: (
        lead: string, leadExtra: number, leadTotal: number,
        base: string, baseExtra: number, baseTotal: number
      ) =>
        `${lead} objectives needed more than one answer more often than ${base} ` +
        `objectives (${leadExtra} of ${leadTotal} vs ${baseExtra} of ${baseTotal}).`,
      recurring_shortfall: (attempts: number, nodes: number, kind: string) =>
        `${attempts} answers across ${nodes} objectives fell short the same ` +
        `way: ${kind}.`,
      // Deliberately an aggregate, not an instruction.
      area_evidence: (demonstrated: number, assessed: number, area: string) =>
        `${demonstrated} of ${assessed} assessed objectives demonstrated in ${area}.`,
      // ── M3b: gap-derived. These describe what happened to named
      // misconceptions, never what the learner is like. "waived" is always
      // reported separately from "verified" — a decision to stop is not
      // evidence of mastery, and merging them would let one read as the other.
      gap_outcomes: (total: number, verified: number, waived: number, open: number) =>
        `${total} specific misconceptions came up: ${verified} checked and ` +
        `cleared, ${waived} you chose not to pursue, ${open} still open.`,
      blocking_backlog: (gaps: number, nodes: number) =>
        `${gaps} misconceptions across ${nodes} objectives are still holding ` +
        `those objectives back.`,
      blockingExhausted: (count: number) =>
        count === 1
          ? "One of these has run out of check attempts, so it is no longer offered."
          : `${count} of these have run out of check attempts, so they are no longer offered.`,
      verification_outcomes: (tested: number, closed: number) =>
        `Of ${tested} misconceptions you were re-checked on, ${closed} cleared.`,
      verificationRetried: (count: number) =>
        count === 1
          ? "One needed more than one check."
          : `${count} needed more than one check.`,
      remediation_closure: (warmups: number, closed: number) =>
        `${closed} of ${warmups} warm-ups closed the misconception they were built for.`,
      // Appended only when some of them were set aside, so the sentence above
      // is not read as outstanding work.
      setAsideNote: (count: number) =>
        count === 1
          ? "One of these you chose not to pursue."
          : `${count} of these you chose not to pursue.`,
    },
    // The Grader's shortfall vocabulary, in words a learner can read.
    shortfall: {
      missing_prerequisite: "a missing foundation",
      wrong_model: "a confident but incorrect model",
      right_idea_wrong_altitude: "the right idea at the wrong level",
    } as Record<string, string>,
    profileTitle: "What you understand",
    // The journey IS the understanding view now, so it gets the plain name.
    journeyTitle: "Your journey",
    demonstratedLabel: "Demonstrated",
    journeyLabel: (settled: number, total: number) =>
      `Journey · ${settled} of ${total} stops`,
    inProgress: (count: number) => `${count} in progress`,
    moreBreakdowns: "More detail",
    needsWork: "Needs work",
    workedThrough: "Worked through",
    workedThroughHint: "Fell short at first, then demonstrated.",
    setAside: "Set aside",
    setAsideHint: "Still unresolved, but you chose not to pursue it.",
    notAssessed: (count: number) => `${count} not yet assessed`,
    assessedOf: (assessed: number, total: number) =>
      `${assessed} of ${total} units have evidence`,
    ofAssessed: (n: number, total: number) => `${n} of ${total}`,
    noEvidenceYet: "No answers recorded yet — nothing to show about your understanding.",
    // Shown when gap-model M7 holds a unit back although the last answer
    // reached the objective. Says THAT, never invents a why.
    gapsLabel: "What is unresolved",
    gapBlocking: "Holding this back",
    gapNonBlocking: "Worth knowing",
    gapWaived: "Set aside by you",
    gapVerified: "Checked and cleared",
    gapExhausted: "No more checks offered",
    // One sentence explaining an `unresolved` state. Each names a different
    // cause: a check not yet taken, a decision the learner made, misconceptions
    // still open, or simply an answer that fell short.
    whyPendingVerification:
      "Not counted as demonstrated yet — there is a check waiting to be taken.",
    whyWaived: (count: number) =>
      count === 1
        ? "One point here you chose not to pursue, so this stays undemonstrated."
        : `${count} points here you chose not to pursue, so this stays undemonstrated.`,
    whyOpenGaps: (count: number) =>
      count === 1
        ? "One misconception is still open here."
        : `${count} misconceptions are still open here.`,
    whyNotYetDemonstrated:
      "Your last answer did not yet reach the objective.",
    pendingVerification: "Not yet counted as demonstrated — verification pending.",
    // --- evidence drawer ---
    evidence: "Evidence",
    evidenceFor: "Why this state",
    close: "Close",
    objectiveLabel: "The claim you were marked against",
    timeline: "What happened",
    yourAnswer: "Your answer",
    systemDid: "The system",
    noRecord: "no record of what the system did",
    notEvidence: "not counted as evidence",
    gradingFailed: "grading failed — not counted",
    supersededLesson: "Replaced an earlier version of this lesson",
    interventionLabel: {
      none: "recorded — nothing was owed",
      hint: "gave a hint",
      reteach: "re-taught this unit",
      followup: "asked a follow-up",
      prerequisite: "added a warm-up",
    } as Record<string, string>,
    byKind: "By kind of understanding",
    topicsTouched: "Topics touched",
    whereInRepo: "Where in the repository",
    theRoute: "The route",
    unlocks: (title: string) => `· unlocks “${title}”`,

    // --- the stop card (the map's summary of one stop) ---
    //
    // Clicking a stop used to jump into its lesson immediately. That made the map
    // a set of links rather than a map: the one surface whose whole job is
    // deciding where to go was the only one that would not tell you anything
    // about a place before taking you there. The card answers "what is this one?"
    // and then offers the jump as a separate, deliberate act.
    //
    // Every line of it is ALREADY IN THE GRAPH — the objective the Planner wrote,
    // the anchors, the tags, the evidence state. Nothing here is generated, and
    // nothing is a claim the rest of the app does not already make.
    stop: {
      label: "Stop",
      // The eyebrow, when the stop consumes no number: a warm-up, or depth the
      // learner did not ask for. Both are reachable, neither is on the walk.
      offRoute: "Off the default walk",
      objective: "What this stop is for",
      // Said rather than left blank: a pre-B3 graph has no `objective`, and an
      // empty space would read as "nothing to learn here".
      noObjective: "No objective was recorded for this stop.",
      where: "Where in the code",
      concepts: "Concepts",
      // The card states evidence; it never asks for any. Both counters are read
      // out as facts, because the map is not where an answer is given.
      untouched: "No answers recorded here yet",
      optional: "Optional — off the default walk, still reachable",
      // Two labels for one button, because the act differs. From anywhere else
      // this moves the session pointer; on the stop you are already standing on
      // it just puts the lesson back in front of you.
      goToLesson: "Go to lesson",
      returnToLesson: "Back to this lesson",
      close: "Close",
    },
    understoodOfTotal: (understood: number, total: number) =>
      `${understood} of ${total} understood`,
  },

  // --- shared vocabularies ---
  // Keys match the concept-tag and understanding-state values the backend
  // emits; only the label is chosen here.
  tags: {
    architecture: "architecture",
    flow: "flow",
    extension_point: "extension point",
    risk: "risk",
    test_coverage: "test coverage",
    component: "component",
    synthesis: "synthesis",
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
    at_first_question: "This is the first question — there's nothing behind it.",
    invalid_goal_type_option: "Pick one of the listed options.",
    invalid_code_depth_option: "Pick one of the listed options.",
    // The three ways a check can be refused. All were reachable before and
    // rendered as raw slugs; `nothing_to_verify` became easier to reach once the
    // node's remediation cap could actually fire (F100), so naming them is part
    // of offering the check rather than an aside.
    //
    // "Stopped proposing" is the honest wording: the gap is still open and still
    // counted. The system has run out of ways to ask about it, which is not the
    // same as the gap having gone away (§18.16.1).
    nothing_to_verify:
      "There's nothing left to check here — the system has stopped proposing " +
      "questions for what's still open.",
    source_unavailable:
      "The source for this stop couldn't be read, so no question could be built from it.",
    verification_unavailable: "Couldn't write a question for this one. Try again in a moment.",
    no_pending_verification: "That question is no longer open.",
    server_unreachable:
      "Couldn't reach the server. Check the backend is running on port 8000, " +
      "and that this page is open on the same host it allows (localhost).",
  } as Record<string, string>,
};

/**
 * Backend failures arrive as `detail` slugs (`session_not_found`) mixed with
 * real prose (a pipeline error list). Replace the ones we recognise and pass
 * anything else through — a raw stack trace is more useful than a generic
 * "something went wrong".
 */
export function errorText(message: string): string {
  return t.errors[message.trim()] ?? message;
}
