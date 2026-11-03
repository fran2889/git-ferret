# Fast-forward clean branches that are not checked out

Issue: <https://github.com/fran2889/git-ferret/issues/9>

## Intent

`local --update` only walks worktrees. A clean branch that is behind its upstream but that no
worktree has checked out is reported as behind and can never be brought up to date, even though git
can move the ref directly. This change extends the existing write path so those branches are
fast-forwarded too.

The tool remains read-only without `--update`, and `--update` remains the only write path.

## Goals

- Advance a clean branch that is behind its upstream and is not checked out in any worktree.
- Include an unchecked-out base branch such as `main`; it is a local branch like any other for this
  purpose.
- Leave a diverged branch untouched and report it exactly as today.
- Let every branch checked out in a worktree go through the existing worktree path, exactly once.
- Keep dirty or unreadable worktrees failing closed.
- Make the ref move a genuine fast-forward from the branch's current tip, and refuse rather than
  clobber a ref that moved unexpectedly.
- Cover the ref-only path with tests.

## Non-goals

- No new command, flag, or summary section.
- No update of remote-tracking refs, tags, or branches with no live upstream.
- No change to findings, exit codes, or the existing worktree update behaviour.
- No `git fetch` from the network in this path; the upstream is already a local remote-tracking ref.

## Anti-goals

- Updating a branch that is ahead, diverged, has no upstream, or whose upstream is gone.
- Reaching the same branch through both the worktree path and the ref-only path.
- Bypassing the dirty or unreadable worktree gate by moving a checked-out branch's ref directly.
- Force-moving a ref, which could discard a commit if the branch changed after it was inspected.

## Approaches considered

### Chosen: ancestry check plus compare-and-swap `update-ref`

For each ref-only candidate, read the branch tip and the upstream tip, confirm with
`git merge-base --is-ancestor <tip> <upstream>` that the move is a fast-forward, then run
`git update-ref refs/heads/<branch> <upstream> <tip>`.

The expected-old argument makes the write a compare-and-swap. If the branch moved after it was read,
`update-ref` fails and nothing is written. The command touches only the branch ref, so `FETCH_HEAD`
and the freshness calculation are unaffected. The safety rule is explicit and testable.

### Rejected: `git fetch . <upstream>:<branch>`

This works for the ordinary case and already refuses non-fast-forwards, but it has avoidable
downsides: a short source ref can resolve to an unintended local branch, a missing destination is
recreated instead of refused, and a plain fetch rewrites `FETCH_HEAD`, which makes a stale
repository look freshly fetched unless `--no-write-fetch-head` is passed. It also delegates the
compare-and-swap guarantee to fetch internals rather than stating the expected old tip.

### Rejected: `git branch -f`

Force-moving a ref can discard a commit that arrived between the check and the write. It fails the
issue's "not clobbered" requirement.

## Behaviour

The worktree pass stays first and unchanged. It returns the branches it moved.

The ref-only pass then considers branches from `list_branches` that are not in the set of checked-out
branches and have a configured upstream. The ahead and behind counts are not used as a gate: they are
measured against the short upstream name, which a local branch can shadow. The full remote-tracking
ref and the ancestry test against the freshly read tips are authoritative.

For each candidate:

1. Resolve the branch tip as `refs/heads/<branch>`.
2. Resolve the upstream as a full remote-tracking ref, `refs/remotes/<remote>/<short>`, so a local
   branch that happens to be named like the upstream cannot shadow it.
3. Skip when either ref cannot be read.
4. Skip when `merge-base --is-ancestor` reports that the upstream does not descend from the tip.
5. Run `update-ref` with the tip as the expected old value. Record the branch only when it succeeds.

A checked-out branch is excluded from the ref-only pass even when its worktree is clean, so the
worktree path owns it. A dirty or unreadable checked-out worktree is therefore still skipped by the
worktree pass and cannot be moved through the ref-only pass.

Review added two guards to that exclusion. The ref-only path refuses a candidate whose destination
`refs/heads/<branch>` is symbolic, because `git update-ref` dereferences a symbolic ref and would
move the ref's target (a checked-out `main`, or a remote-tracking ref) rather than the branch
itself. It also revalidates checked-out membership immediately before the write, because the
snapshot taken before the pass can go stale and git offers no atomic "ref is not checked out" lock.

The combined function keeps returning only the branches that moved. Diverged, ahead, no-upstream,
upstream-gone, up-to-date, and dirty cases continue to appear only as findings in the repository's
own section.

The `## fast-forwarded` summary stays one block with one line per moved branch. It does not
distinguish worktree updates from ref-only updates: the repository heading already gives the
location, which resolves the issue's open question.

## Tests

- A clean unchecked-out branch behind its upstream is advanced, and its tip matches the upstream.
- An unchecked-out base branch is advanced too.
- A diverged unchecked-out branch is not moved and is still reported as `[DIVERGED]`.
- A branch checked out in a clean worktree is moved once and appears once in the summary.
- A dirty checked-out branch is not moved by either path.
- A stale expected-old tip is refused by the compare-and-swap.
- Branches with no upstream or a deleted upstream are not moved.
- The summary reports a ref-only update with the same line shape as a worktree update.

## Documentation

- `README.md`: describe that `--update` covers clean unchecked-out branches as well as worktrees,
  and update the command reference line for `--update`.
- `git_ferret/cli.py`: update the `--update` help text and the module docstring that names the write
  path.
- `AGENTS.md`: update the hard constraint so it describes both safe cases.
- Do not rewrite earlier design notes.

## Left to the builder

- Helper names and whether the combined entry point is a rename of `fast_forward_worktrees` or a
  new `fast_forward_branches` wrapper.
- Whether `BranchInfo` gains a full upstream ref field or the ref-only pass derives it from
  `remote` and `upstream`.
- Exact fixture construction for the ref-only tests.
- Wording of the README and help-text changes, within the decisions above.
