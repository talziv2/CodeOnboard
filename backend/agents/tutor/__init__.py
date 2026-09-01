"""The Tutor — conversation as an instrument of the learning engine.

Design: `docs/planning/phases/tutor.md`.

**No module in this package may import `run_grader`, `mutate_graph`,
`adaptation`, or `record_attempt`.** A conversation turn is not evidence about
the learner, and that boundary is structural rather than a matter of care:
`tests/test_tutor_boundary.py` walks this package's ASTs and fails the build if
one of them appears.
"""
