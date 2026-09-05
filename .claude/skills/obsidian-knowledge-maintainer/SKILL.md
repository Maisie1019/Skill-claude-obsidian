---
name: obsidian-knowledge-maintainer
description: Maintain a local Obsidian knowledge base by triaging captured material, preserving provenance, deduplicating sources, drafting atomic knowledge notes, linking related pages, recording conflicts, updating indexes, and validating metadata. Use for inbox processing, knowledge gardening, vault audits, and turning trusted notes into traceable outputs; do not use to silently approve AI inferences or resolve human judgment calls.
---

# Obsidian Knowledge Maintainer

Work inside the user's existing vault structure and obey the repository's `CLAUDE.md`. If no local schema exists, read [references/schema.md](references/schema.md) and propose one before broad edits.

## Operating contract

- Default to read-only analysis. Create, move, or modify files only after the user confirms the proposed write scope.
- Preserve raw source material and provenance. Never rewrite or delete evidence content.
- Label facts, external viewpoints, AI inferences, personal judgments, and empirical results distinctly. Never invent a personal judgment for the user.
- Search before creating. Compare title, aliases, canonical URL, authorship, dates, and key concepts.
- Treat similar conclusions from different sources as corroboration, not duplicate source records.
- Treat competing conclusions as a conflict, not a deduplication problem.
- Codex may draft and route work to review. A human decides retention, trust, conflict resolution, and promotion to `verified`.
- Require specific confirmation before deletion, overwrite, bulk rename, directory restructuring, merge cleanup, or conflict resolution.
- Do not store or repeat passwords, tokens, private keys, or customer-sensitive information.

## Choose the mode

- **Triage:** Read [references/workflows.md](references/workflows.md), section “Inbox triage”.
- **Knowledge gardening:** Read the “Gardening” section before reorganizing links, maps, or stale notes.
- **Derived writing:** Read the “Outputs” section before drafting articles or training material.
- **Audit:** Run `scripts/validate_vault.py <vault-path>` and distinguish structural errors from editorial recommendations.

## Required handoff

After authorized changes, update related knowledge pages, meaningful internal links, the narrowest relevant index, and the run log. Report new files, updated files, duplicates or conflicts, pending decisions, skipped actions, and validation results separately.
