# backend/repo — deterministic repository knowledge (Layer A).
#
# This package holds everything the system knows about a repository *without*
# asking a model: the file inventory, the symbol index, and the anchor resolver
# that verifies a (file, symbol, line range) against the real checkout.
#
# It is deliberately free of LLM calls and of any dependency on backend/rag.
# See docs/planning/phases/repo-understanding.md, Stage 0.
