# Create Pull Request

Open a pull request, or a merge request on GitLab, for the current branch.

1. Confirm the branch is not the default branch. Read `git log <default>..HEAD` and `git diff <default>...HEAD --stat` for the scope.
2. Write the body with the global `pr-description` skill (`~/.claude/skills/pr-description/`) into a scratch file, then `python3 ~/.claude/hooks/pr-body-guard.py --check <file>`.
3. GitHub: `gh pr create --title "type(scope): subject" --body-file <file>`. GitLab: `glab mr create --title "type(scope): subject" -d "$(cat <file>)"`. The guard hook refuses a body that breaks the template.
4. Return the PR or MR URL.
