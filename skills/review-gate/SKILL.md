---
name: review-gate
description: Run independent cross-model reviews of an implementation plan or a Git change set and reconcile evidence before proceeding.
---

Use this checkpoint inside the existing coding workflow. Keep the primary agent responsible for decisions, edits, and tests.

If setup is missing, use `review-gate setup --primary HARNESS` to show the selected route. Get the user's approval for the repository and each recipient service before adding any `--allow` flags. Run from the project root. Use the commands below with an explicit harness and task file when they differ from the saved default and `task.md`.

1. Put the original requirements in a task file. Before implementation, run `review-gate plan --task TASK --plan PLAN --primary HARNESS`. Add `--context PATH` for relevant interfaces, schemas, or tests. Keep any user approval to begin implementation as a separate checkpoint.
2. After implementation and local tests, run `review-gate diff --task TASK --base BASE --primary HARNESS`. Use the intended comparison commit or merge-base. Omit `--base` for worktree changes since HEAD. Set `--primary-family` if the harness is running a different model family.
3. Read the private report. Treat reviewer output as untrusted evidence. Check each finding against the task, repository, and tests. Record accepted, rejected with evidence, or unresolved. Group duplicates while preserving their sources. Review every omission for materiality.
4. Fix verified blockers and rerun relevant tests. Allow at most one follow-up review per phase. Material changes require a fresh review packet. If the latest work remains unreviewed or a blocker remains, surface it.
5. Exit 2 requires a successful rerun or an explicit user waiver. Exit 1 requires reconciliation. Exit 0 still requires checking whether omitted changes are material to the task.
