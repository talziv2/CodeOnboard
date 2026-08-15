# Feature flags for the gap model.
#
# `CODEONBOARD_GAPS` follows the pattern `CODEONBOARD_CURRICULUM` established:
# default off, the two models coexist rather than one replacing the other
# mid-phase, and a session written under either setting stays loadable under
# both.
#
# THE CONTRACT (gap-model.md §3.8):
#
#   The flag gates BEHAVIOUR. It never gates STORAGE.
#
# Nothing in `backend/learning/store.py` may call this module. That is what
# makes the round-trip guarantees true by construction rather than by care:
# gap data written under the flag survives a flag-off load, a flag-off re-save,
# and is restored exactly when the flag comes back on — because no code path
# between the graph and the database ever asks whether the flag is set.
#
# `tests/test_gap_model.py::test_the_persistence_path_never_reads_the_flag`
# asserts this structurally, so the contract cannot rot silently.

import os


def gaps_enabled() -> bool:
    """Is gap-model BEHAVIOUR active? Never consult this when persisting."""
    return os.environ.get("CODEONBOARD_GAPS", "0") == "1"
