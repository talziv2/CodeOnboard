# RetrievalProfile — per-goal_type configuration for the early pipeline layers.
#
# The four goal_type values need very different context. A RetrievalProfile is
# the single source of truth for those differences: which evidence pools (chunk
# roles) are pedagogically appropriate, which retrieval strategy runs, how big
# a chunk budget the Mentor gets, whether the goal is split into multiple
# sub-queries, and how aggressively the Prioritization Agent prunes the map.
#
# Indexing always embeds every chunk (tagged with a role); `retrieval_roles`
# is the goal-aware pool whitelist applied at query time, so one commit-cached
# collection serves all goal types.
#
# The retrieval pipeline (focused strategy) is three layers:
#   1. Pool selection — profile.retrieval_roles decides which pools are
#      pedagogically valid for the goal (a system tour does not query tests).
#   2. Per-pool retrieval + RRF fusion — each pool runs its own query and
#      contributes its top per_pool_k matches; results are fused by rank, not
#      raw similarity, so larger pools cannot drown out smaller ones.
#   3. Diversity cap — no single file may contribute more than max_per_file
#      chunks to the final selection, preventing one large file from flooding
#      top-K (e.g. fastapi/routing.py is 5k lines).

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalProfile:
    goal_type: str
    retrieval_roles: frozenset[str]   # pedagogically valid pools for this goal
    retrieval_strategy: str           # "per_module" | "focused"
    top_k: int                        # final chunk budget handed to the Mentor
    per_module_top_k: int             # chunks per module — per_module strategy only
    per_pool_k: int                   # candidates per pool before RRF fusion
    max_per_file: int                 # diversity cap on the final selection
    decompose_query: bool             # split goal fields into separate sub-queries
    prioritization_mode: str          # "preserve_breadth" | "prune"
    drop_redundant_classes: bool


PROFILES: dict[str, RetrievalProfile] = {
    # Broad system-level tour: sweep every module shallowly, source code only.
    # A library tour is the library showing itself — tests and examples would
    # dilute the architectural narrative.
    "understand_system": RetrievalProfile(
        goal_type="understand_system",
        retrieval_roles=frozenset({"source"}),
        retrieval_strategy="per_module",
        top_k=24,
        per_module_top_k=2,
        per_pool_k=24,
        max_per_file=3,
        decompose_query=False,
        prioritization_mode="preserve_breadth",
        drop_redundant_classes=True,
    ),
    # Feature-oriented exploration: one deep focused query on the focus area.
    # Tests would dilute the abstraction; source only.
    "understand_component": RetrievalProfile(
        goal_type="understand_component",
        retrieval_roles=frozenset({"source"}),
        retrieval_strategy="focused",
        top_k=18,
        per_module_top_k=2,
        per_pool_k=18,
        max_per_file=3,
        decompose_query=False,
        prioritization_mode="prune",
        drop_redundant_classes=True,
    ),
    # Targeted implementation guidance: source = what to extend, tests = how
    # the extension surface is exercised, examples = usage idioms to mirror.
    "contribute_code": RetrievalProfile(
        goal_type="contribute_code",
        retrieval_roles=frozenset({"source", "test", "example"}),
        retrieval_strategy="focused",
        top_k=20,
        per_module_top_k=2,
        per_pool_k=20,
        max_per_file=3,
        decompose_query=True,
        prioritization_mode="prune",
        drop_redundant_classes=True,
    ),
    # Focused debugging: tests reproduce bugs and pin down expected behavior;
    # decompose into goal + error + what was already tried.
    "debug_issue": RetrievalProfile(
        goal_type="debug_issue",
        retrieval_roles=frozenset({"source", "test"}),
        retrieval_strategy="focused",
        top_k=16,
        per_module_top_k=2,
        per_pool_k=16,
        max_per_file=3,
        decompose_query=True,
        prioritization_mode="prune",
        drop_redundant_classes=True,
    ),
    # Architecture tour: like understand_system, but slightly more chunks per
    # module so we have headroom to surface entry points, boundaries, and
    # public APIs. Source-only — the architectural narrative is in the code,
    # not the tests.
    "understand_architecture": RetrievalProfile(
        goal_type="understand_architecture",
        retrieval_roles=frozenset({"source"}),
        retrieval_strategy="per_module",
        top_k=28,
        per_module_top_k=3,
        per_pool_k=28,
        max_per_file=3,
        decompose_query=False,
        prioritization_mode="preserve_breadth",
        drop_redundant_classes=True,
    ),
    # Safe-change planning: similar pool mix to contribute_code (source +
    # test + example), focused retrieval, and decomposition so the
    # change_target / risk_tolerance fields contribute their own embedding
    # rather than dilute the primary goal. Tests are essential here — the
    # user needs to know what guards the area they will touch.
    "improve_existing_system": RetrievalProfile(
        goal_type="improve_existing_system",
        retrieval_roles=frozenset({"source", "test", "example"}),
        retrieval_strategy="focused",
        top_k=22,
        per_module_top_k=2,
        per_pool_k=22,
        max_per_file=3,
        decompose_query=True,
        prioritization_mode="prune",
        drop_redundant_classes=True,
    ),
}

# Unknown goal_type falls back to the broad tour — the safest default.
_DEFAULT_PROFILE = PROFILES["understand_system"]


def get_profile(goal_type: str) -> RetrievalProfile:
    return PROFILES.get(goal_type, _DEFAULT_PROFILE)
