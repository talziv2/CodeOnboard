# Feature flags for the gap model and the Tutor.
#
# `CODEONBOARD_GAPS` follows the pattern `CODEONBOARD_CURRICULUM` established:
# default off, the two models coexist rather than one replacing the other
# mid-phase, and a session written under either setting stays loadable under
# both.
#
# `CODEONBOARD_TUTOR` no longer follows it. It is DEFAULT ON, and it is read
# `!= "0"` rather than `== "1"` — see `tutor_enabled` for why the direction of
# the comparison is the whole point.
#
# THE CONTRACT (gap-model.md §3.8), unchanged by any default:
#
#   The flag gates BEHAVIOUR. It never gates STORAGE.
#
# Nothing in `backend/learning/store.py` may call this module. That is what
# makes the round-trip guarantees true by construction rather than by care:
# gap data written under the flag survives a flag-off load, a flag-off re-save,
# and is restored exactly when the flag comes back on — because no code path
# between the graph and the database ever asks whether the flag is set.
#
# `tests/test_gap_model.py::test_the_persistence_path_never_reads_the_flag` and
# `tests/test_tutor_store.py::test_the_persistence_path_never_reads_the_tutor_flag`
# assert this structurally, so the contract cannot rot silently.

import os


def gaps_enabled() -> bool:
    """Is gap-model BEHAVIOUR active? Never consult this when persisting."""
    return os.environ.get("CODEONBOARD_GAPS", "0") == "1"


def tutor_enabled() -> bool:
    """Is the Tutor active? **Never consult this when persisting.**

    ## Default ON, and read as "not explicitly off"

    Unset means ENABLED. The comparison is `!= "0"`, not `== "1"`, and that is
    the whole mechanism: a fresh clone with no `.env` at all gets the complete
    application, and turning the Tutor off is something a deployment has to say
    out loud.

    THE FAILURE THIS PREVENTS. While this defaulted to `0`, the Tutor was
    present in the code, tested, documented and invisible — every new clone ran
    a build with the CHAT control compiled out, and the only symptom was a
    feature that appeared not to exist. Diagnosing that meant knowing to look
    for a flag, in two files, one of which Next inlines at build time. A feature
    nobody can reach without reading the source is not shipped.

    THE COST OF THIS DEFAULT, stated rather than buried. It was `0` on measured
    evidence, not caution: `docs/planning/phases/evidence/tutor/` records 1
    answer leak in 30 adversarial SCAFFOLD prompts against a stated gate of 0,
    and `tutor.md` T8 made a green Eval 1 the condition for defaulting on. That
    gate has NOT been met. The default was changed by decision, and the evidence
    file records it as such. The architecture still removes the cheap leak — a
    `ScaffoldContext` has no field that can hold the answer — so the residual is
    a model reasoning its way to the answer from source it legitimately holds,
    bounded by the ladder's terminus rather than eliminated.

    An unrecognised value enables, because the fallback has to land on the
    default and the default is on. `frontend/lib/flags.ts` makes the same choice
    for the same reason: a typo in an environment variable should not decide a
    product question, and it should certainly not take a feature away silently.

    ## The contract, which the default does not touch

    This gates BEHAVIOUR — the endpoints answer 404, the CHAT control is absent,
    and `retry.py`'s reveal and assisted clauses are inert because nothing can
    set the counters they read. It never gates STORAGE. A conversation written
    flag-on survives a flag-off load and a flag-off re-save, because no code path
    between the graph and the database asks whether the flag is set.

    `tests/test_tutor_store.py::test_the_persistence_path_never_reads_the_tutor_flag`
    asserts that structurally, so the contract cannot rot quietly.
    """
    return os.environ.get("CODEONBOARD_TUTOR", "1") != "0"
