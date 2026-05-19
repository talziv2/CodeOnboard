# RetrievalProfile — per-goal_type configuration for the early pipeline layers.
#
# The four goal_type values need very different context. A RetrievalProfile is
# the single source of truth for those differences: which chunk roles are
# visible to retrieval, which retrieval strategy runs, how big a chunk budget
# the Mentor gets, whether the goal is split into multiple sub-queries, and how
# aggressively the Prioritization Agent prunes the module map.
#
# Indexing always embeds every chunk (tagged with a role); `retrieval_roles`
# only controls what is visible at query time, so one commit-cached collection
# serves all goal types.

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalProfile:
    goal_type: str
    retrieval_roles: frozenset[str]   # chunk roles retrievable at query time
    retrieval_strategy: str           # "per_module" | "focused"
    top_k: int                        # final chunk budget handed to the Mentor
    per_module_top_k: int             # chunks per module — per_module strategy only
    decompose_query: bool             # split goal fields into separate sub-queries
    prioritization_mode: str          # "preserve_breadth" | "prune"
    drop_redundant_classes: bool


PROFILES: dict[str, RetrievalProfile] = {
    # Broad system-level tour: sweep every module shallowly, source code only.
    "understand_system": RetrievalProfile(
        goal_type="understand_system",
        retrieval_roles=frozenset({"source"}),
        retrieval_strategy="per_module",
        top_k=24,
        per_module_top_k=2,
        decompose_query=False,
        prioritization_mode="preserve_breadth",
        drop_redundant_classes=True,
    ),
    # Feature-oriented exploration: one deep focused query on the focus area.
    "understand_component": RetrievalProfile(
        goal_type="understand_component",
        retrieval_roles=frozenset({"source"}),
        retrieval_strategy="focused",
        top_k=18,
        per_module_top_k=2,
        decompose_query=False,
        prioritization_mode="prune",
        drop_redundant_classes=True,
    ),
    # Targeted implementation guidance: tests show extension/usage patterns,
    # so they are retrievable; decompose into goal + contribution context.
    "contribute_code": RetrievalProfile(
        goal_type="contribute_code",
        retrieval_roles=frozenset({"source", "test"}),
        retrieval_strategy="focused",
        top_k=20,
        per_module_top_k=2,
        decompose_query=True,
        prioritization_mode="prune",
        drop_redundant_classes=True,
    ),
    # Focused debugging: tight, deep retrieval; tests reproduce bugs, so they
    # are retrievable; decompose into goal + error + what was already tried.
    "debug_issue": RetrievalProfile(
        goal_type="debug_issue",
        retrieval_roles=frozenset({"source", "test"}),
        retrieval_strategy="focused",
        top_k=16,
        per_module_top_k=2,
        decompose_query=True,
        prioritization_mode="prune",
        drop_redundant_classes=True,
    ),
}

# Unknown goal_type falls back to the broad tour — the safest default.
_DEFAULT_PROFILE = PROFILES["understand_system"]


def get_profile(goal_type: str) -> RetrievalProfile:
    return PROFILES.get(goal_type, _DEFAULT_PROFILE)
