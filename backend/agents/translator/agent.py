# Translator Agent — renders already-written session prose in another language.
#
# Why this exists: a learning graph's titles and lessons are generated once, in
# the language the session was created in, and then persisted. Regenerating them
# to switch language would cost a full pipeline run and — worse — produce
# *different lessons*, silently invalidating the answers the user already gave
# against the originals. Translating preserves the session; regenerating replaces
# it.
#
# Entry point:
#   translate(client, texts, target_language) → {key: translated}
#
# Batched by design: one call carries every string that needs translating, so
# switching the language of a whole graph costs a single Haiku call rather than
# one per node. Keys are opaque to the model and come back unchanged, which is
# what lets the caller reassemble the result without positional guesswork.

import json
import os

import anthropic

from backend.agents.language import SUPPORTED_LANGUAGES


MODEL = "claude-haiku-4-5"
# Generous: a whole graph's titles plus one lesson body, both directions.
MAX_TOKENS = 4096

_SYSTEM_PROMPT = """\
You translate developer-education prose between languages.

You receive a JSON object mapping opaque keys to source strings. Return a JSON
object with THE SAME KEYS, where each value is that string translated into
{language}.

Rules:
- Translate the prose only. Never translate, transliterate, or "correct" a code
  identifier, function name, class name, file path, module name, CLI flag, or
  anything inside backticks — reproduce those byte-for-byte.
- Preserve markdown: backticks, **bold**, lists, and line breaks stay exactly
  where they are.
- Preserve the meaning and the register. These are lesson titles, code
  walkthroughs, and questions put to a developer — keep them concise and
  concrete, not florid.
- A string that is already in {language} comes back unchanged.
- Return every key you were given, and no others.
- Return ONLY the JSON object — no markdown fences, no commentary.
"""


def _parse(raw: str) -> dict:
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
    if not isinstance(decoded, dict):
        raise ValueError("translation response was not an object")
    return decoded


def translate(
    texts: dict[str, str],
    target_language: str,
    client: anthropic.Anthropic | None = None,
) -> dict[str, str]:
    """Translate a batch of strings, keyed so the caller can reassemble them.

    Returns only the keys that came back as non-empty strings. A key the model
    dropped or mangled is simply absent — callers fall back to the original,
    because showing untranslated prose beats showing nothing.

    Raises on a transport or parse failure so the caller can decide whether to
    degrade; it never raises for a partially-translated batch.
    """
    if not texts:
        return {}
    if target_language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported target language: {target_language!r}")

    if client is None:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    system = _SYSTEM_PROMPT.format(language=SUPPORTED_LANGUAGES[target_language])
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[
            {
                "role": "user",
                "content": json.dumps(texts, ensure_ascii=False, indent=1),
            }
        ],
    )
    decoded = _parse(response.content[0].text)

    return {
        key: decoded[key]
        for key in texts
        if isinstance(decoded.get(key), str) and decoded[key].strip()
    }
