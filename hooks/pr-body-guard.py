#!/usr/bin/env python3
"""PreToolUse guard: a PR/MR body must follow the pr-description skill's template.

Reads the hook payload on stdin. Exit 2 blocks the call and feeds stderr back to
Claude; exit 0 lets it through. Anything that is not a PR/MR create or edit is
ignored, and unparseable input is let through so a broken payload cannot wedge
every Bash call.
"""
import json
import os
import re
import sys

VISIBLE_WORD_BUDGET = 250
CELL_WORD_BUDGET = 60
REQUIRED_HEADINGS = ("## Why", "## What changed", "## How to verify")
SKILL = "~/.claude/skills/pr-description/SKILL.md"
VOICE_FILE = os.environ.get("PR_BODY_GUARD_VOICE") or os.path.expanduser("~/.claude/skills/pr-description/voice.md")
REPO_VOICE_FILE = os.path.join(".claude", "pr-voice.md")
HEREDOC_GAP = 24  # chars between the body flag and `<<`, room for `"$(cat <<'EOF'`

COMMAND_RE = re.compile(
    r"(?:^|[\s;&|(])(?:rtk\s+)?(?:gh\s+pr\s+(create|edit)|glab\s+mr\s+(create|update))\b"
)
BODY_FLAG_RE = re.compile(r"(?:^|\s)(--body-file|--body|--description|-[bdF])(?:=|\s+)")
# Terminator must open its own line, which is the shell's rule too.
HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)\n\2[ \t]*(?=\n|$)", re.S)
QUOTED_RE = re.compile(r"""\s*(?:"((?:[^"\\]|\\.)*)"|'([^']*)')""", re.S)
TOKEN_RE = re.compile(r"""\s*(?:"([^"]*)"|'([^']*)'|(\S+))""")
HEADING_RE = re.compile(r"^#{2,3}\s+(.+?)\s*$", re.M)
DETAILS_RE = re.compile(r"<details>.*?</details>", re.S | re.I)
ISSUE_LINE_RE = re.compile(
    r"^[ \t]*(?:closes?|closed|fix(?:es|ed)?|resolves?|resolved|refs?|related to)\b[^\n]*#\d+",
    re.I | re.M,
)
BANNED_BLOCK_RE = re.compile(r"```banned[ \t]*\n(.*?)```", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|(?:\s*:?-+:?\s*\|)+\s*$")


def words(text):
    return len(re.findall(r"\S+", text))


def find_command(command):
    """The PR/MR verb match, skipping mentions inside heredoc bodies (documentation, not commands)."""
    bodies = [(m.start(3), m.end(3)) for m in HEREDOC_RE.finditer(command)]
    for m in COMMAND_RE.finditer(command):
        if not any(a <= m.start() < b for a, b in bodies):
            return m
    return None


def extract_body(command, verb):
    """Return (body, problem). Both None when the command carries no body flag."""
    flag = BODY_FLAG_RE.search(command, verb.end())
    if not flag:
        return None, None
    rest = command[flag.end():]

    if flag.group(1) in ("--body-file", "-F"):
        token = TOKEN_RE.match(rest)
        path = next(g for g in token.groups() if g is not None) if token else ""
        if path in ("", "-"):
            return None, "the body comes from stdin, which this guard cannot read; pass a file path to --body-file"
        if "$" in path:
            return None, f"the guard does not expand shell variables in {path}; pass a literal path to --body-file"
        try:
            with open(os.path.expanduser(path), encoding="utf-8") as fh:
                return fh.read(), None
        except OSError as exc:
            return None, f"could not read the body file {path}: {exc.strerror}"

    heredoc = HEREDOC_RE.search(command, flag.end())
    if heredoc and heredoc.start() - flag.end() <= HEREDOC_GAP:
        return heredoc.group(3), None
    quoted = QUOTED_RE.match(rest)
    if quoted:
        return quoted.group(1) if quoted.group(1) is not None else quoted.group(2), None
    token = TOKEN_RE.match(rest)
    return (token.group(3) if token else ""), None


def section_spans(text):
    """Map lower-cased heading text -> (content_start, content_end)."""
    heads = list(HEADING_RE.finditer(text))
    spans = {}
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        spans.setdefault(h.group(1).strip().lower(), (h.end(), end))
    return spans


def check_table(details_html):
    """Return (has_table, oversized_cells) for one <details> block."""
    lines = [l for l in details_html.splitlines() if TABLE_ROW_RE.match(l)]
    sep = next((i for i, l in enumerate(lines) if TABLE_SEPARATOR_RE.match(l)), None)
    if sep is None or sep + 1 >= len(lines):
        return False, []
    oversized = []
    for row in lines[sep + 1:]:
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", row.strip())[1:-1]]
        for cell in cells:
            if words(cell) > CELL_WORD_BUDGET:
                oversized.append(cell[:60] + "…")
    return True, oversized


def banned_phrases(cwd):
    """(phrases, voice file) from the repo's voice file if present, else the global one; ([], None) without either."""
    candidates = ([os.path.join(cwd, REPO_VOICE_FILE)] if cwd else []) + [VOICE_FILE]
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        block = BANNED_BLOCK_RE.search(text)
        phrases = [l.strip() for l in block.group(1).splitlines() if l.strip()] if block else []
        return phrases, path
    return [], None


def banned_hits(body, phrases):
    prose = INLINE_CODE_RE.sub("", body).lower()
    return [p for p in phrases if p.lower() in prose]


def problems_in(body, cwd=None):
    problems = []
    details = DETAILS_RE.findall(body)
    visible = DETAILS_RE.sub("", body)
    visible = "\n".join(l for l in visible.splitlines() if "Generated with" not in l)

    spans = section_spans(visible)
    for heading in REQUIRED_HEADINGS:
        if heading[3:].lower() not in spans:
            problems.append(f"missing heading `{heading}`")

    count = words(visible)
    if count > VISIBLE_WORD_BUDGET:
        problems.append(
            f"visible body is {count} words; the budget is {VISIBLE_WORD_BUDGET} "
            "(the <details> block is not counted, move file-level detail there)"
        )

    why = spans.get("why")
    for m in ISSUE_LINE_RE.finditer(visible):
        if why is None or not (why[0] <= m.start() < why[1]):
            problems.append(
                f"issue reference `{m.group(0).strip()}` must be the last line of `## Why`, not elsewhere"
            )

    if not details:
        problems.append("missing the `<details><summary>Files</summary>` block holding the per-file table")
    else:
        tables = [check_table(d) for d in details]
        if not any(has for has, _ in tables):
            problems.append("the <details> block holds no markdown table (`| File | Change |` plus one row per file or group)")
        for _, oversized in tables:
            for cell in oversized:
                problems.append(f"table cell over {CELL_WORD_BUDGET} words: {cell}")

    phrases, voice = banned_phrases(cwd)
    for hit in banned_hits(body, phrases):
        problems.append(f"banned phrase `{hit}`, see the voice rules in {voice}")
    return problems


def refuse(problems):
    sys.stderr.write("PR body refused by pr-body-guard (see " + SKILL + "):\n")
    for p in problems:
        sys.stderr.write(f"  - {p}\n")
    return 2


def check_file(path):
    with open(path, encoding="utf-8") as fh:
        problems = problems_in(fh.read(), os.getcwd())
    if problems:
        return refuse(problems)
    print("ok")
    return 0


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        return check_file(sys.argv[2])
    try:
        payload = json.load(sys.stdin)
        command = payload["tool_input"]["command"]
        if payload.get("tool_name", "Bash") != "Bash":
            return 0
    except (ValueError, KeyError, TypeError):
        return 0
    if not isinstance(command, str):
        return 0
    verb = find_command(command)
    if verb is None:
        return 0

    body, problem = extract_body(command, verb)
    creating = (verb.group(1) or verb.group(2)) == "create"
    if problem:
        problems = [problem]
    elif body is None:
        if not creating:
            return 0
        problems = ["a PR/MR body is required; write it with the pr-description skill and pass it via --body / --body-file / -d"]
    else:
        problems = problems_in(body, payload.get("cwd"))

    return refuse(problems) if problems else 0


if __name__ == "__main__":
    sys.exit(main())
