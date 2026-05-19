# Prioritization Agent — narrows the module map to what matters for the goal.
#
# Entry point:
#   run(state, client) → reads module_map + goal, calls Haiku once to pick the
#                        relevant modules, validates the result, writes
#                        state.relevant_modules, and returns state.
#
# Runs between the Code Structure Agent and the Mentor Agent. Critical for
# large repos (fastapi has 50+ modules, most irrelevant for any one goal):
# a smaller map means cheaper, more focused Mentor Agent retrieval.
#
# Mirrors the other agents: client injected, errors appended to state.errors,
# never raises. On any failure it leaves relevant_modules as None, which the
# Mentor Agent treats as "use the full map" — so a failure degrades to Phase 1
# behaviour rather than breaking the pipeline.

import json
import os

import anthropic
from pydantic import BaseModel

from backend.pipeline.state import OnboardState
from backend.pipeline.profiles import get_profile

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 1024

# Below this many modules, filtering is not worth an LLM call — the Mentor
# Agent can handle a handful of modules directly.
MIN_MODULES_TO_PRIORITIZE = 6


class PrioritizationOutput(BaseModel):
    relevant_modules: list[str]


_SYSTEM_PROMPT = """\
You are triaging a Python codebase for a developer with a specific goal.

You are given the developer's goal and a list of the repository's modules with
a one-sentence purpose for each. Decide which modules the developer needs to
read to achieve their goal, and which can be skipped.

Return ONLY a JSON object with exactly this key:
  relevant_modules: list of module names (exactly as given) worth reading

Rules:
- Use module names exactly as they appear in the list — do not invent names.
- Follow the pruning instruction given with the goal.
- Always keep at least one module. Never return an empty list.
- Return ONLY the JSON object — no markdown fences, no explanation.
"""

# The retrieval profile picks the pruning aggressiveness; the directive is
# spelled out to the model so it does not have to infer it from goal_type.
_PRUNING_DIRECTIVE: dict[str, str] = {
    "preserve_breadth": (
        "Pruning instruction: the developer wants a broad tour. Keep the major "
        "modules and only drop clearly peripheral ones (tests, examples, build "
        "tooling)."
    ),
    "prune": (
        "Pruning instruction: the developer has a focused goal. Prune "
        "aggressively — keep only the modules on the path to that goal. In a "
        "large repo most modules are noise."
    ),
}


def _format_module_list(module_map: dict) -> str:
    return "\n".join(
        f"- {name}: {entry['purpose']}" for name, entry in module_map.items()
    )


def _build_prompt(goal: dict, module_map: dict, pruning_mode: str) -> str:
    parts = [
        f"Developer goal: {goal['primary_goal']}",
        f"Goal type: {goal['goal_type']}",
    ]
    focus = goal.get("focus_area")
    if focus:
        parts.append(f"Focus area: {focus}")
    parts.append("")
    parts.append(_PRUNING_DIRECTIVE[pruning_mode])
    parts.append("")
    parts.append("Modules:")
    parts.append(_format_module_list(module_map))
    return "\n".join(parts)


def _parse_output(raw: str) -> PrioritizationOutput:
    raw = raw.strip()
    if "```json" in raw:
        raw = raw.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in raw:
        parts = raw.split("```")
        if len(parts) >= 2:
            raw = parts[1]
    start = raw.find("{")
    if start < 0:
        raise ValueError("no JSON object found in response")
    decoded, _ = json.JSONDecoder().raw_decode(raw[start:])
    return PrioritizationOutput(**decoded)


def run(
    state: OnboardState,
    client: anthropic.Anthropic | None = None,
) -> OnboardState:
    if client is None:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    if state.goal is None:
        state.errors.append("prioritization_agent: goal missing")
        return state

    if state.module_map is None:
        state.errors.append("prioritization_agent: module_map missing")
        return state

    # Small maps do not need filtering — skip the call and let the Mentor
    # Agent see the full map (relevant_modules stays None).
    if len(state.module_map) < MIN_MODULES_TO_PRIORITIZE:
        return state

    profile = get_profile(state.goal["goal_type"])
    prompt = _build_prompt(state.goal, state.module_map, profile.prioritization_mode)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        output = _parse_output(response.content[0].text)
    except Exception as e:
        state.errors.append(f"prioritization_agent LLM call failed: {e}")
        return state

    # Keep only names that exist in the map — drop anything the LLM invented.
    relevant = [m for m in output.relevant_modules if m in state.module_map]

    # If the LLM kept everything (or nothing usable), there is nothing to gain
    # from filtering — leave relevant_modules None so the Mentor Agent uses the
    # full map unchanged.
    if not relevant or len(relevant) == len(state.module_map):
        return state

    state.relevant_modules = relevant
    return state
