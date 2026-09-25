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
import shlex
import sys

VISIBLE_WORD_BUDGET = 250
CELL_WORD_BUDGET = 25
REQUIRED_HEADINGS = ("## Why", "## What changed", "## How to verify")
SKILL = "~/.claude/skills/pr-description/SKILL.md"
VOICE_FILE = os.environ.get("PR_BODY_GUARD_VOICE") or os.path.expanduser("~/.claude/skills/pr-description/voice.md")
REPO_VOICE_FILE = os.path.join(".claude", "pr-voice.md")
HEREDOC_GAP = 24  # chars between the body flag and `<<`, room for `"$(cat <<'EOF'`

COMMAND_RE = re.compile(
    r"(?:^|[\s;&|(])(?:rtk\s+)?(?:gh\s+pr\s+(create|edit)|glab\s+mr\s+(create|update))\b"
)
# `-d` is --draft to gh and --description to glab, so each CLI gets its own flags.
GH_BODY_FLAGS = {"--body": "text", "-b": "text", "--body-file": "file", "-F": "file"}
GLAB_BODY_FLAGS = {"--description": "text", "-d": "text"}
SHELL_WORD_RE = re.compile(r"""(?:[^\s"'\\]|\\.|"(?:[^"\\]|\\.)*"|'[^']*')+""", re.S)
BLANK_RE = re.compile(r"(?:[ \t]|\\\n)*")
SEPARATORS = {";", "&", "&&", "||", "|"}
CAT_RE = re.compile(r"\$\(\s*(?:cat\s+|<\s*)(.+?)\s*\)", re.S)
# Terminator must open its own line, which is the shell's rule too.
HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)\n\2[ \t]*(?=\n|$)", re.S)
HEADING_RE = re.compile(r"^##[ \t]+(.+?)\s*$", re.M)
DETAILS_RE = re.compile(r"<details>.*?</details>", re.S | re.I)
ISSUE_LINE_RE = re.compile(
    r"^[ \t]*(?:closes?|closed|fix(?:es|ed)?|resolves?|resolved|refs?|related to)\b[^\n]*#\d+",
    re.I | re.M,
)
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


def shell_words(command, pos):
    """Shell words of the command starting at pos, up to an operator or an unescaped newline."""
    while True:
        pos = BLANK_RE.match(command, pos).end()
        word = SHELL_WORD_RE.match(command, pos)
        if not word or word.group(0) in SEPARATORS:
            return
        yield word
        pos = word.end()


def unquote(word):
    try:
        parts = shlex.split(word)
    except ValueError:
        return word
    return parts[0] if len(parts) == 1 else word


def read_body_file(path):
    if path in ("", "-"):
        return None, "the body comes from stdin, which this guard cannot read; pass a file path"
    if "$" in path:
        return None, f"the guard does not expand shell variables in {path}; pass a literal path"
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as fh:
            return fh.read(), None
    except OSError as exc:
        return None, f"could not read the body file {path}: {exc.strerror}"


def extract_body(command, verb):
    """Return (body, problem). Both None when the command carries no body flag."""
    flags = GH_BODY_FLAGS if verb.group(1) else GLAB_BODY_FLAGS
    words = shell_words(command, verb.end())
    for word in words:
        name, eq, inline = word.group(0).partition("=")
        if name not in flags:
            continue
        if eq:
            value = unquote(inline)
        else:
            value_start = BLANK_RE.match(command, word.end()).end()
            heredoc = HEREDOC_RE.search(command, value_start)
            if heredoc and heredoc.start() - value_start <= HEREDOC_GAP:
                return heredoc.group(3), None
            nxt = next(words, None)
            value = unquote(nxt.group(0)) if nxt else ""
        if flags[name] == "file":
            return read_body_file(value)
        cat = CAT_RE.fullmatch(value)
        if cat:
            return read_body_file(unquote(cat.group(1)))
        return value, None
    return None, None


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


def voice_blocks(cwd):
    """({block name: phrases}, voice file) from the repo's voice file if present, else the global one."""
    candidates = ([os.path.join(cwd, REPO_VOICE_FILE)] if cwd else []) + [VOICE_FILE]
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        blocks = {}
        for name in ("banned", "ci-checks"):
            block = re.search(r"```" + name + r"[ \t]*\n(.*?)```", text, re.S)
            blocks[name] = [l.strip() for l in block.group(1).splitlines() if l.strip()] if block else []
        return blocks, path
    return {}, None


def banned_hits(body, phrases):
    prose = INLINE_CODE_RE.sub("", body).lower()
    return [p for p in phrases if p.lower() in prose]


def ci_check_hits(section, phrases):
    """Phrases found at the start of a word, inline code included, since `ruff` is the usual spelling."""
    return [p for p in phrases if re.search(r"(?<!\w)" + re.escape(p), section, re.I)]


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
    if why:
        lines = [l for l in visible[why[0]:why[1]].splitlines() if l.strip()]
        first = next((i for i, l in enumerate(lines) if ISSUE_LINE_RE.match(l)), None)
        if first is not None and not all(ISSUE_LINE_RE.match(l) for l in lines[first:]):
            problems.append("the issue reference must be the last line of `## Why`, move the text after it above it")

    if not details:
        problems.append("missing the `<details><summary>Files</summary>` block holding the per-file table")
    else:
        tables = [check_table(d) for d in details]
        if not any(has for has, _ in tables):
            problems.append("the <details> block holds no markdown table (`| File | Change |` plus one row per file or group)")
        for _, oversized in tables:
            for cell in oversized:
                problems.append(f"table cell over {CELL_WORD_BUDGET} words: {cell}")

    blocks, voice = voice_blocks(cwd)
    for hit in banned_hits(body, blocks.get("banned", [])):
        problems.append(f"banned phrase `{hit}`, see the voice rules in {voice}")
    verify = spans.get("how to verify")
    if verify:
        for hit in ci_check_hits(visible[verify[0]:verify[1]], blocks.get("ci-checks", [])):
            problems.append(
                f"`{hit}` under `## How to verify`: CI reports it, name the screen or request a reviewer checks by hand"
            )
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
