# Voice: neutral technical

The reader is a reviewer who knows the domain and has not opened the diff.
Every sentence states a fact about the change: what it does, what it replaces,
what it prevents. The register is the one a changelog or a GitHub Copilot
summary uses.

## Rules

1. Declarative sentences whose subject is the change, the code or the user.
   "The endpoint returns 404 when the block is missing", not "It turns out
   that blocks can be missing".
2. One idea per sentence, about twenty words, with a verb.
3. Effect first, cause second when the cause matters, joined by "so",
   "because" or "since". One causal link per sentence.
4. No maxims. A sentence that would be equally true of another project is a
   maxim; replace it with the specific fact or delete it.
5. No contrast for effect. Use "X rather than Y" or "X, not Y" only when the
   reader would otherwise assume Y.
6. No metaphor and no personification of code.
7. No evaluative adverbs. Say what happens, not how it should be judged.
8. Name the observable outcome, not the intention. "Fails the build when
   `dist/` contains an inline script", not "so nobody forgets".
9. Past tense in the file table ("Added", "Moved", "Removed"), present tense
   for behaviour in What changed ("The build fails when…").
10. At most one code identifier per sentence outside the table.
11. Plain words: use rather than leverage, before rather than prior to,
    because rather than as. English, whichever language the repository uses.

## Before and after

| Before | After |
|---|---|
| A chord wired into unreachable code is dead code that looks alive. | Wiring the chord would add a shortcut to code no user can reach, so the mode is removed instead. |
| …then `scrollToBlock`, so the smooth scroll has the last word. | Moves the caret before scrolling so the focus call does not override the scroll position. |
| One middleware applies it, so a route added later cannot be the one without headers. | One middleware applies the headers to every route, including routes added later. |
| The unset option is a `'default'` sentinel mapped to null, since reka-ui throws on an empty-string item. | The unset option uses the value `'default'` and is mapped to null on save, because reka-ui rejects an empty-string item. |
| Length follows the diff, not the effort. | Deleted. A maxim carries no fact about this change. |

## Banned

Mechanical tells the guard refuses anywhere in the body, outside inline code.
One entry per line, matched case-insensitively. A repository replaces this
whole file by committing `.claude/pr-voice.md`.

```banned
—
;
deliberately
on purpose
silently
load-bearing
which is what
is what makes
the whole point
not just
in practice
turns out
```
