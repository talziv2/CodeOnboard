"""
Pytest tests for RetrievalProfile resolution.
Run with: uv run pytest tests/test_profiles.py -v
"""
from backend.pipeline.profiles import PROFILES, get_profile


def test_all_four_goal_types_have_a_profile():
    assert set(PROFILES) == {
        "understand_system",
        "understand_component",
        "contribute_code",
        "debug_issue",
    }


def test_get_profile_returns_matching_profile():
    profile = get_profile("debug_issue")
    assert profile.goal_type == "debug_issue"


def test_unknown_goal_type_falls_back_to_understand_system():
    profile = get_profile("alien_request")
    assert profile.goal_type == "understand_system"


def test_only_understand_system_uses_per_module_strategy():
    assert get_profile("understand_system").retrieval_strategy == "per_module"
    for goal_type in ("understand_component", "contribute_code", "debug_issue"):
        assert get_profile(goal_type).retrieval_strategy == "focused"


def test_debug_and_contribute_retrieve_test_chunks():
    for goal_type in ("debug_issue", "contribute_code"):
        assert "test" in get_profile(goal_type).retrieval_roles
    for goal_type in ("understand_system", "understand_component"):
        assert "test" not in get_profile(goal_type).retrieval_roles


def test_only_debug_and_contribute_decompose_the_query():
    assert get_profile("debug_issue").decompose_query
    assert get_profile("contribute_code").decompose_query
    assert not get_profile("understand_system").decompose_query
    assert not get_profile("understand_component").decompose_query


def test_understand_system_preserves_breadth_others_prune():
    assert get_profile("understand_system").prioritization_mode == "preserve_breadth"
    for goal_type in ("understand_component", "contribute_code", "debug_issue"):
        assert get_profile(goal_type).prioritization_mode == "prune"
