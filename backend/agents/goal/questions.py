# Question flow for the Goal Agent dialogue.
#
# Everyone gets the 4 CORE_QUESTIONS in order:
#   1. familiarity  (options)   — where the user is starting from
#   2. goal_type_raw (options)  — why they're here; drives follow-up routing
#   3. primary_goal (free text) — what they want to walk away able to do
#   4. background   (free text) — languages/frameworks they already know
#
# After Q4, FOLLOWUP_QUESTIONS adds 1–2 goal-specific questions:
#   understand_system / understand_component  →  focus_area
#   understand_architecture                   →  focus_area
#   contribute_code                           →  contribution_context
#   improve_existing_system                   →  change_target
#                                                risk_tolerance
#   debug_issue                               →  error_description
#                                                tried_so_far
#
# These strings are shown to the user verbatim, so they are translated here
# rather than by the model — the interview is the same five questions in every
# language and there is no reason to pay for, or risk drift on, a translation.
# Question.text and Question.options are keyed by locale; `localize` flattens a
# Question down to one language for the wire.
#
# The option a user picks comes back as the display string, so OPTION_KEYS maps
# every localized option back to a stable English key. GOAL_TYPE_MAP is keyed on
# those stable keys, which is why answering Q2 in Hebrew still routes correctly.

from dataclasses import dataclass

from backend.agents.language import DEFAULT_LANGUAGE


@dataclass
class Question:
    key: str
    text: dict[str, str]
    options: dict[str, list[str]] | None = None


@dataclass
class LocalizedQuestion:
    key: str
    text: str
    options: list[str] | None = None


def localize(question: Question, language: str = DEFAULT_LANGUAGE) -> LocalizedQuestion:
    """Flatten a Question to one language, falling back to English."""
    text = question.text.get(language) or question.text[DEFAULT_LANGUAGE]
    options = None
    if question.options is not None:
        options = question.options.get(language) or question.options[DEFAULT_LANGUAGE]
    return LocalizedQuestion(key=question.key, text=text, options=options)


# --- option vocabularies -----------------------------------------------------
#
# Each entry is (stable English key, {locale: display string}). The key is what
# the rest of the backend reasons about; the display strings are what the user
# sees and what comes back on the wire.

_FAMILIARITY: list[tuple[str, dict[str, str]]] = [
    (
        "Starting fresh — never looked at it",
        {
            "en": "Starting fresh — never looked at it",
            "he": "מתחיל מאפס — לא הסתכלתי עליו בכלל",
        },
    ),
    (
        "Skimmed the README or docs",
        {
            "en": "Skimmed the README or docs",
            "he": "עברתי ברפרוף על ה-README או התיעוד",
        },
    ),
    (
        "Looked at some code but still confused",
        {
            "en": "Looked at some code but still confused",
            "he": "הסתכלתי על קצת קוד אבל עדיין מבולבל",
        },
    ),
    (
        "Used it before, now diving into the source",
        {
            "en": "Used it before, now diving into the source",
            "he": "השתמשתי בו בעבר, עכשיו צולל לקוד המקור",
        },
    ),
]

_GOAL_TYPES: list[tuple[str, str, dict[str, str]]] = [
    (
        "Use it in my own project",
        "understand_component",
        {
            "en": "Use it in my own project",
            "he": "להשתמש בו בפרויקט שלי",
        },
    ),
    (
        "Understand the architecture (layers, boundaries, design)",
        "understand_architecture",
        {
            "en": "Understand the architecture (layers, boundaries, design)",
            "he": "להבין את הארכיטקטורה (שכבות, גבולות, עיצוב)",
        },
    ),
    (
        "Improve or extend the codebase safely",
        "improve_existing_system",
        {
            "en": "Improve or extend the codebase safely",
            "he": "לשפר או להרחיב את הקוד בבטחה",
        },
    ),
    (
        "Contribute code / open a PR",
        "contribute_code",
        {
            "en": "Contribute code / open a PR",
            "he": "לתרום קוד / לפתוח PR",
        },
    ),
    (
        "Debug an issue I'm hitting",
        "debug_issue",
        {
            "en": "Debug an issue I'm hitting",
            "he": "לדבג תקלה שאני נתקל בה",
        },
    ),
    (
        "Understand how it works (reading/learning)",
        "understand_system",
        {
            "en": "Understand how it works (reading/learning)",
            "he": "להבין איך הוא עובד (קריאה/לימוד)",
        },
    ),
]


def _by_locale(entries: list[tuple[str, dict[str, str]]]) -> dict[str, list[str]]:
    locales = {loc for _, labels in entries for loc in labels}
    return {loc: [labels[loc] for _, labels in entries] for loc in locales}


FAMILIARITY_OPTIONS: dict[str, list[str]] = _by_locale(_FAMILIARITY)

GOAL_TYPE_OPTIONS: dict[str, list[str]] = _by_locale(
    [(key, labels) for key, _, labels in _GOAL_TYPES]
)

# Every localized display string → its stable English key. Includes the English
# strings themselves, so lookup is uniform regardless of interview language.
OPTION_KEYS: dict[str, str] = {
    label: key
    for entries in (_FAMILIARITY, [(k, lbl) for k, _, lbl in _GOAL_TYPES])
    for key, labels in entries
    for label in labels.values()
}

GOAL_TYPE_MAP: dict[str, str] = {key: goal_type for key, goal_type, _ in _GOAL_TYPES}


def option_key(answer: str) -> str:
    """The stable English key for a chosen option, or the answer itself.

    Free-text answers pass through untouched — only option answers are mapped.
    """
    return OPTION_KEYS.get(answer.strip(), answer)


# --- questions ---------------------------------------------------------------

CORE_QUESTIONS: list[Question] = [
    Question(
        key="familiarity",
        text={
            "en": "How familiar are you with this codebase?",
            "he": "כמה אתה מכיר את בסיס הקוד הזה?",
        },
        options=FAMILIARITY_OPTIONS,
    ),
    Question(
        key="goal_type_raw",
        text={
            "en": "What brings you to this repo?",
            "he": "מה מביא אותך למאגר הזה?",
        },
        options=GOAL_TYPE_OPTIONS,
    ),
    Question(
        key="primary_goal",
        text={
            "en": "What specifically do you want to be able to do after this session?",
            "he": "מה בדיוק תרצה להיות מסוגל לעשות בסוף הסשן הזה?",
        },
    ),
    Question(
        key="background",
        text={
            "en": "What languages, frameworks, or similar tools do you already know?",
            "he": "אילו שפות, פריימוורקים או כלים דומים אתה כבר מכיר?",
        },
    ),
]

_UNDERSTAND_FOLLOWUP = Question(
    key="focus_area",
    text={
        "en": "Is there a part of the system you're most curious about, or do you want the full picture?",
        "he": "יש חלק במערכת שהכי מסקרן אותך, או שאתה רוצה את התמונה המלאה?",
    },
)

_ARCHITECTURE_FOLLOWUP = Question(
    key="focus_area",
    text={
        "en": "Any specific architectural concern (e.g. request lifecycle, extension surface, plugin system), or a full architectural tour?",
        "he": "יש נושא ארכיטקטוני ספציפי (למשל מחזור חיי בקשה, נקודות הרחבה, מערכת תוספים), או סיור ארכיטקטוני מלא?",
    },
)

FOLLOWUP_QUESTIONS: dict[str, list[Question]] = {
    "understand_system": [_UNDERSTAND_FOLLOWUP],
    "understand_component": [_UNDERSTAND_FOLLOWUP],
    "understand_architecture": [_ARCHITECTURE_FOLLOWUP],
    "contribute_code": [
        Question(
            key="contribution_context",
            text={
                "en": "Is there a specific issue or feature you're working on? (paste a GitHub issue link or describe it)",
                "he": "יש issue או פיצ'ר ספציפי שאתה עובד עליו? (הדבק קישור ל-issue בגיטהאב או תאר אותו)",
            },
        )
    ],
    "improve_existing_system": [
        Question(
            key="change_target",
            text={
                "en": "What change do you want to make? (e.g. \"add a new auth scheme\", \"refactor the session lifecycle\", \"extend the adapter interface\")",
                "he": "איזה שינוי אתה רוצה לעשות? (למשל \"להוסיף שיטת אימות חדשה\", \"לשכתב את מחזור החיים של הסשן\", \"להרחיב את ממשק האדפטר\")",
            },
        ),
        Question(
            key="risk_tolerance",
            text={
                "en": "How safety-critical is this change? (e.g. \"prototype, can break\", \"production use, must not regress\")",
                "he": "כמה קריטי השינוי הזה מבחינת בטיחות? (למשל \"אב טיפוס, מותר שיישבר\", \"שימוש בפרודקשן, אסור שתהיה רגרסיה\")",
            },
        ),
    ],
    "debug_issue": [
        Question(
            key="error_description",
            text={
                "en": "What error or unexpected behavior are you seeing?",
                "he": "איזו שגיאה או התנהגות לא צפויה אתה רואה?",
            },
        ),
        Question(
            key="tried_so_far",
            text={
                "en": "What have you already tried?",
                "he": "מה כבר ניסית?",
            },
        ),
    ],
}
