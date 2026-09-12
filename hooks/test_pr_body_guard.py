import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pr-body-guard.py")

GOOD_BODY = """## Why
The tab title never changed, so every bookmark of a documentation product read the same string.
Closes #426.

## What changed
- One composable renders `page · workspace · Narset` from the layouts.
- A document rename moves the tab title without a reload.

## How to verify
- `pnpm test` in `src/frontend`: 582 passed, 11 new.
- E2E not run locally. CI covers the two new title assertions.

<details><summary>Files</summary>

| File | Change |
|---|---|
| `app/composables/useDocumentTitle.ts` | Added the composable that maps routes to their existing nav message keys and reads the document store for entity pages. |
| `app/layouts/default.vue` | Calls the composable once so every route is covered without a per-page convention. |
</details>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
"""


def run_hook(command, tool_name="Bash", raw_stdin=None, cwd=None, voice="/nonexistent/voice.md"):
    payload = raw_stdin if raw_stdin is not None else json.dumps(
        {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": {"command": command}, "cwd": cwd}
    )
    env = dict(os.environ, PR_BODY_GUARD_VOICE=voice)
    proc = subprocess.run([sys.executable, HOOK], input=payload, capture_output=True, text=True, timeout=10, env=env)
    return proc.returncode, proc.stderr


def heredoc(body, flag="--body", cmd='gh pr create --title "t"'):
    return f"{cmd} {flag} \"$(cat <<'EOF'\n{body}\nEOF\n)\""


def without_line(body, needle):
    return "\n".join(l for l in body.splitlines() if needle not in l)


class PassThrough(unittest.TestCase):
    def test_unrelated_command_is_ignored(self):
        self.assertEqual(run_hook("ls -la")[0], 0)

    def test_pr_view_is_ignored(self):
        self.assertEqual(run_hook("gh pr view 12 --json body")[0], 0)

    def test_edit_without_body_is_ignored(self):
        self.assertEqual(run_hook('gh pr edit 5 --title "renamed"')[0], 0)

    def test_other_tools_are_ignored(self):
        self.assertEqual(run_hook("gh pr create --body x", tool_name="Read")[0], 0)

    def test_mention_inside_heredoc_content_is_ignored(self):
        cmd = "cat > doc.md <<'MD'\nRun gh pr " + "create --title t --body-file /tmp/body.md\nMD\necho done"
        self.assertEqual(run_hook(cmd)[0], 0)

    def test_garbage_stdin_is_ignored(self):
        self.assertEqual(run_hook("", raw_stdin="not json")[0], 0)


class BodyExtraction(unittest.TestCase):
    def test_good_heredoc_body_passes(self):
        code, err = run_hook(heredoc(GOOD_BODY))
        self.assertEqual(code, 0, err)

    def test_rtk_prefix_is_still_inspected(self):
        code, _ = run_hook(heredoc("just a sentence", cmd='rtk gh pr create --title "t"'))
        self.assertEqual(code, 2)

    def test_compound_command_is_inspected(self):
        code, _ = run_hook(heredoc("just a sentence", cmd='git push -u origin x && gh pr create --title "t"'))
        self.assertEqual(code, 2)

    def test_pr_edit_body_is_inspected(self):
        code, _ = run_hook(heredoc("just a sentence", cmd="gh pr edit 464"))
        self.assertEqual(code, 2)

    def test_glab_description_flag_is_inspected(self):
        code, _ = run_hook(heredoc("just a sentence", flag="-d", cmd='glab mr create --title "t"'))
        self.assertEqual(code, 2)
        code, _ = run_hook(heredoc("just a sentence", flag="--description", cmd="glab mr update 12"))
        self.assertEqual(code, 2)

    def test_body_file_is_read(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write("just a sentence")
        try:
            code, _ = run_hook(f'gh pr create --title "t" --body-file {f.name}')
            self.assertEqual(code, 2)
            code, _ = run_hook(f'gh pr create --title "t" -F "{f.name}"')
            self.assertEqual(code, 2)
        finally:
            os.unlink(f.name)

    def test_body_file_with_shell_variable_says_so(self):
        code, err = run_hook('gh pr edit 5 --body-file $S/new-$n.md')
        self.assertEqual(code, 2)
        self.assertIn("literal", err)

    def test_good_body_file_passes(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(GOOD_BODY)
        try:
            code, err = run_hook(f'gh pr create --title "t" --body-file {f.name}')
            self.assertEqual(code, 0, err)
        finally:
            os.unlink(f.name)

    def test_plain_quoted_body_is_inspected(self):
        code, _ = run_hook('gh pr create --title "t" --body "just a sentence"')
        self.assertEqual(code, 2)
        code, _ = run_hook("gh pr create --title t --body='just a sentence'")
        self.assertEqual(code, 2)

    def test_create_without_any_body_is_refused(self):
        code, err = run_hook('gh pr create --title "t"')
        self.assertEqual(code, 2)
        self.assertIn("body", err.lower())

    def test_heredoc_after_an_earlier_heredoc_is_the_one_inspected(self):
        cmd = (
            "git commit -m \"$(cat <<'EOF'\nfeat: something\n\nlong commit body\nEOF\n)\" && "
            + heredoc(GOOD_BODY)
        )
        code, err = run_hook(cmd)
        self.assertEqual(code, 0, err)


class Rules(unittest.TestCase):
    def assertBlocked(self, body, fragment):
        code, err = run_hook(heredoc(body))
        self.assertEqual(code, 2, f"expected a block mentioning {fragment!r}")
        self.assertIn(fragment, err)

    def test_missing_why_heading(self):
        self.assertBlocked(GOOD_BODY.replace("## Why", "## Context"), "## Why")

    def test_missing_what_changed_heading(self):
        self.assertBlocked(GOOD_BODY.replace("## What changed", "## Changes"), "## What changed")

    def test_missing_how_to_verify_heading(self):
        self.assertBlocked(GOOD_BODY.replace("## How to verify", "## Test plan"), "## How to verify")

    def test_visible_body_over_250_words(self):
        padding = "\n- " + " ".join(["word"] * 240)
        body = GOOD_BODY.replace("## How to verify", "## What changed (more)" + padding + "\n\n## How to verify")
        self.assertBlocked(body, "250")

    def test_details_block_does_not_count_toward_the_budget(self):
        rows = "\n".join(
            f"| `file{i}.ts` | " + " ".join(["word"] * 50) + " |" for i in range(20)
        )
        body = GOOD_BODY.replace("</details>", rows + "\n</details>")
        code, err = run_hook(heredoc(body))
        self.assertEqual(code, 0, err)

    def test_missing_details_table(self):
        body = GOOD_BODY.replace("| File | Change |", "").replace("|---|---|", "")
        body = "\n".join(l for l in body.splitlines() if not l.startswith("| `"))
        self.assertBlocked(body, "table")

    def test_missing_details_block(self):
        body = GOOD_BODY.split("<details>")[0] + "🤖 Generated with Claude Code"
        self.assertBlocked(body, "details")

    def test_table_cell_over_60_words(self):
        long_cell = " ".join(["word"] * 61)
        body = GOOD_BODY.replace(
            "Calls the composable once so every route is covered without a per-page convention.", long_cell
        )
        self.assertBlocked(body, "60")

    def test_closes_outside_why_is_refused(self):
        body = without_line(GOOD_BODY, "Closes #426.").replace(
            "🤖 Generated", "Closes #426\n\n🤖 Generated"
        )
        self.assertBlocked(body, "Why")

    def test_fixes_keyword_outside_why_is_refused(self):
        body = without_line(GOOD_BODY, "Closes #426.").replace(
            "## How to verify", "Fixes #426\n\n## How to verify"
        )
        self.assertBlocked(body, "Why")

    def test_body_without_any_issue_reference_passes(self):
        code, err = run_hook(heredoc(without_line(GOOD_BODY, "Closes #426.")))
        self.assertEqual(code, 0, err)

    def test_every_problem_is_reported_at_once(self):
        body = GOOD_BODY.replace("## Why", "## Context").replace("## How to verify", "## Test plan")
        code, err = run_hook(heredoc(body))
        self.assertEqual(code, 2)
        self.assertIn("## Why", err)
        self.assertIn("## How to verify", err)


VOICE_MD = """# Voice

Rules here.

```banned
deliberately
which is what
—
```
"""


class Voice(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.voice = os.path.join(self.dir, "voice.md")
        with open(self.voice, "w") as f:
            f.write(VOICE_MD)

    def test_banned_phrase_is_refused_and_named(self):
        body = GOOD_BODY.replace("One composable renders", "One composable deliberately renders")
        code, err = run_hook(heredoc(body), voice=self.voice)
        self.assertEqual(code, 2)
        self.assertIn("deliberately", err)

    def test_banned_check_is_case_insensitive(self):
        body = GOOD_BODY.replace("One composable renders", "Deliberately, one composable renders")
        self.assertEqual(run_hook(heredoc(body), voice=self.voice)[0], 2)

    def test_em_dash_is_refused(self):
        body = GOOD_BODY.replace("without a reload.", "without a reload — always.")
        self.assertEqual(run_hook(heredoc(body), voice=self.voice)[0], 2)

    def test_phrase_inside_inline_code_is_ignored(self):
        body = GOOD_BODY.replace("One composable renders", "One composable (`deliberately_flag`) renders")
        code, err = run_hook(heredoc(body), voice=self.voice)
        self.assertEqual(code, 0, err)

    def test_missing_voice_file_skips_the_phrase_check(self):
        body = GOOD_BODY.replace("One composable renders", "One composable deliberately renders")
        code, err = run_hook(heredoc(body), voice="/nonexistent/voice.md")
        self.assertEqual(code, 0, err)

    def test_repo_voice_file_replaces_the_global_one(self):
        repo = tempfile.mkdtemp()
        os.makedirs(os.path.join(repo, ".claude"))
        with open(os.path.join(repo, ".claude", "pr-voice.md"), "w") as f:
            f.write("# Repo voice\n\n```banned\nbasically\n```\n")
        global_banned = GOOD_BODY.replace("One composable renders", "One composable deliberately renders")
        code, err = run_hook(heredoc(global_banned), cwd=repo, voice=self.voice)
        self.assertEqual(code, 0, err)
        repo_banned = GOOD_BODY.replace("One composable renders", "One composable basically renders")
        code, err = run_hook(heredoc(repo_banned), cwd=repo, voice=self.voice)
        self.assertEqual(code, 2)
        self.assertIn("basically", err)

    def test_refusal_names_the_voice_file(self):
        body = GOOD_BODY.replace("One composable renders", "One composable deliberately renders")
        _, err = run_hook(heredoc(body), voice=self.voice)
        self.assertIn(self.voice, err)


class CheckMode(unittest.TestCase):
    def check(self, body):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(body)
        try:
            env = dict(os.environ, PR_BODY_GUARD_VOICE="/nonexistent/voice.md")
            proc = subprocess.run([sys.executable, HOOK, "--check", f.name], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10, env=env)
            return proc.returncode, proc.stderr
        finally:
            os.unlink(f.name)

    def test_check_passes_a_good_body(self):
        code, err = self.check(GOOD_BODY)
        self.assertEqual(code, 0, err)

    def test_check_reports_problems(self):
        code, err = self.check(GOOD_BODY.replace("## Why", "## Context"))
        self.assertEqual(code, 2)
        self.assertIn("## Why", err)


if __name__ == "__main__":
    unittest.main(verbosity=1)
