"""Grader evaluation cases — expected labels, authored BEFORE any Grader run.

This file is committed on its own, ahead of the evaluation, so that "the expected
judgement was established first" is checkable in git history rather than
asserted. Nothing here was written to match the Grader's prompt wording; each
expectation comes from the objective and the repository evidence.

Six real objectives from two real B3 journeys, spanning five lesson kinds and
both demo repositories, so a single unusually hard objective cannot masquerade
as a systematic problem.

Eight answer qualities per objective. The one that matters most is the
`understood` / `partial` boundary — `complete` versus `concise` — because that
is where prune-ahead is being starved: a correct, objective-aligned answer that
simply does not elaborate should still be `understood`.

`expected_classification` is a SET where the taxonomy genuinely admits more than
one defensible answer (an "I don't know" is arguably `off-topic` or `confused`).
Narrowing those to one value would manufacture disagreement.
"""

# (session_id, node_id_prefix, repo, kind, short label)
OBJECTIVES = [
    ("a3234f413b024fbfb4242917fa34c173", "b50c4cad", "requests", "component",
     "auth parameter forms"),
    ("a3234f413b024fbfb4242917fa34c173", "bbae87b9", "requests", "risk",
     "response.text encoding"),
    ("a3234f413b024fbfb4242917fa34c173", "7ecc5fe3", "requests", "architecture",
     "AuthBase contract"),
    ("d1e5fc95e9f740f8a06f024e492248b7", "ed5b84d5", "fastapi", "architecture",
     "app/router two layers"),
    ("d1e5fc95e9f740f8a06f024e492248b7", "44e85351", "fastapi", "flow",
     "decorator-to-registration chain"),
    ("d1e5fc95e9f740f8a06f024e492248b7", "1699bba2", "fastapi", "synthesis",
     "declaration vs runtime"),
]

# quality -> (expected classifications, expected gap_kind or None if unconstrained)
EXPECTATION = {
    "complete":       ({"understood"}, "none"),
    "concise":        ({"understood"}, "none"),
    "wrong_altitude": ({"partial", "confused"}, "right_idea_wrong_altitude"),
    "partial":        ({"partial"}, None),
    "wrong_model":    ({"confused"}, "wrong_model"),
    "no_attempt":     ({"off-topic", "confused"}, "no_attempt"),
    "off_topic":      ({"off-topic"}, None),
    "missing_prereq": ({"off-topic", "confused"}, "missing_prerequisite"),
}

ANSWERS: dict[str, dict[str, str]] = {

    # ── requests · component · the three forms `auth` accepts ────────────────
    "b50c4cad": {
        "complete":
            "auth accepts three forms. A (user, pass) tuple, which prepare_auth "
            "detects and promotes to HTTPBasicAuth(user, pass); an AuthBase "
            "instance such as HTTPBasicAuth or HTTPDigestAuth, used as-is; or any "
            "callable with the same signature. Whatever it is, prepare_auth calls "
            "auth_handler(self) with the PreparedRequest and the handler mutates "
            "it. Because the tuple is promoted to exactly HTTPBasicAuth, passing "
            "('alice','secret') and passing HTTPBasicAuth('alice','secret') "
            "produce an identical Authorization header — the tuple is pure sugar.",
        "concise":
            "A tuple is just shorthand: prepare_auth turns it into HTTPBasicAuth, "
            "so a tuple and an explicit HTTPBasicAuth end up calling the same "
            "handler and produce the same header. An AuthBase instance or any "
            "callable of the same shape works too.",
        "wrong_altitude":
            "It runs `if isinstance(auth, tuple) and len(auth) == 2` and then does "
            "`auth = HTTPBasicAuth(*auth)`, then `r = auth(self)`, then "
            "`self.__dict__.update(r.__dict__)` and finally calls "
            "prepare_content_length(self.body). Those are the lines it executes in "
            "prepare_auth.",
        "partial":
            "You can pass a tuple of username and password, or an auth object like "
            "HTTPBasicAuth. Both end up setting the Authorization header on the "
            "request.",
        "wrong_model":
            "The tuple is passed straight through to the server as the credentials "
            "— requests sends the username and password as separate fields in the "
            "request body, and HTTPBasicAuth is a different mechanism that instead "
            "encodes them into a header, so the two produce different requests.",
        "no_attempt":
            "I don't know, I haven't looked at this part of the code.",
        "off_topic":
            "I think the project should really migrate to httpx, and the test suite "
            "would be much faster with pytest-xdist enabled.",
        "missing_prereq":
            "I can't follow this because I don't know what an HTTP header is or "
            "what base64 encoding does, so the idea of credentials being turned "
            "into a header doesn't mean anything to me yet.",
    },

    # ── requests · risk · response.text encoding ─────────────────────────────
    "bbae87b9": {
        "complete":
            "It removes the charset_normalizer fallback. response.encoding is only "
            "set when the server declared a charset in Content-Type; when it did "
            "not, encoding is None and the original code falls back to "
            "apparent_encoding, which detects the real encoding from the bytes. "
            "The proposed version instead assumes UTF-8 in exactly that case, so "
            "any server that returns Latin-1, GB18030 or Shift-JIS without "
            "declaring it now decodes to mojibake — and with errors='replace' it "
            "fails silently rather than raising. You would fix it by setting "
            "response.encoding explicitly before reading .text.",
        "concise":
            "The fallback it deletes is the one that runs when the server didn't "
            "declare a charset. Those responses now get decoded as UTF-8 whatever "
            "they actually are, so non-UTF-8 APIs silently produce corrupted text.",
        "wrong_altitude":
            "The change edits the `text` property in models.py, dropping the branch "
            "that reads self.apparent_encoding and replacing it with `encoding = "
            "self.encoding or 'utf-8'`. It keeps errors='replace' and the empty "
            "content guard, so the diff is three lines in one property.",
        "partial":
            "It hardcodes UTF-8, which won't be right for every response. Some "
            "servers use other encodings and the text would come out wrong.",
        "wrong_model":
            "The problem is performance: charset_normalizer is what makes .text "
            "fast, so removing it means every response now has to be decoded twice "
            "— once to guess and once for real — and large bodies will be much "
            "slower even though the characters come out correct.",
        "no_attempt":
            "No idea, sorry.",
        "off_topic":
            "Response objects should probably be immutable, and I'd add __slots__ "
            "to reduce memory usage across the codebase.",
        "missing_prereq":
            "I can't reason about this because I don't know what a character "
            "encoding is, or what the difference between bytes and a string is in "
            "Python. That's missing for me before this can make sense.",
    },

    # ── requests · architecture · the AuthBase contract ──────────────────────
    "7ecc5fe3": {
        "complete":
            "The handler's whole job is to take a PreparedRequest and return it "
            "with whatever it needs added — normally an Authorization header. That "
            "is all it owns. It does not decide whether auth applies, it does not "
            "build itself from credentials, and it does not reconcile the mutated "
            "request back into the caller: prepare_auth does all three, promoting a "
            "tuple, invoking the handler, then updating __dict__ and recomputing "
            "the content length. Because the contract is only 'callable taking a "
            "PreparedRequest and returning one', any plain function satisfies it — "
            "subclassing AuthBase is a convention, not a requirement.",
        "concise":
            "A handler is just a callable that receives the PreparedRequest, mutates "
            "it and returns it. Everything else — choosing the handler, syncing the "
            "result back, fixing content length — belongs to prepare_auth, which is "
            "why any callable works and AuthBase is only a convention.",
        "wrong_altitude":
            "AuthBase defines __call__ and raises NotImplementedError, and "
            "HTTPBasicAuth overrides __call__ to set r.headers['Authorization'] = "
            "_basic_auth_str(self.username, self.password). It also defines __eq__ "
            "and __ne__ comparing username and password.",
        "partial":
            "The auth handler adds the Authorization header to the request. "
            "requests calls it for you as part of preparing the request.",
        "wrong_model":
            "The handler owns the whole authentication decision: it inspects the "
            "URL and the environment, decides whether credentials are needed at "
            "all, opens the connection so it can read the server's challenge, and "
            "then returns a fresh Request object that replaces the original one.",
        "no_attempt":
            "I don't know.",
        "off_topic":
            "Honestly the naming in this module is inconsistent and I'd rename "
            "several of these classes before doing anything else.",
        "missing_prereq":
            "I don't understand what it means for an object to be callable in "
            "Python, or what __call__ is for, so 'the handler is a callable' isn't "
            "something I can reason about yet.",
    },

    # ── fastapi · architecture · the two layers ──────────────────────────────
    "ed5b84d5": {
        "complete":
            "FastAPI owns the public surface — the decorators you write and their "
            "parameters — and deliberately owns no registration. Every @app.get "
            "hands straight to self.router, an APIRouter created in __init__, and "
            "APIRouter owns the actual registration: storing routes, prepending "
            "prefixes, and merging tags, dependencies and callbacks into each route "
            "it creates. That split is what makes include_router work: because "
            "composition happens inside add_api_route, including a router with a "
            "prefix and tags applies them to every route it holds, which would be "
            "impossible if the app had registered routes directly.",
        "concise":
            "FastAPI is a facade: it owns the decorator API and delegates all "
            "registration to its internal APIRouter, which owns route storage and "
            "prefix/tag merging. That is why include_router can apply a prefix and "
            "tags to a whole set of routes at once.",
        "wrong_altitude":
            "FastAPI.get() has a very long signature with parameters like "
            "response_model, status_code, tags, dependencies, summary, description, "
            "response_description, responses, deprecated, methods, operation_id and "
            "so on, and its body is a single return statement calling "
            "self.router.get() and forwarding each of those parameters.",
        "partial":
            "FastAPI delegates to APIRouter — the app doesn't store routes itself, "
            "the router does. So @app.get ends up calling into the router.",
        "wrong_model":
            "FastAPI and APIRouter are two independent registries kept in sync: the "
            "app registers the route on itself first for speed, then copies it into "
            "the router so that include_router has something to merge later. At "
            "request time FastAPI matches against its own copy and only falls back "
            "to the router's list if nothing matches.",
        "no_attempt":
            "I don't know this codebase well enough to answer.",
        "off_topic":
            "I'd like to know how FastAPI compares to Django REST Framework for "
            "large teams, and whether the async support is worth it.",
        "missing_prereq":
            "I can't answer because I don't know what a decorator is in Python — "
            "I've never used the @ syntax — so I can't reason about what @app.get "
            "does at all.",
    },

    # ── fastapi · flow · the decorator chain ─────────────────────────────────
    "44e85351": {
        "complete":
            "Control goes to APIRouter.get, because FastAPI.get's body is nothing "
            "but a delegation to self.router.get — the app holds no routing logic "
            "of its own. From there APIRouter.get calls api_route, which is where "
            "the HTTP method is turned into a generic registration, and api_route "
            "returns a decorator; when that decorator is applied to your endpoint "
            "it calls add_api_route and returns the function untouched. "
            "add_api_route is the only step that builds an APIRoute and appends it "
            "to self.routes, and it is also where router-level prefix, tags and "
            "dependencies get merged in — which is precisely why the chain does not "
            "shortcut straight there.",
        "concise":
            "To APIRouter.get — FastAPI.get is pure delegation. get names the "
            "method, api_route returns the decorator, and only add_api_route builds "
            "and stores the APIRoute, which is also where router defaults are "
            "merged, so skipping to it would lose that.",
        "wrong_altitude":
            "It returns self.router.get(path, response_model=response_model, "
            "status_code=status_code, tags=tags, dependencies=dependencies, "
            "summary=summary, description=description, ...) — a single return "
            "statement forwarding roughly thirty keyword arguments to the router's "
            "method of the same name.",
        "partial":
            "It goes to the router's get method, which eventually leads to "
            "add_api_route where the route object gets created and stored.",
        "wrong_model":
            "It goes directly to add_api_route — get() is just an alias that fills "
            "in methods=['GET'] and calls it. api_route only exists for the case "
            "where you want to pass several methods at once, so it is not part of "
            "the path a plain @app.get takes.",
        "no_attempt":
            "Not sure.",
        "off_topic":
            "The type hints in this file are extremely verbose; I'd consider "
            "generating them or splitting the signatures into a TypedDict.",
        "missing_prereq":
            "I can't follow this because I don't understand how a decorator that "
            "returns another function works, or what it means for a function to be "
            "'applied' to another one. I need that before this chain means anything.",
    },

    # ── fastapi · synthesis · declaration vs runtime ─────────────────────────
    "1699bba2": {
        "complete":
            "Because the analysis happens when you decorate, not when a request "
            "arrives. APIRoute.__init__ calls get_dependant immediately, which walks "
            "the signature and runs analyze_param on every parameter, so a bad "
            "annotation or a path parameter that matches nothing in the path raises "
            "while the module is being imported — at startup, before any traffic. "
            "The tree is then stored on the route, so request handling only "
            "executes a structure that already exists: the introspection cost is "
            "paid once per route rather than per request. The price is rigidity — "
            "the set of parameters a route accepts is fixed once it is registered, "
            "so changing it means re-registering the route rather than altering "
            "anything at request time.",
        "concise":
            "Because APIRoute.__init__ builds the whole Dependant tree at decoration "
            "time via get_dependant, so signature errors surface at import rather "
            "than on the first request, introspection is paid once instead of per "
            "request, and the accepted parameters are frozen once the route exists.",
        "wrong_altitude":
            "analyze_param checks Annotated metadata first, then the default value's "
            "type, then whether the parameter name appears in path_param_names. "
            "get_dependant loops over the signature and either appends to "
            "dependant.dependencies or adds a ModelField to query_params, "
            "path_params, header_params or cookie_params depending on that result.",
        "partial":
            "Because the dependency tree is built when the route is registered, so "
            "problems in the signature show up then rather than later.",
        "wrong_model":
            "Because FastAPI validates every endpoint signature during app startup "
            "in a separate validation sweep that runs after all modules are "
            "imported — it walks app.routes once the server boots and type-checks "
            "each one, which is also when the dependency tree gets built, so the "
            "decorator itself does no analysis.",
        "no_attempt":
            "I don't know how to answer this one.",
        "off_topic":
            "Does FastAPI support WebSockets well? That's what I'd want to use it "
            "for on my next project.",
        "missing_prereq":
            "I can't answer this because I don't know what a type annotation is in "
            "Python, or what introspection means. Those are missing for me, so "
            "'analyzing the signature' isn't something I can picture.",
    },
}
