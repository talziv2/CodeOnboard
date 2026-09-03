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
  // ── authentication (multi-user M2) ──────────────────────────────────────
  //
  // The two failure messages are deliberately incurious. "Email or password is
  // incorrect" and "that email cannot be used" say nothing about whether an
  // account exists, because "is this person a user here" is not a question an
  // anonymous visitor gets to ask. The backend returns exactly these; they are
  // repeated here as the fallback when it cannot be reached.
  // ── the dashboard (multi-user M5) ───────────────────────────────────────
  //
  // The empty state INVITES rather than apologises: a learner with no sessions
  // has not lost anything, they simply have not started one yet.
  dashboard: {
    title: "My Learning Sessions",
    // The name, not the address. `display_name` when the learner gave one,
    // otherwise the local part of the email — nobody wants to be greeted by
    // their own inbox.
    welcome: (name: string) => `Welcome back, ${name}`,
    // The greeting with nothing to greet. An account created without a display
    // name and with an unreadable address still gets a sentence, not a blank.
    welcomeAnonymous: "Welcome back",
    // The card's mono label for the learner's own words. The title above it is
    // the focus area; this is the sentence they wrote about why.
    goalLabel: "Goal",
    // Pressing the card SELECTS it — it grows and shows the rest of what it
    // knows. Opening the session is `Continue`, and only `Continue`, because a
    // card that navigates on any click cannot be read without leaving.
    expand: (title: string) => `More about ${title}`,
    collapse: (title: string) => `Less about ${title}`,
    // `Continue` reads fine beside its own card and says nothing on its own in
    // a list of four, so the accessible name carries which session it opens.
    openSession: (title: string) => `Continue: ${title}`,
    loading: "Loading your sessions…",
    loadFailed: "Couldn't load your sessions. Try again.",
    empty: "No sessions yet. Point CodeOnboard at a repository and it will build you a route through it.",
    noneArchived: "Nothing archived.",
    startNew: "Start a new session",
    backToDashboard: "Back to my sessions",
    // The same act, at header width. `backToDashboard` is the spoken name and
    // the tooltip; this is what fits beside a repository path and a goal without
    // taking the room the goal needs. Both say "sessions" rather than "home" or
    // "dashboard" — the destination is the learner's OWN list, and the one thing
    // the words have to rule out is that this ends or restarts anything.
    mySessions: "My sessions",
    continue: "Continue",
    // Planning runs in the background, so the card exists from the first second
    // and says what it is doing. Closing the tab no longer loses the session.
    generating: "Building your route…",
    // A plan that never arrived. Named rather than left spinning: a learner who
    // cannot tell whether to wait or retry is worse off than one who is told.
    failed: "Couldn't build this route",
    rename: "Rename",
    renameLabel: "Session name",
    save: "Save",
    cancel: "Cancel",
    archive: "Archive",
    unarchive: "Unarchive",
    archived: "archived",
    showArchived: "Show archived",
    hideArchived: "Hide archived",
    delete: "Delete",
    // Named as irreversible, because it is. Archiving keeps everything and is
    // offered first; this is for someone who means it.
    deleteConfirm: "Delete permanently?",
    deleteYes: "Delete",
    ready: (percent: number) => `${percent}% ready`,
    stops: (settled: number, total: number) => `${settled} of ${total} stops`,
  },

  auth: {
    emailLabel: "Email",
    passwordLabel: "Password",
    nameLabel: "Name (optional)",
    passwordHint: "At least 10 characters. Length beats punctuation.",
    login: {
      title: "Sign in",
      subtitle: "Sign in to pick up where you left off.",
      submit: "Sign in",
      busy: "Signing in…",
      failed: "Could not sign in. Try again.",
      switchPrompt: "No account yet?",
      switchAction: "Create one",
    },
    signup: {
      title: "Create an account",
      subtitle: "Create an account to keep your learning sessions.",
      submit: "Create account",
      busy: "Creating…",
      failed: "Could not create the account. Try again.",
      switchPrompt: "Already have an account?",
      switchAction: "Sign in",
    },
    // Sits under the sign-in form. Named as the question the learner is asking,
    // not as the mechanism ("Reset password"), because at that moment they do
    // not yet know a reset is what they need.
    forgotLink: "Forgot password?",
    forgot: {
      title: "Reset your password",
      subtitle: "Enter your email and we'll make you a reset link.",
      submit: "Get a reset link",
      busy: "Preparing…",
      failed: "Could not start a reset. Try again.",
      // Shown for EVERY address, including one with no account — the server
      // answers identically either way and this copy must not undo that.
      sent: "If that email has an account with a password, a reset link is ready.",
      // Development only. The banner says so, because a link handed straight to
      // whoever asked for it is not how this would work anywhere real.
      devNotice: "Development build: no email is sent, so the link is shown here.",
      devOpen: "Open the reset link",
      back: "Back to sign in",
    },
    reset: {
      title: "Choose a new password",
      subtitle: "Pick a new password for your account.",
      newPasswordLabel: "New password",
      submit: "Set password and sign in",
      busy: "Saving…",
      failed: "Could not set the password. Try again.",
      // The link is single-use and short-lived, so the two ways to arrive here
      // without a usable one get the same instruction: start again.
      missingToken: "That reset link is incomplete. Start again from the sign-in page.",
      restart: "Start again",
      // Says the consequence BEFORE the click, because it is one a learner on
      // another device would otherwise discover by being logged out.
      revokeNotice: "Setting a new password signs you out everywhere else.",
    },
    signOut: "Sign out",
    google: "Continue with Google",
    // The link step exists because the app verifies no email of its own, so
    // Google proving the address is not the same as proving the account.
    linkTitle: "Connect Google to your account",
    linkBody:
      "An account already uses this email. Enter its password to connect Google to it — you'll be signed out of any other devices.",
    linkSubmit: "Connect and sign in",
    linkBusy: "Connecting…",
    checking: "Checking your session…",
  },

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
    /** The Tutor's control, beside `showSource` and of the same prominence. */
    showChat: "Chat",
    hideChat: "Close the tutor",
    // ── two different actions, and they used to be one ──────────────────────
    //
    // `Start over` re-ran the whole pipeline: two to four minutes, and a
    // DIFFERENT route than the one on screen. That is a rebuild, not a restart,
    // so they are now separate controls with separate confirmations.
    //
    // The copy carries the whole distinction, because the two sit one click apart
    // and the difference between them is minutes and money. This one names what
    // is KEPT, since "will I lose the route?" is the actual question.
    startOver: "Start over",
    startingOver: "Starting over…",
    startOverConfirm:
      "Walk this same route again from the first stop? The stops, their order and their lessons stay exactly as they are. Your progress, answers, feedback, gaps and any warm-ups added along the way are cleared.",
    startOverYes: "Start over",
    startOverNo: "Keep my progress",
    // Shown when the reset itself failed. It leads with what did NOT happen,
    // because the learner's first question is whether their work is gone — and it
    // is not: a failed reset changes nothing on the server.
    startOverFailed: "Couldn't start over, and nothing has changed — your progress is exactly where it was.",
    dismiss: "Dismiss",
    // The old `Start over`, named for what it does. The wording has to earn the
    // wait rather than spring it on someone.
    rebuild: "Rebuild learning path",
    rebuilding: "Rebuilding…",
    rebuildConfirm:
      "Plan a brand-new route for the same repository and the same answers? This reads the repository again, takes two to four minutes, and the new route will not be the same as this one. Your current session is kept until the new one is ready.",
    rebuildYes: "Rebuild it",
    rebuildNo: "Never mind",
    // ── the rebuild's own wait ──────────────────────────────────────────────
    //
    // A rebuild re-runs the entire pipeline, which is the same two-to-four
    // minutes the landing page warns about. It used to say so nowhere: the menu
    // item greyed out and the session sat there, which is indistinguishable from
    // a click that did nothing.
    rebuildWaitLabel: "Rebuilding your route",
    // Says what survives, because that is the question someone watching a
    // three-minute wait actually has.
    rebuildWaitNote:
      "Same repository, same answers — the route is planned again from scratch. Your current session stays exactly as it is until the new one is ready.",
    rebuildWaitFailed: "Couldn't build the new route.",
    rebuildWaitReassurance:
      "Nothing happened to the session you were in — it is still here, and still where you left it.",
    rebuildWaitRetry: "Try again",
    // Withdraws the WAIT, not the run: the backend finishes either way, and
    // saying "cancel" would promise a stop we cannot deliver.
    rebuildWaitCancel: "Keep the session I have",
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
          "Every lesson points at actual lines in the repository, never at an invented example. They sit behind this row so they are not a third copy of the same thing.",
        cue: "Open it, then click a line.",
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
        // Says what the DRAWING means, because the drawing is now carrying real
        // claims: the line's colour is progress, a marker is evidence, and a stop
        // set off to the side is the journey having changed around an answer. A
        // learner who is not told that reads three signals as decoration.
        body:
          "Every stop and how they connect; click one to go and read it. The line runs cyan as far as where you are, each marker says how that stop went, and a stop set off to the side is one the journey added for you after an answer fell short.",
      },
      legend: {
        title: "The key, when you need it",
        body:
          "Every marker and every kind of line, spelled out — branches included, since those are the part that changes as you go. It opens from here whenever you want a reminder. The Analysis tab beside the map is the evidence behind all of it.",
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

  // --- the Tutor (docs/planning/phases/tutor.md) ---
  //
  // The copy here carries two things the architecture cannot: that the assessment
  // Tutor genuinely does not hold the answer (§7.3 makes that literally true, and
  // saying so is only honest because it is), and that revealing costs the current
  // question (§6.3 — stated BEFORE the click, on the control itself).
  tutor: {
    window: "Tutor",
    title: "Tutor",
    /** The composer, in each mode. Never "Submit" — that word belongs to answers. */
    ask: "Ask",
    asking: "Thinking…",
    placeholderExplain: "Ask about this code",
    placeholderScaffold: "What's confusing you?",
    /** Advertised beside the button, like the answer composer's own shortcut. */
    askHint: "⌘↵ to ask",

    /** The mode strip. Two modes that must never be confusable at a glance. */
    modeExplain: "Explaining",
    modeScaffold: "Helping you answer",
    /**
     * Printed because it is architecturally TRUE, not as a promise: the scaffold
     * context has no field that could hold the reveal or the expected answer.
     */
    scaffoldBlurb: "I can see this stop's code and your question. I can't see the answer.",
    explainBlurb: "I can see this repository, your route, and how you've done here.",
    outOfScopeTag: "Outside what I can see",

    /** The ladder. */
    hintLevel: (used: number, max: number) => `Hint ${used} of ${max}`,
    /** On the turn itself. No denominator — the ladder states the cap. */
    hintTurn: (level: number) => `Hint ${level}`,
    askForHint: "Give me a hint",
    askForAnotherHint: "Another hint",
    hintsSpent: "That's every hint I have for this one.",

    /**
     * §6.3, and the most carefully worded string in the product. The learner is
     * choosing to leave assessment and return to learning; the trade is named in
     * full before the control, and again inside the control's own label.
     */
    revealWarning:
      "You can see the explanation now, but this question stops counting as your assessment. You'll get a new question on the same concept.",
    revealAction: "Show answer & get a new question",
    revealCancel: "Keep trying",
    revealHeading: "The explanation",
    revealedNotice:
      "You've seen the explanation, so this question is done. Ask me again when you want a fresh one.",

    /** Offers. `label_key` on a suggestion names one of these. */
    offer: {
      checkGap: "Check that misconception",
      askAgain: "Try a fresh question",
      goToStop: "Go to that stop",
      goDeeper: "Add the optional material",
    } as Record<string, string>,
    offerDwelling: "You've been on this one a while.",
    offerReturning: "You'd marked this done.",

    /** The transcript. */
    empty: "Ask me anything about this stop, this repository, or how you're doing.",
    emptyScaffold: "Stuck? Ask me what's confusing you, or take a hint.",
    earlier: (count: number) =>
      count === 1 ? "1 question earlier in this session" : `${count} questions earlier in this session`,
    earlierStop: "Asked at a stop that's no longer on your route",
    you: "You",
    /** Attribution, so canonical and personalized material are never confused. */
    tutorSaid: "Tutor",
    pin: "Keep this with the lesson",
    unpin: "Remove from the lesson",
    pinned: "Kept",
    remaining: (left: number) => `${left} left`,
    capReached: "You've used all your tutor questions for this session.",
    failed: "That didn't go through. Nothing was used up — try again.",

    /** The entry point beside the composer. Names the intent, not the tool. */
    stuck: "I'm stuck",
    /** Pinned notes, on the Lesson surface. */
    notesHeading: (count: number) =>
      count === 1 ? "Your note (1)" : `Your notes (${count})`,
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
    /**
     * Answered, and the answer said nothing either way.
     *
     * Deliberately not "needs work" and not "failed". An off-topic answer is
     * evidence of neither understanding nor misunderstanding, so the caption
     * reports what happened — they tried — and makes no claim about what they
     * know. The alternative is what shipped before M0: a stop the learner
     * answered reading exactly like one they had never opened.
     */
    attempted: "◦ attempted",
    attemptedHint: "You answered here, but the answer didn't show either way",
    /**
     * Reached, never answered, walked past.
     *
     * Deliberately not "skipped in error" and not "set aside": nothing here
     * claims the learner got anything wrong, because nothing was ever assessed.
     * It reports the movement and stops, which is the same rule the arrival
     * notice's copy follows.
     */
    passedBy: "◦ moved past",
    passedByHint: "You moved on from here without answering",
    /** Why a stop is settled without being demonstrated. */
    movedOnHint: "You chose to move on without demonstrating this",
    assertedHint: "You marked this as already known — not demonstrated",
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
    /**
     * Why the ledger opened itself, said once, at the top of it.
     *
     * Counted rather than named, because the claims are directly underneath: a
     * sentence that repeated them would be the same information twice in the
     * same box, which is the crowding the disclosure discipline exists to stop.
     */
    gapsOpenedNow: (count: number) =>
      count === 1
        ? "Your answer added one to this list."
        : `Your answer added ${count} to this list.`,
    gapsResolvedNow: (count: number) =>
      count === 1
        ? "Your answer cleared one from this list."
        : `Your answer cleared ${count} from this list.`,
    gapsHelp:
      "Each one stays on the record. Resolve it by answering a fresh question about it — it then reads as resolved rather than disappearing.",
    /** The ledger's own tally: resolved over total, never a bare count of debt. */
    gapsTally: (resolved: number, total: number) =>
      `${resolved} of ${total} resolved`,
    /**
     * THE TWO VERBS, and the wording is the whole point of the pair.
     *
     * They were `Clear this` and `Set aside`, which read as two ways of getting
     * rid of the same row — so the one that ASKS FOR A QUESTION looked like a
     * second way to dismiss. They do opposite things: one is the only act that
     * can ever produce `verified`, the other records that the learner is
     * deliberately not doing it. The labels now say which is which before the
     * learner has to find out by pressing one.
     *
     * `Ignore for now` is also the honest end of the semantics: waiving is
     * reversible, is never evidence, and keeps the stop short of `understood` —
     * so "ignored" and "resolved" are different states and the copy must not let
     * them blur (see `gapWaivedNote` and `gapStatusWaived`).
     */
    gapSolve: "Check me on this",
    gapSolveBusy: "Writing a question…",
    gapStatusOpen: "Unresolved",
    gapStatusVerified: "Resolved",
    gapStatusWaived: "Ignored for now",
    gapSettledHeading: "Settled",
    /** Shown on a resolved gap: what closed it, and that only an answer could. */
    gapResolvedNote: "You answered a check on this correctly.",
    /** NOT resolved, and the sentence has to keep saying so. */
    gapWaivedNote:
      "Still unresolved — you chose not to work on it now. Ask to be checked whenever you want.",
    /** The system stopped offering; the learner can still ask. */
    gapAskedTwice: "Asked twice already — you can still ask to be checked.",
    gapBlocking: "Holding this stop back",
    gapNonBlocking: "Worth knowing",
    gapWaived: "You chose to ignore this for now",
    gapVerified: "Checked and cleared",
    gapExhausted: "No more checks offered here",
    waiveOne: "Ignore for now",
    notNow: "Not now",
    waiveAll: "Ignore all for now",
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
    /** The misconceptions the rewrite was written to correct. */
    rewriteAnswers: "This version answers",
    compareEarlier: "The version you read before is under “Earlier explanations”.",
    /** The primary action while rewritten material is unread. */
    readWhatChanged: "Read what changed",
    /**
     * The primary action once an answer has unlocked the withheld explanation.
     *
     * Names the THING, not the tab. "Go to Lesson" would describe our layout;
     * this describes what is waiting there, which is the half a dot cannot say.
     */
    readNewExplanation: "Read the new explanation",
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
    /**
     * The question an answer was answering.
     *
     * Shown above the answer, never beside the node's CURRENT prompt: after a
     * re-teach those are different questions, and the whole point of recording
     * this is that an old answer must not be captioned with a question it never
     * saw.
     */
    youWereAsked: "You were asked",
    /**
     * A check, in the answer list.
     *
     * Shown INSTEAD of a verdict word, because a check has none: it is graded
     * per gap, and `understanding_of` — not this answer — decides whether the
     * stop is demonstrated. Labelling it is what let checks stop being hidden.
     */
    checkRow: "Check",
    checkRowCleared: (count: number) =>
      count === 1 ? "cleared 1" : `cleared ${count}`,
    checkRowClearedNone: "nothing cleared",
    /** Which mechanism put the question. Absent for the unit's original prompt —
     *  that is the unmarked case and a badge saying so would be noise on every
     *  row. */
    askedBy: {
      reteach: "rewritten question",
      verification: "check question",
      reassessment: "fresh question",
    } as Record<string, string>,
    checkUnderstanding: "Check your understanding",
    answerPlaceholder: "Write your answer…",
    grading: "Grading…",
    submit: "Submit",
    skipStop: "Skip this stop",
    submitHint: "⌘↵ to submit",
    /**
     * The two ways to answer a question that ships options. The learner picks
     * the input, not the marking: an option and a typed sentence are graded the
     * same way, against the objective.
     */
    writeOwnAnswer: "Write my own answer instead",
    chooseFromOptions: "Choose from the options instead",
    loadingShort: "Loading…",
    nextStop: "Next stop →",
    /**
     * THE ONE RETRY. Which mechanism serves it — a check on a named
     * misconception, or a fresh question about the objective — is ours to
     * decide, and a learner asked to pick between them is being asked to
     * diagnose themselves before they are allowed another go.
     */
    askAgain: "Ask me again",
    /** Shown where the composer used to be, once the unit's prompt is spent. */
    promptAnswered:
      "You've answered this one, and the explanation is on the Lesson tab. To show it again you'll get a different question.",
    askAgainBusy: "Writing a question…",
    /** Why there is no retry. Each is something to act on or accept, never a
     *  malfunction, so each is said rather than the control silently vanishing. */
    retryReason: {
      objective_met: "You've shown this one — nothing left to check here.",
      budget_spent:
        "You've used both fresh questions on this stop. It stays open — set it aside or move on.",
      already_asked: "There's a question waiting for you above.",
      not_applicable: "There's nothing to assess on this stop.",
    } as Record<string, string>,
    /** How many fresh objective questions remain. Shown only on the last one —
     *  a running counter on every verdict would be pressure, not information. */
    lastAskLeft: "Last fresh question on this stop.",
    /** The heading over a fresh objective-scoped question. */
    reassessmentHeading: "A different question, same objective",
    buildWarmUp: "Build me a warm-up",
    startWarmUp: "Start the warm-up →",
    skipItMoveOn: "Skip it, move on",
    moveOnAnyway: "Move on anyway",
    /**
     * Beside `Next stop →` on a stop the learner has already answered.
     *
     * Says why the button is there without claiming anything about how well they
     * did — a revisit to a stop they got wrong shows the same row, and captioning
     * it "done" would be a verdict this line has no business giving.
     */
    alreadyDealtWith: "You've already worked on this stop.",
    /**
     * THE OTHER HALF OF THIS STOP, at the foot of each surface.
     *
     * Lesson and Understanding are two views of one activity, and the only way
     * between them was the tab bar at the very top of the column — so a learner
     * who had read the material to the bottom had to scroll all the way back up
     * to answer, and one who had finished with their verdict had to do the same
     * to re-read what it was about.
     *
     * Named for the DESTINATION rather than the act. `Continue` or `Back` would
     * be a second name for a place the tab bar already labels, and two names for
     * one place is two places.
     */
    toUnderstanding: "Understanding →",
    toLesson: "← Lesson",
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
    /**
     * The cancel, on a session the learner chose to end.
     *
     * Named as what it DOES — carry on where they were — rather than as
     * "Cancel", which would describe a dialog. Nothing is being cancelled: the
     * session was never ended, and this screen is what asks whether it should
     * be.
     */
    keepGoing: "Keep going →",
    notFinishedYet:
      "Nothing has been ended yet — your session is exactly where you left it.",
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
    // --- the map's one context line ---
    //
    // The shape of the route, plus the one thing about it the session header does
    // not already say. Both are counted off the stops on screen, with the same
    // definitions `progress.py` uses, so neither can disagree with the header —
    // and neither is a measure the header already reports, which is what would
    // turn the map back into the dashboard it stopped being.
    //
    // "need work" rather than "need attention": it is the wording the
    // understanding vocabulary already uses for `unresolved`, and a route that
    // called the same state two things would be the exact drift M3a.3 closed.
    chapterCount: (count: number) =>
      count === 1 ? "1 chapter" : `${count} chapters`,
    needWork: (count: number) =>
      count === 1 ? "1 needs work" : `${count} need work`,
    // --- the map's key ---
    //
    // WORDING RULE: a row names the symbol in the words the MAP already uses and
    // then says what it means. Never the model's own vocabulary — a learner never
    // meets `standing`, `disposition` or `insufficient`, and a key is the last
    // place to introduce them.
    //
    // The bar gets ONE row although two standings draw it. `passed_by` and
    // `set_aside` differ to the model and not to the symbol: the bar says "you
    // closed this", the card's own caption says which way, and a second row would
    // teach a distinction the marker does not make.
    legend: {
      open: "Key",
      hint: "What the markers on this map mean",
      stopGroup: "The markers",
      routeGroup: "The line",
      here: "The stop you are standing on.",
      demonstrated: "You explained it, and never fell short here.",
      needsWork: "Assessed, and not demonstrated yet.",
      untouched: "Nothing has happened here yet.",
      closedLabel: "Closed without demonstrating",
      closed: "You moved on, skipped it, or said you already knew it.",
      walkedLabel: "Behind you",
      walked: "The part of the route you have already walked.",
      aheadLabel: "Still ahead",
      ahead: "Where the route goes next.",
      // The two branch kinds, and the difference between them is the whole
      // reason they are drawn in different colours: one is the journey reacting
      // to an answer, the other was never promised in the first place.
      branchWarmUp: "The journey changed shape: a warm-up added after an answer fell short.",
      optionalLabel: "Off the default walk",
      branchOptional: "Depth you did not ask for. Still yours to read.",
    },
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
    gapWaived: "Ignored for now, by you",
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
    // ── auth (multi-user M2) ──────────────────────────────────────────────
    //
    // Both of these are deliberately incurious. The backend returns one refusal
    // for a wrong password and for an email that has no account, because "is
    // this person a user here" is not a question an anonymous visitor gets to
    // ask; the copy must not undo that by being more specific than the API.
    not_authenticated: "Your session has ended. Sign in again.",
    oauth_state: "That sign-in link expired. Try again.",
    oauth_failed: "Google sign-in didn't complete. Try again.",
    oauth_unverified:
      "Google hasn't verified that email address, so it can't be used to sign in here.",
    google_not_configured:
      "Google sign-in isn't set up on this server. Use your email and password.",
    no_pending_link: "That sign-in link expired. Start again from the sign-in page.",
    last_identity:
      "That's the only way into this account, so it can't be removed. Set a password first.",
    too_many_attempts: "Too many attempts. Wait a moment, then try again.",
    // One message for unknown, expired and already-used, because the API
    // returns one refusal for all three — a reset link that has been spent must
    // not be distinguishable from one that never existed.
    invalid_reset_token:
      "That reset link has expired or has already been used. Request a new one.",
    "Email or password is incorrect.": "Email or password is incorrect.",
    "That email cannot be used to register.":
      "That email can't be used. Try signing in instead.",
    // `passwords.validate`'s refusals, mapped so they survive `errorTextOr`.
    // These are the opposite case to the login refusals above: this is the
    // caller's OWN password being judged, so it reveals nothing about anyone
    // else and the person cannot act without being told what is wrong. Worded
    // identically to the API on purpose — the mapping exists to mark them as
    // messages we have vetted, not to reword them.
    //
    // COUPLED to `passwords.MIN_PASSWORD_LENGTH`: raising it there changes the
    // sentence and this key stops matching, at which point the learner gets the
    // generic failure instead of the actionable one. Cheap to notice, so it is
    // recorded rather than engineered around.
    "Use at least 10 characters.": "Use at least 10 characters.",
    "That password is too common. Pick another.":
      "That password is too common. Pick another.",
    // A session planned before the route was snapshotted, so there is nothing to
    // restore it to. Says what to do instead, because the learner cannot fix this
    // one and rebuilding genuinely is the way out.
    no_plan_snapshot:
      "This session was created before routes could be restored, so it can't be started over. Rebuilding the learning path will give you a fresh one.",
    node_not_found: "That stop isn't part of this session.",
    // --- the Tutor ---
    tutor_limit_reached:
      "You've used all your tutor questions for this session. Your route and your answers are unaffected.",
    question_too_long: "That's a bit long — try asking it in a sentence or two.",
    question_empty: "Type a question first.",
    // The ladder is spent. Deliberately not phrased as a refusal to help: asking
    // is never blocked, only being written another hint is.
    hint_ladder_spent:
      "That's every hint for this question. You can still ask me about the code, or see the explanation.",
    // A hint or a reveal on a stop that is not asking anything. A client bug
    // rather than a learner action, but it must still read as a sentence.
    not_asking: "There's no open question here right now.",
    already_revealed: "You've already seen the explanation for this question.",
    // The learner revealed the answer in the tutor and then submitted an answer
    // to the same question — a stale composer, usually in a second tab.
    prompt_revealed:
      "You've seen the explanation for this question, so it can't be marked. Ask for a fresh question and answer that one instead.",
    no_explanation_for_this_question:
      "This is a fresh check, so there's no explanation to show — it's meant to be answered from what you already know.",
    no_explanation_available: "There's no explanation stored for this stop yet.",
    turn_not_found: "That message is no longer in your conversation.",
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

/**
 * `errorText`, but never shows a backend string we have not worded ourselves.
 *
 * The fall-through in `errorText` is right where the API's `detail` slugs are
 * the only thing that can arrive. It is wrong for anything a *transport* failure
 * can reach: a stale server missing a new route answers `{"detail":"Not Found"}`,
 * and "Not Found" rendered under an email field tells a learner nothing about
 * their email, their account, or what to do. Prefer this wherever an unmapped
 * message would be shown to somebody who cannot act on it.
 */
export function errorTextOr(message: string, fallback: string): string {
  return t.errors[message.trim()] ?? fallback;
}
