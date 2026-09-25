# pr-description

A Claude Code skill and guard hook that keep pull request and merge request
descriptions short, uniform and readable. Works with `gh` on GitHub and `glab`
on GitLab.

## What a description looks like

```markdown
## Why
One to three sentences on the problem. The issue reference is the last line.
Closes #123.

## What changed
- Three to six one-line bullets about behaviour.

## How to verify
- What to check by hand: the screen and action, or the request and its response.

## Notes for the reviewer
- Optional, at most three. Only what could look wrong at first glance.

<details><summary>Files</summary>

| File | Change |
|---|---|
| `path/to/file.ts` | One or two sentences in the style of a GitHub Copilot summary item. |
</details>
```

The part above the fold stays under 250 words. Per-file detail goes in the
collapsed table, one row per file or per group of files changed for one reason.

## What is in the repo

| Path | Role |
|---|---|
| `skill/SKILL.md` | The template and how to fill each slot. Loaded by Claude Code when a PR or MR body is being written. |
| `skill/voice.md` | The writing voice, with a `banned` list the guard enforces. |
| `skill/example.md` | A real 22-file PR rewritten in the template. |
| `hooks/pr-body-guard.py` | PreToolUse hook. Refuses `gh pr create|edit` and `glab mr create|update` when the body breaks the template. |
| `hooks/test_pr_body_guard.py` | The hook's tests. Plain `unittest`, no dependencies. |
| `commands/pr.md` | A project command to copy into a repository's `.claude/commands/`. |
| `install.sh` | Links everything into `~/.claude` and registers the hook. |

## Install

Requires `python3` and `git`.

```bash
git clone git@github.com:manawasp/pr-description.git
cd pr-description
./install.sh
```

The installer symlinks `skill/` to `~/.claude/skills/pr-description` and the
hook to `~/.claude/hooks/pr-body-guard.py`, adds the hook to `~/.claude/settings.json`
under `hooks.PreToolUse` with matcher `Bash`, and runs the tests. Anything already
at those paths is moved to `~/.claude/backups/`. A running Claude Code session
loads the hook after `/hooks`; a new session has it from the start.

## Update

Run `git pull` in the clone. The symlinks mean the live skill and hook change
with the checkout, so keep the clone where it was installed from.

## What the guard refuses

| Rule | Limit |
|---|---|
| Visible body, everything outside `<details>` | 250 words |
| Required headings | `## Why`, `## What changed`, `## How to verify` |
| Files table inside `<details>` | present, one row minimum |
| Table cell | 25 words |
| Issue reference (`Closes`, `Fixes`, `Refs` and variants) | last lines of `## Why` only, no text after it |
| Tools in the voice file's `ci-checks` block (`ruff`, `tsc`, `tests pass`…) | none under `## How to verify` |
| Phrases in the voice file's `banned` block | none, outside inline code |
| Body passed by `--body-file` or `-d "$(cat <path>)"` | a literal path, no shell variables, not stdin |

A refusal lists every problem at once. Check a body before shipping it:

```bash
python3 ~/.claude/hooks/pr-body-guard.py --check body.md
```

The guard reads `-b/--body` and `-F/--body-file` for `gh`, `-d/--description`
for `glab`, heredocs and `$(cat <path>)` included. It reads flags as shell
words, so `-d` (draft) on `gh` or a flag inside a quoted title is not taken for
a body, and it ignores the same words inside a heredoc that writes documentation.

## Voice per repository

`skill/voice.md` is the default voice. A repository that wants a different one
commits `.claude/pr-voice.md`. When a PR command runs from that repository the
guard reads that file's `banned` and `ci-checks` blocks instead of the global ones. The file can
also carry the prose rules Claude should follow there.

## Project command

Copy `commands/pr.md` into a repository's `.claude/commands/` to get a `/pr`
command that follows the skill and runs the guard before creating the PR.

## Run the tests

```bash
python3 hooks/test_pr_body_guard.py
```

## Uninstall

```bash
rm ~/.claude/skills/pr-description ~/.claude/hooks/pr-body-guard.py
```

Then remove the entry whose command is `python3 ~/.claude/hooks/pr-body-guard.py`
from `hooks.PreToolUse` in `~/.claude/settings.json`.
