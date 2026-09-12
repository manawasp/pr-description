---
name: pr-description
description: Use when writing or rewriting the body of a pull request or merge request, before running gh pr create, gh pr edit, glab mr create or glab mr update, on GitHub or GitLab alike.
---

# PR description

## Overview

A PR body is read by a reviewer deciding whether and how to read the diff. It
fits on one screen. Reasoning about *why the code is shaped this way* lives in
code comments, `docs/specs/` and commit messages; per-file detail folds into a
collapsed table so the visible part stays short.

`~/.claude/hooks/pr-body-guard.py` refuses a body that breaks the shape below
and lists every problem at once. Check a body before shipping it:

```bash
python3 ~/.claude/hooks/pr-body-guard.py --check body.md
```

## The body, in order

```markdown
## Why
One to three sentences. The problem or goal as the user or operator meets it.
Closes #123.

## What changed
- Three to six bullets. Each is one sentence about behaviour, not about a file.

## How to verify
- What ran, and its result.
- What did not run, and why.

## Notes for the reviewer
- Optional, at most three. Only what could look wrong at first glance.

<details><summary>Files</summary>

| File | Change |
|---|---|
| `path/to/file.ts` | Past-tense verb first, symbol in backticks, one to three sentences: what it does and what it enables or prevents. |
| `locales/*/settings.json` | Files changed for one reason share a row. |
</details>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

## Filling each slot

| Slot | Contents | Bound |
|---|---|---|
| Why | The problem, then the issue reference as the **last line**, with the keyword and path form the repository uses: `Closes #12` where merging closes the ticket, `Refs group/project#12` where it must not. No issue, no line. | 1 to 3 sentences |
| What changed | Behaviour a reviewer can check. A file name belongs in the table, not here. | 3 to 6 bullets |
| How to verify | One line of outcome per check, not a transcript. Anything skipped is named as skipped, with the reason. Counts only where the repository wants them. | bullets |
| Notes for the reviewer | A decision that looks wrong and is not, a deviation from the issue, a follow-up filed. Omit the section when empty. | up to 3 bullets |
| Files table | One row per file, or per group changed for one reason (generated code, locales, lockfiles, fixtures). The Change cell reads like a GitHub Copilot summary item: `Added a pure builder that…`, `Replaced the per-page call with…`. | up to 60 words per cell |
| Visible part | Everything outside `<details>` | up to 250 words |

## Voice

`voice.md` in this directory sets the register: neutral technical, the tone of
a changelog or a Copilot summary. Read it before writing. Its `banned` block is
enforced by the guard anywhere in the body outside inline code. A repository
replaces the whole file by committing `.claude/pr-voice.md`, which the guard
reads instead when the command runs from that repository.

## Shipping it

Write the body to a file, check it, pass the file by a literal path (the guard
reads it and does not expand shell variables). Read `example.md` and `voice.md` in
this directory once per session before writing the first body.

```bash
python3 ~/.claude/hooks/pr-body-guard.py --check /tmp/body.md
gh pr create --title "type(scope): subject" --body-file /tmp/body.md
glab mr create --title "type(scope): subject" -d "$(cat /tmp/body.md)"
```

## Common mistakes

| Mistake | Fix |
|---|---|
| `## Summary` / `## Changes` / `## Test plan` from the old template | `## Why` / `## What changed` / `## How to verify` |
| `Closes #123` at the bottom of the body | Last line of `## Why` |
| A sentence of rationale after every bullet | Behaviour in the bullet. Rationale in a code comment, the spec or the commit |
| File paths in What changed | Move them to the table |
| A cell that names a symbol and stops | Say what it does and what that enables or prevents |
| No table because one file changed | One row is still a table |
