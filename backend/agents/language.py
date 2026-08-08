# Output language for the agents that produce text the user actually reads.
#
# The Mentor, Teaching, Grader and Goal agents all write prose that lands in the
# UI (node titles, walkthroughs, grading rationales). That prose follows the
# user's chosen language. Everything a downstream component *parses* — JSON
# keys, classification values, concept tags, the `depth` and `goal_type` enums —
# stays English, because the frontend and the other agents key off those strings.
#
# The language rides on OnboardState.goal["language"], which is set once during
# the goal dialogue and persisted with the graph. Agents receive state.goal
# already, so nothing new has to be threaded through the pipeline.

DEFAULT_LANGUAGE = "en"

# Locale code → the name to use when instructing the model.
SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "he": "Hebrew",
}

# Locales written right-to-left. Latin identifiers embedded in RTL prose get
# reordered by the bidi algorithm around punctuation, so these get an extra
# instruction to fence them.
RTL_LANGUAGES = frozenset({"he"})


def language_of(goal: dict | None) -> str:
    """The locale code carried by a goal dict, defaulting to English."""
    code = (goal or {}).get("language") or DEFAULT_LANGUAGE
    return code if code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def language_instruction(goal: dict | None) -> str:
    """A system-prompt suffix pinning the output language.

    Returns "" for English so the English path sends exactly the prompt it
    always did — no behaviour change, no extra tokens.
    """
    code = language_of(goal)
    if code == DEFAULT_LANGUAGE:
        return ""

    name = SUPPORTED_LANGUAGES[code]
    rtl_note = (
        f"\n- {name} is written right-to-left. When an English identifier appears\n"
        f"  inside a {name} sentence, wrap it in backticks (`Session.send`) so it\n"
        "  stays readable when the two directions meet.\n"
        if code in RTL_LANGUAGES
        else ""
    )

    return f"""

OUTPUT LANGUAGE — {name}

Write every piece of prose a person will read in {name}: titles, explanations,
questions, rationales, and any sentence describing the code.

Keep these in English exactly as this prompt specifies them — they are parsed by
other software, not read as prose:
- every JSON key
- every value drawn from a fixed set this prompt enumerates (classifications,
  edge kinds, prompt kinds, confidence levels, concept tags, depth, goal_type)
- code identifiers, file paths, module and function names, and anything quoted
  verbatim from the source{rtl_note}
Do not translate a code identifier, and do not transliterate one. `Session`
stays `Session`.
"""
