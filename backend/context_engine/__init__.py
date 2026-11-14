# context_engine — Phase 3
# Assembles rich workspace context for LLM prompts.
# Replaces the simple file-injection approach from Phase 2.
#
# Layers (highest → lowest priority):
#   1. Current file content
#   2. Imported local dependencies (auto-resolved)
#   3. Other open tabs
#   4. AST symbol summary
#   5. Error logs (Phase 5)
