import type { Dictionary } from "@/lib/i18n/en";

/**
 * Hebrew. Typed as `Dictionary`, so this file fails to compile the moment a key
 * is added to `en.ts` and not translated here.
 *
 * Directional glyphs are flipped rather than translated: an arrow that means
 * "forward" points left in an RTL layout.
 */
export const he: Dictionary = {
  appName: "CodeOnboard",
  tagline: "בנה הבנה אמיתית של בסיס קוד לא מוכר, מושג מעוגן אחד בכל פעם.",

  language: {
    label: "שפה",
    en: "English",
    he: "עברית",
  },

  home: {
    repoLabel: "מאגר לקריאה",
    repoPlaceholder: "https://github.com/psf/requests",
    recent: "אחרונים",
    checking: "בודק את המאגר…",
    start: "התחל",
    repoUnreachable: "לא ניתן היה לפתוח את המאגר הזה.",
    serverUnreachable: "לא ניתן להגיע לשרת.",
    pipelineFailed: "לא ניתן היה לבנות עבורך מסלול למידה.",
  },

  starting: {
    label: "קורא את המאגר",
    phases: [
      "משכפל את המאגר",
      "מנתח קבצים למושגים",
      "מאנדקס לאחזור",
      "מתכנן את המסלול שלך",
    ],
    elapsed: (seconds: number) =>
      `חלפו ${seconds} שניות · בדרך כלל כדקה על מאגר קטן`,
  },

  failed: {
    label: "לא ניתן היה לבנות עבורך מסלול למידה",
    reassurance:
      "התשובות שלך נשמרו, כך שניסיון חוזר לא יחייב אותך לענות על השאלות שוב.",
    tryAgain: "נסה שוב",
    differentRepo: "בחר מאגר אחר",
  },

  goal: {
    starting: "מתחיל את הריאיון…",
    progress: (index: number, total: number) => `שאלה ${index} מתוך ${total}`,
    answerPlaceholder: "התשובה שלך…",
    thinking: "חושב…",
    continue: "המשך",
    enterHint: "↵ להמשך",
    answerFailed: "לא ניתן היה לשמור את התשובה.",
  },

  session: {
    readiness: "מוכנות",
    hideSource: "הסתר מקור",
    showSource: "הצג מקור",
    startingOver: "מתחיל מחדש…",
    startOver: "התחל מחדש",
    tabLesson: "שיעור",
    tabMap: "מפת התקדמות",
    mapHint: (count: number) =>
      `${count} מושגים · לחץ על תחנה כדי לעבור אליה · esc לחזרה`,
    loading: "טוען סשן…",
    loadFailed: "לא ניתן היה לטעון את הסשן הזה.",
    retryLoad: "נסה לטעון שוב",
    jumpFailed: "לא ניתן היה לעבור לתחנה הזו.",
    firstLesson: "טוען את השיעור הראשון שלך…",
    depth: {
      overview: "סקירה",
      moderate: "בינוני",
      deep: "מעמיק",
    },
  },

  rail: {
    title: "המסלול שלך",
    openMap: "פתח מפה",
    addedAfterConfusion: "נוסף לאחר בלבול",
    markedWeak: "⚑ סומן כחלש",
  },

  lesson: {
    writing: "כותב את השיעור…",
    warmUpHeading: "חימום · נוסף לאחר בלבול",
    stopOf: (position: number, total: number) => `תחנה ${position} מתוך ${total}`,
    lines: (start: number, end: number) => `שורות ${start}–${end}`,
    recoveredLabel: "החימום עבד",
    recoveredBody: "הצלחת את זה אחרי שלמדת קודם את",
    recoveredBodyEnd: ". התחנה נשארת מסומנת כנקודה חלשה, אבל התאוששת ממנה.",
    walkthrough: "הסבר",
    yourAnswers: (count: number) => `התשובות שלך (${count})`,
    youWrote: "כתבת",
    feedback: "משוב",
    checkUnderstanding: "בדוק את ההבנה שלך",
    answerPlaceholder: "כתוב את התשובה שלך…",
    grading: "בודק…",
    submit: "שלח",
    skipStop: "דלג על התחנה",
    submitHint: "⌘↵ לשליחה",
    loadingShort: "טוען…",
    nextStop: "← לתחנה הבאה",
    buildWarmUp: "בנה לי תרגיל חימום",
    startWarmUp: "← התחל את החימום",
    skipItMoveOn: "דלג והמשך",
    moveOnAnyway: "המשך בכל זאת",
    finishEarly: "סיים את הסשן מוקדם",
    gradeFailed: "לא ניתן היה לבדוק את התשובה. נסה שוב.",
    advanceFailed: "לא ניתן היה לעבור לתחנה הבאה.",
    warmUpFailed: "לא ניתן היה לבנות תרגיל חימום לתחנה הזו.",
    warmUpAdded: "הוספנו תרגיל חימום קצר לפני התחנה הזו כדי לבנות אליה בהדרגה.",
    warmUpExists: "כבר היה לך תרגיל חימום לתחנה הזו, ואין עוד אחד להוסיף.",
    warmUpUnavailable:
      "לא הצלחנו לבנות תרגיל חימום לתחנה הזו, אז ההחלטה איך להמשיך היא שלך.",
    verdict: {
      understood: "הבנת",
      partial: "כמעט שם",
      confused: "עדיין לא",
      "off-topic": "לא לעניין",
    },
    when: {
      justNow: "עכשיו",
      minutes: (n: number) => `לפני ${n} דקות`,
      hours: (n: number) => `לפני ${n} שעות`,
    },
  },

  completion: {
    tabSummary: "סיכום",
    tabMap: "המפה שלך",
    label: "הסשן הושלם",
    heading: (understood: number, total: number) =>
      `הבנת ${understood} מתוך ${total} מושגים`,
    body:
      "המפה שלך נשמרה. חזור לאותו מאגר ואותה מטרה ותמשיך בדיוק מהנקודה שבה עצרת — כולל התחנות שעדיין מסומנות כחלשות.",
    anotherPass: (count: number) => `שווה מעבר נוסף (${count})`,
    newSession: "התחל סשן חדש",
    goHome: "חזרה לדף הבית",
  },

  map: {
    label: "מה הבנת עד כה",
    thisCodebase: "בסיס הקוד הזה",
    conceptsUnderstood: (understood: number, total: number) =>
      `${understood} מתוך ${total} מושגים הובנו`,
    filesTouched: (count: number) => `${count} קבצים נגעת בהם`,
    markedWeak: (count: number) => `${count} סומנו כחלשים`,
    readiness: "מוכנות",
    byKind: "לפי סוג ההבנה",
    topicsTouched: "נושאים שנגעת בהם",
    whereInRepo: "היכן במאגר",
    theRoute: "המסלול",
    unlocks: (title: string) => `· פותח את ״${title}״`,
    understoodOfTotal: (understood: number, total: number) =>
      `${understood} מתוך ${total} הובנו`,
  },

  tags: {
    architecture: "ארכיטקטורה",
    flow: "זרימה",
    extension_point: "נקודת הרחבה",
    risk: "סיכון",
    test_coverage: "כיסוי בדיקות",
    component: "רכיב",
  },

  states: {
    understood: "הובן",
    partial: "חלקי",
    failed: "דורש מעבר נוסף",
    not_started: "טרם התחיל",
  },

  errors: {
    session_not_found: "הסשן הזה כבר לא קיים.",
    node_not_found: "התחנה הזו אינה חלק מהסשן הזה.",
    session_has_no_current_node: "לסשן הזה אין תחנה נוכחית.",
    no_lesson_rendered_yet: "השיעור עדיין לא נטען — תן לו רגע.",
    invalid_path: "נתיב הקובץ הזה אינו בתוך המאגר.",
    file_not_found: "הקובץ הזה לא נמצא במאגר.",
    no_graph: "לא ניתן היה לבנות מסלול למידה עבור המאגר הזה.",
    synthesis_failed: "לא הצלחנו להבין את התשובות. נסה לנסח מחדש.",
  },
};
