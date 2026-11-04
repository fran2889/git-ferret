# IntelliJ shelf detection in local scans

## Intent

`local` already reports stashed work, but work parked in IntelliJ shelves under
`.idea/shelf/` is invisible. Report each shelf so it can be found, without
reading or changing what is inside it.

This is a small change: one new finding type, one filesystem scan per
worktree, and documentation.

## Why now

The original design listed "Cleaning IDE state (IntelliJ shelves and similar)"
as an out-of-scope non-goal. Issue #4 deliberately revisits that decision.
Shelf detection is read-only and narrow, so it does not weaken the original
promise against deletion or cleanup.

## Goals

- Emit exactly one `[SHELF]` finding per non-auto-generated directory under
  `.idea/shelf/`, in every worktree returned by `list_worktrees`.
- Name the shelf and state its modification time in the finding.
- Say that the shelf's contents were not inspected.
- Ignore directories named `Uncommitted_changes_before_*`, which IntelliJ
  creates as churn.
- Emit nothing when `.idea/shelf/` is absent or holds only auto-generated
  directories.
- Document the marker in the README.

## Non-goals

- Unshelving, deleting, or otherwise writing anything.
- Reading or parsing `shelved.patch`, `shelved.xml`, or any shelf contents.
- Inferring which files, branches, or commits a shelf belongs to.
- Detecting non-IntelliJ IDE state.
- Changing any exit code.

## Anti-goals

- Reporting IntelliJ's `Uncommitted_changes_before_*` directories as shelved
  work.
- Wording that implies the shelf was opened, read, or understood.
- Adding a dependency or a git command for a plain filesystem scan.

## Constraints

- Read-only, as with every report path.
- Python 3.14, pyright strict, ruff clean, ASCII prose.
- Tests build real repositories through `tests.helpers`, consistent with the
  rest of the suite.
- The original design document stays as written; it records the decision at
  the time. This document records the reversal.

## Approaches

1. **Inline scan in `analysis/local.py` (chosen).** A small helper called from
   the existing worktree loop. The worktree loop already owns local worktree
   state, and the rule is one directory listing.
2. **Dedicated `git_ferret/shelves.py`.** Better isolation, but one small rule
   does not justify a second module and a second boundary to keep typed.
3. **Generic IDE-artifact scanner.** Future-proof, but speculative. It makes
   the first rule harder to read and adds a design surface nobody asked for.

## Decided how

- Add `Status.SHELF`, rendered as `[SHELF]`, with a unique decorative glyph.
- Add `_report_shelves(worktree, branch, report)` in `analysis/local.py` and
  call it while iterating `list_worktrees`.
- The finding's branch field is the worktree's branch name, or the worktree
  path when detached. This makes a linked worktree's shelf traceable, matching
  how dirty worktrees are named.
- The detail is `IntelliJ shelf "<name>", modified YYYY-MM-DD HH:MM, contents
  not inspected`. The timestamp is the shelf directory's own `st_mtime` in
  local time. A shelf is the directory; inspecting its newest file would
  undermine the promise that contents were not read.
- Sort shelves by name so reports stay deterministic.
- Treat only directories as shelves; files directly under `.idea/shelf/` are
  not shelves. Match the auto-generated prefix case-sensitively, as IntelliJ
  writes it.
- Add a `[SHELF]` row to the README marker table, mention shelves in the
  `local` section, and add shelf reporting to the additional-features list.

## Left to the builder

- Test file layout and fixture details, provided each requirement is covered.
- The exact unique glyph, provided `test_every_status_has_an_emoji` and
  `test_no_two_statuses_share_an_emoji` still pass.
- Whether the timestamp keeps seconds; the documented shape is minute
  precision.
