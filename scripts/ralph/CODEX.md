# Ralph Agent Instructions for Codex

You are Codex running one autonomous Ralph iteration on a software project.

## Ralph State Files

- Work from the git repository root.
- Use `scripts/ralph/` as the Ralph directory.
- Read `prd.json` and `progress.txt` from the Ralph directory before editing code.

## Your Task

1. Read `scripts/ralph/prd.json`.
2. Read `scripts/ralph/progress.txt` and check the `Codebase Patterns` section first.
3. Ensure you are on the branch from `prd.json.branchName`. If needed, create it from the default branch.
4. Pick the highest priority user story where `passes` is `false`.
5. Implement only that single user story.
6. Run the smallest relevant quality checks for the changed code, then broader checks if needed.
7. Update nearby `AGENTS.md` or `CLAUDE.md` files if you discover reusable, non-story-specific patterns.
8. If checks pass, commit feature changes with message `feat: [Story ID] - [Story Title]`.
9. Push the branch to origin using `source "$HOME/.config/opencode/github-proxy.env" && git push -u origin HEAD`.
10. Update `scripts/ralph/prd.json` to set that story's `passes` field to `true` only after checks pass.
11. Append progress to `scripts/ralph/progress.txt`.
12. Commit progress updates with message `chore: [Story ID] - update progress` and push again.
13. If more stories still have `passes: false`, continue to the next Ralph iteration automatically unless blocked by a real decision, missing credentials, missing permissions, or an unsafe/ambiguous repo state.

## Autonomy Default

- Do not stop after each completed story just to ask whether to continue.
- Default behavior is to keep going story-by-story until all remaining `passes: false` stories are done or the configured iteration budget is exhausted.
- Ask the user only when a choice has non-obvious consequences or the task is blocked externally.

## Live Logging Requirements

Print concise progress logs to stdout throughout the iteration so external watchers can follow your work in real time.

You MUST print these milestones as you go:
- `STORY: <id> <title>` immediately after selecting the story
- `PLAN: <1-2 sentence approach>` before editing
- `FILES: <comma-separated paths>` after you know which files you will touch
- `EDITING: <path>` each time you start modifying a file
- `TEST: <exact command>` before each verification command
- `TEST RESULT: PASS - <summary>` or `TEST RESULT: FAIL - <summary>` after each verification command
- `GIT: committing feat` before the feature commit
- `GIT: pushing feat` before pushing the feature commit
- `GIT: committing chore` before the progress commit
- `GIT: pushing chore` before pushing the progress commit
- `DIFF: <short git diff --stat style summary>` before your final written summary

## Stop Condition

After finishing one story, check whether all stories now have `passes: true`.

If all stories are complete, reply with exactly:

```text
<promise>COMPLETE</promise>
```

Otherwise end normally so the next iteration can continue.
