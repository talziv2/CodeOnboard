"""Stage 2 probe: does a *prompt-faithful* answer get marked down?

Stage 1 (`grader_eval.py`) answered each node's **objective**, clause by clause,
and 12/12 strong answers were graded `understood`. That rules out a blunt
"the Grader is too strict" story. It leaves a sharper hypothesis:

    The Grader marks against the OBJECTIVE (correct, per the B1 contract).
    The learner answers the PROMPT.
    Where the prompt elicits less than the objective states, an answer that is
    a complete, correct response to the question asked is still incomplete
    against the objective — and is graded `partial`.

Reading the six objectives against their six prompts, five under-elicit:

  requests/component     objective wants three auth forms; prompt asks only about
                         tuple vs HTTPBasicAuth — never about "any callable"
  requests/risk          objective wants the fix (set response.encoding); prompt
                         asks only what is wrong and what breaks
  requests/architecture  objective wants "...which is why any callable qualifies";
                         prompt asks only for the ownership line and the sequence
  fastapi/flow           objective wants the four-step chain and each step's
                         contribution; prompt asks only where control goes after
                         one line, and why
  fastapi/synthesis      objective wants "what you cannot do at runtime"; prompt
                         asks only about error discovery and performance

  fastapi/architecture   ALIGNED — the prompt asks for every clause. Control case.

PREDICTION, recorded before this ran (see git history):
  the five under-eliciting nodes -> `partial`
  the aligned node (fastapi/architecture) -> `understood`

If that is what comes back, the defect is in the objective/prompt contract, not
in grading calibration, and the fix belongs to Teaching — not to the Grader's
thresholds, labels or prompt.

Each answer below is a complete, correct, confident response to the question as
asked, and volunteers nothing the prompt did not ask for. Nothing here changes
any prompt, threshold, label or policy; this only measures.

    uv run python scripts/grader_probe_prompt.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(override=True)

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import anthropic  # noqa: E402

from grader_eval import DB, grade, load_node  # noqa: E402
from grader_eval_cases import OBJECTIVES  # noqa: E402

# node prefix -> (answer written to the PROMPT, predicted classification)
PROMPT_FAITHFUL: dict[str, tuple[str, str]] = {}


def _register(prefix: str, predicted: str, answer: str) -> None:
    PROMPT_FAITHFUL[prefix] = (answer.strip(), predicted)


_register(
    "b50c4cad", "partial",
    """
The tuple goes through the promotion branch at the top of prepare_auth(). It checks
whether auth is a tuple of length 2, and if so replaces it with HTTPBasicAuth(*auth) --
so ('alice', 'secret') becomes HTTPBasicAuth('alice', 'secret') before anything else
happens. After that branch, auth is an auth handler object either way.

The final auth_handler(self) call invokes that object's __call__ with the
PreparedRequest as its argument. For HTTPBasicAuth, __call__ sets
r.headers['Authorization'] to the base64 Basic credential string built from the
username and password, and returns r.

If the developer passed auth=HTTPBasicAuth('alice', 'secret') directly, the promotion
branch simply does not fire -- the object is already an auth handler, so it falls
straight through to the same auth_handler(self) call. The two paths converge one line
later and produce the identical Authorization header. The tuple form is pure
convenience sugar; there is no behavioural difference.
""",
)

_register(
    "bbae87b9", "partial",
    """
The change removes the charset_normalizer fallback, so it silently mis-decodes any
response whose body is not UTF-8 and whose Content-Type header does not declare a
charset.

The current code only sets self.encoding from the Content-Type header. Plenty of
servers omit the charset there -- and for those responses self.encoding is None. Today
that None is what triggers apparent_encoding, which runs charset_normalizer over the
actual bytes and detects the real encoding. The proposed version replaces that
detection with a hardcoded assumption of UTF-8.

What breaks: any response in a non-UTF-8 encoding that does not announce it. A
Shift-JIS or Big5 or GB18030 page, a legacy latin-1 API, an ISO-8859-8 Hebrew page --
all of these decode as garbage. And because errors="replace" is used, nothing raises;
the bytes that fail to decode are silently replaced with U+FFFD. The caller gets a
string back, no exception, no warning, and the corruption is only visible if someone
looks at the text. That silence is the real danger -- a crash would at least be
noticed.

The author's premise, that modern APIs send UTF-8, is true for the APIs they happen to
use. requests is a general-purpose HTTP client that also fetches arbitrary web pages,
and the long tail of the web is not UTF-8.
""",
)

_register(
    "7ecc5fe3", "partial",
    """
The handler owns exactly one thing: mutating the PreparedRequest it is handed and
returning it. In practice that means setting the Authorization header (or whatever
credential-bearing headers or body its scheme needs) and handing the object back.

What it must NOT own: it does not build the request, does not choose the URL or method,
does not send anything, does not touch the connection, does not decide whether auth is
needed at all, and does not construct its own PreparedRequest. requests owns all of
that. The handler is handed a fully prepared request and is trusted only to add
credentials to it.

Sequence in prepare_auth():
  Before -- it resolves where the credentials come from. If auth was not passed
  explicitly it extracts any username/password embedded in the URL and uses that
  instead. It then normalises the tuple shorthand into an auth handler object.
  During -- it calls auth_handler(self), passing the PreparedRequest, and rebinds self
  to whatever comes back. That rebinding is why the handler's return value matters and
  why mutating in place but returning None would break it.
  After -- it re-runs prepare_content_length(self.body), because a handler may have
  changed the body (digest auth and some signing schemes do), and a stale
  Content-Length would corrupt the request on the wire.
""",
)

_register(
    "ed5b84d5", "understood",
    """
FastAPI is the application-level object; APIRouter is the route-collection object.
FastAPI owns everything that is true of the application as a whole -- the ASGI entry
point and middleware stack, exception handlers, the OpenAPI schema and docs endpoints,
lifespan/startup, and app-wide dependencies. It does not own the route table. It holds
an APIRouter as self.router and delegates every routing decision to it.

APIRouter owns the list of routes, the machinery that turns a decorated function into
an APIRoute, and the defaults that apply to a group of routes: prefix, tags,
dependencies, responses, and the like. When you write @app.get('/x'), FastAPI.get does
not register anything itself -- it returns self.router.get('/x'), so the registration
happens on the router.

That separation is what makes prefix and tag inheritance work. Because a router is a
first-class object that carries its own defaults, you can build one independently --
APIRouter(prefix='/users', tags=['users']) -- and then app.include_router() copies its
routes onto the app's router, merging the parent prefix and concatenating tags as it
goes. Inclusion is composable, so a router included into a router into an app
accumulates prefixes down the chain. If FastAPI stored routes directly, there would be
nothing to attach group-level defaults to, and no unit smaller than the app to compose;
you would be back to declaring the full path and full tag list on every single
endpoint. It also means the app's own routes and an included router's routes are the
same kind of thing, handled by one code path.
""",
)

_register(
    "44e85351", "partial",
    """
Control goes to APIRouter.get -- the router held on self.router. FastAPI.get's body is
just return self.router.get(...), forwarding every argument it was given, so the next
frame is the router's own get().

It goes there rather than straight to add_api_route because the router, not the app, is
what owns routes, and because the arguments are not yet in the form add_api_route
expects. APIRouter.get still has work to do: it is the layer that knows this call means
the GET method specifically, so it is where methods=['GET'] gets attached. Jumping
directly to add_api_route from FastAPI.get would mean the app duplicating that
knowledge, and would bypass the router entirely -- the route would have to be recorded
somewhere the app manages itself, which is exactly the design FastAPI avoids by
delegating.
""",
)

_register(
    "1699bba2", "partial",
    """
The reason is that all the introspection happens inside APIRoute.__init__, which runs
while the decorator is being applied -- that is, at import time, when Python evaluates
the @app.get(...) line -- and not when a request arrives.

APIRoute.__init__ calls get_dependant on the endpoint function. get_dependant walks the
signature parameter by parameter and hands each one to analyze_param, which reads the
three signals: the type annotation, the default value, and whether the name appears in
the path. From those it decides what the parameter is -- path param, query param, body
field, dependency -- and builds a Dependant node for it. A parameter you annotated with
a type it cannot resolve, or a path parameter whose name does not match anything in the
path string, fails right there, inside __init__, at decoration time. The exception
surfaces during import, before the server ever binds a port.

For error discovery that means the failure mode is a startup crash with a stack trace
pointing at the offending endpoint, rather than a 500 on some endpoint in production
that nobody exercised until a user hit it. The whole class of route-signature mistakes
becomes impossible to deploy -- the app will not start.

For performance it means the introspection cost is paid exactly once per route, at
import. Signature inspection, annotation resolution and Pydantic field construction are
genuinely expensive, and doing them per request would be a large per-request tax. At
request time solve_dependencies just walks the already-built Dependant tree and fills
in values, so the expensive analysis never repeats.
""",
)


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY missing", file=sys.stderr)
        return 2

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=180.0)
    rows: list[dict] = []

    for session_id, prefix, repo, kind, label in OBJECTIVES:
        answer, predicted = PROMPT_FAITHFUL[prefix]
        graph, node = load_node(session_id, prefix)
        if node is None:
            print(f"SKIP {prefix}: node not found", file=sys.stderr)
            continue
        got = grade(graph, node, answer, client)
        actual = got.get("classification")
        rows.append({
            "repo": repo, "kind": kind, "objective": label, "node": prefix,
            "prompt_elicits_full_objective": predicted == "understood",
            "predicted": predicted,
            "actual_classification": actual,
            "actual_gap": got.get("gap_kind"),
            "matches_prediction": actual == predicted,
            "rationale": got.get("rationale"),
        })
        mark = "OK " if actual == predicted else "XX "
        print(f"  {mark}{repo}/{kind:<14} predicted {predicted:<11} got "
              f"{str(actual):<11} gap={got.get('gap_kind')}", flush=True)
        print(f"      {str(got.get('rationale'))[:220]}", flush=True)

    line = "=" * 78
    print(f"\n{line}\nPROMPT-FAITHFUL ANSWERS\n{line}")
    hit = sum(1 for r in rows if r["matches_prediction"])
    print(f"  prediction held        {hit}/{len(rows)}")
    under = [r for r in rows if not r["prompt_elicits_full_objective"]]
    aligned = [r for r in rows if r["prompt_elicits_full_objective"]]
    for name, group in (("under-eliciting prompt", under), ("aligned prompt", aligned)):
        u = sum(1 for r in group if r["actual_classification"] == "understood")
        print(f"  {name:<24} understood {u}/{len(group)}")

    out = Path("docs/planning/phases/evidence/grader-prompt-faithful.json")
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nwritten: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
