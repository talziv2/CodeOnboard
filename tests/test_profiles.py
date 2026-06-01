"""
Pytest tests for RetrievalProfile resolution.
Run with: uv run pytest tests/test_profiles.py -v
"""
from backend.pipeline.profiles import PROFILES, get_profile


# The six goal types currently supported. Keeping the literal list here (not a
# computed expression over PROFILES) so adding a goal type fails this test and
# forces a thoughtful review of the per-axis assertions below.
ALL_GOAL_TYPES = {
    "understand_system",
    "understand_component",
    "understand_architecture",
    "contribute_code",
    "improve_existing_system",
    "debug_issue",
}


def test_all_goal_types_have_a_profile():
    assert set(PROFILES) == ALL_GOAL_TYPES


def test_get_profile_returns_matching_profile():
    profile = get_profile("debug_issue")
    assert profile.goal_type == "debug_issue"


def test_unknown_goal_type_falls_back_to_understand_system():
    profile = get_profile("alien_request")
    assert profile.goal_type == "understand_system"


def test_per_module_strategy_used_for_breadth_tours():
    # Both system-tour goals sweep every module shallowly.
    for goal_type in ("understand_system", "understand_architecture"):
        assert get_profile(goal_type).retrieval_strategy == "per_module"
    # Focused goals use the three-layer RRF strategy.
    for goal_type in (
        "understand_component",
        "contribute_code",
        "improve_existing_system",
        "debug_issue",
    ):
        assert get_profile(goal_type).retrieval_strategy == "focused"


def test_goal_types_that_retrieve_test_chunks():
    # Tests give behavioral evidence — needed when the user plans to change
    # code (contribute_code, improve_existing_system) or debug it.
    for goal_type in ("debug_issue", "contribute_code", "improve_existing_system"):
        assert "test" in get_profile(goal_type).retrieval_roles
    # Pure understanding tours stay source-only — tests would dilute the
    # architectural narrative.
    for goal_type in (
        "understand_system",
        "understand_component",
        "understand_architecture",
    ):
        assert "test" not in get_profile(goal_type).retrieval_roles


def test_query_decomposition_for_multi_field_goals():
    # These goal types have multiple structured user-supplied fields worth
    # embedding as their own sub-queries.
    for goal_type in ("debug_issue", "contribute_code", "improve_existing_system"):
        assert get_profile(goal_type).decompose_query
    # Single-intent goals stay as one combined query.
    for goal_type in (
        "understand_system",
        "understand_component",
        "understand_architecture",
    ):
        assert not get_profile(goal_type).decompose_query


def test_breadth_tours_preserve_modules_others_prune():
    # Broad tours need most modules kept.
    for goal_type in ("understand_system", "understand_architecture"):
        assert get_profile(goal_type).prioritization_mode == "preserve_breadth"
    # Focused goals can afford to prune.
    for goal_type in (
        "understand_component",
        "contribute_code",
        "improve_existing_system",
        "debug_issue",
    ):
        assert get_profile(goal_type).prioritization_mode == "prune"
