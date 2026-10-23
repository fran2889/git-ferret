# git-ferret

[![CI](https://img.shields.io/github/actions/workflow/status/fran2889/git-ferret/ci.yml?branch=main&label=build)](https://github.com/fran2889/git-ferret/actions/workflows/ci.yml)
[![GitHub release](https://img.shields.io/github/v/release/fran2889/git-ferret)](https://github.com/fran2889/git-ferret/releases)
[![License: GPLv3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

Read-only reporting tool for auditing many local git repositories.

Keep twenty or thirty repositories in one directory and the state rots quietly: branches pushed
long ago and forgotten, upstream branches deleted server-side, work abandoned on a branch from four
months back. Nothing surfaces it. Auditing repo by repo is too slow to do regularly.

git-ferret answers *what is lying around, and what is safe to remove?*, and never removes anything
itself. You delete; it reports and explains.

```console
$ git-ferret merged ~/src
```

## It will not delete anything

The only write this tool performs is a fast-forward, and only when you explicitly ask:

```console
$ git-ferret local ~/src --update
```

Without that flag, every command is read-only. There is no code path that deletes, stashes,
commits, resets, or rewrites anything, so you can audit a directory of real repositories without
touching them.

`--update` fast-forwards worktrees that are clean and behind their upstream, and reports what it
did:

```markdown
## fast-forwarded

- api-server: `feat/new-auth` fast-forwarded
- web-app: `main` fast-forwarded
```

Only what was updated. A worktree that was left alone is not an update, so it does not appear here:
its state is already reported in that repository's own section, where `[DIRTY]`, `[DETACHED]`,
`[NOT PUSHED] no upstream configured` and `[DIVERGED]` sit among the other findings. Nothing is lost
by not repeating it, and the block stays the short record of what this run wrote.

A worktree with uncommitted changes is skipped rather than updated. Git would in fact allow that
when the incoming changes touch different files, as it refuses only when they would overwrite your
edits, but skipping keeps this tool from moving a working tree that has unsaved work.

## Install

Needs Python 3.14 or newer, and `git` on your `PATH`.

### From a checkout

With [uv](https://docs.astral.sh/uv/), one command builds an environment from the committed
lockfile:

```console
$ git clone https://github.com/fran2889/git-ferret
$ cd git-ferret
$ uv sync --locked
$ uv run git-ferret --help
```

`uv sync --locked` installs the runtime dependencies and the package in editable mode, and fails if
`uv.lock` no longer matches `pyproject.toml`. Add `--all-extras`, or run `make sync`, to install
the tools behind `make check` as well.

The pip route works too:

```console
$ cd path/to/git-ferret
$ python3 -m venv .venv
$ source .venv/bin/activate
$ pip install -e .
$ git-ferret --help
```

On Windows the activation is `.venv\Scripts\activate`. `-e` installs in editable mode, so the
command runs the code in your checkout and edits take effect without reinstalling. Drop it for a
plain install, which copies the code into the environment.

To get the test suite and the tools behind `make check` as well, ask for the extras individually or
let the Makefile install all of them at once:

```console
$ pip install -e ".[test,type,lint]"   # just the checks
$ make install                          # every extra, the same set the pipeline uses
```

If `python3 -m venv` fails with `ensurepip is not available`, your Python is missing the venv module,
on Debian and Ubuntu that is `apt install python3.14-venv`, matching your version. The environment has
to be rebuilt afterwards. The uv route above avoids needing it at all.

### Without a checkout

`uvx` runs the package straight from the repository into uv's cache, which is the quickest way to
try it:

```console
$ uvx --from git+https://github.com/fran2889/git-ferret git-ferret --version
```

The first run downloads the package and its dependencies; later runs reuse the cache. `pipx` is the
equivalent if you already use it:

```console
$ pipx install git+https://github.com/fran2889/git-ferret
```

### Without a virtual environment

```console
$ pip install --user -e .
```

Or with pipx, which keeps the tool and its dependencies in their own environment
and puts `git-ferret` on your `PATH` directly:

```console
$ pipx install -e .
```

### Running it without installing

Useful while working on the code, or if you would rather not put it on your
`PATH`:

```console
$ .venv/bin/git-ferret local ~/src          # explicit path
$ source .venv/bin/activate
$ git-ferret local ~/src                    # once activated
```

With uv you need no environment of your own:

```console
$ uv run git-ferret local ~/src                    # editable install in .venv
$ uvx --with-editable . git-ferret local ~/src     # isolated, leaves no .venv
```

Both run the code in your checkout, so an edit takes effect on the next command. The second form keeps
its environment in uv's cache instead of in the project, which is useful when you want the checkout
run but nothing written beside it. `uvx --from .` looks like it does the same thing and does not: it
builds a snapshot of the directory and caches that, so later edits are not picked up.

### Check your install

```console
$ git-ferret --version
git-ferret 0.1.0
$ git-ferret local ~/src --no-fetch | head
```

A run over a directory of real repositories should print a report and exit 0.

## Troubleshooting

Most problems are in the install, not the scan. If a report looks wrong, read the `fetched ...` line
on the repository first: when a repository was read without a successful fetch, the report says so,
and a warning appears once at the top of the run.

### When the venv breaks

```console
$ .venv/bin/git-ferret local ~/src
zsh: bad interpreter: /home/you/src/git-ferret/.venv/bin/python3.11: no such file or directory
```

The environment is intact; its Python is gone. Every script installed into `.venv/bin`
(`git-ferret`, `pytest`, `pip`) starts with the absolute path of the interpreter that created the
environment. Once
that interpreter is uninstalled, upgraded or switched (`pyenv` or `uv` changing versions, a Homebrew
upgrade, the Python macOS ships changing), all of them fail the same way, and activating the
environment does not help.

Rebuild it. Nothing in `.venv` is unique: its contents come from `pyproject.toml`, plus anything you
installed into it by hand, which is worth listing first if you have:

```console
$ .venv/bin/pip list
$ rm -rf .venv
$ python3 -m venv .venv
$ source .venv/bin/activate
$ pip install -e .
```

If the version named in the error is one you no longer want (`python3.11` when you are on
`python3.14`), then `python3 -m venv .venv` builds the same broken environment again. Check what
`python3` resolves to with `python3 --version`, or pin the version: `uv venv --python 3.14`.

## Three questions, three commands

### `local`: what am I sitting on?

Branches checked out locally, plus worktree state: uncommitted changes, detached HEADs, stashes.

```console
$ git-ferret local ~/src
```

```markdown
# git-ferret

## api-server
fetched 2026-10-16 09:41:02 · base: origin/main

- ⬆️ `feat/new-auth` [NOT PUSHED] 1 commits ahead · last commit 4 months ago
- ✓ `feature/done` [OK] last commit 2 weeks ago
- 🔌 `api-server` [UNREACHABLE] fetch failed for origin
- 📦 `api-server` [STASH] stash@{0}: On main: refactor storage layer
```

Repository headings are relative to the directory you scanned, so the root you typed is not repeated
above every one of them. A repository that *is* the root you scanned is named `.`. The line under a
heading belongs to it, which is where that repository's refs came from, and repositories are
separated from each other by a blank line.

### `remote`: which of my remote branches can go?

Remote branches, filtered by author or by name. Useful well beyond "my branches": filter by a
ticket number and you get every branch for that ticket, whoever wrote it.

```console
$ git-ferret remote ~/src --author you@example.com
$ git-ferret remote ~/src --branch ABC-123
```

### `merged`: which remote branches are already in main?

Remote branches whose changes are fully present in the base branch, marked as deletion candidates or
not.

```console
$ git-ferret merged ~/src
```

```markdown
# git-ferret

## web-app
fetched 2026-10-16 09:41:05 · base: origin/main

- 🔀 `origin/feat/new-auth` [NOT MERGED] not merged
- 🗑️ `origin/fix/typo` [SAFE TO DELETE] merged into origin/main, no unpushed local changes
```

`[SAFE TO DELETE]` is the answer this command exists to give, in the marker rather than in a line of
prose you have to read. A branch that is merged but must be kept comes out as
`[UNSAFE TO DELETE]`, never as `[OK]`.

## Why it does not trust commit history

Most tools answer "is this branch merged?" with `git branch --merged`, which only asks whether the
branch is an *ancestor* of main. That is wrong in a way that matters here:

- A **squash-merged** branch is not an ancestor. `git branch --merged` says "not merged" for a branch
  whose changes are sitting in main right now.
- A branch merged and later **reverted** stays an ancestor, so it reads as "merged" when its changes
  are gone.

git-ferret instead asks the behavioural question: *would applying this branch change anything?*
by performing a real three-way merge in memory and comparing the result to the base tree:

```console
$ git merge-tree --write-tree origin/main origin/fix/typo
```

Nothing is checked out, no index or ref is touched, and squash-merged branches are recognised. Git
itself uses tree comparison for exactly this purpose in `git cherry`.

**Known limitation:** a branch that was merged and then reverted still reports as merged. Reverting
does not remove ancestry, so the merge genuinely is a no-op. Every safe-to-delete line states its
reason so you can judge it.

## Safe to delete means two things

A branch is only marked `[SAFE TO DELETE]` when **both** hold:

1. its changes are already in the base branch, **and**
2. no local branch of the same name has unpushed commits.

The second condition is the one that saves you. A remote branch tells you nothing about work sitting
in a local branch of the same name, so a branch that fails it is reported as `[UNSAFE TO DELETE]`
rather than quietly dropped or, worse, marked `[OK]`:

```markdown
- 🚫 `origin/fix/typo` [UNSAFE TO DELETE] merged into origin/main, but local 'fix/typo' has unpushed changes
```

`local` reports the same branch as `[NOT PUSHED]`, so the problem is visible from both directions.

## Stale answers are labelled

Conclusions drawn from old refs are the main way a tool like this could quietly mislead you, so
every repository carries the time of its last successful fetch:

```markdown
## api-server
fetched 2026-10-16 09:41:02 · base: origin/main
```

When any repository was read without a successful fetch this run, a warning appears once at the top.

The base branch is always `origin/main` (or `origin/master`) when that exists, not your local copy.
A local `main` forty commits behind would report live branches as unmerged and send you deleting
live work. When no remote ref exists it falls back to the local one, and says so, which is a weaker
claim, and the output treats it as one.

## Fetching

All three commands fetch (`git fetch --all --prune`) before analysing, so the refs they read are
current. A failed fetch is never fatal: the repository is still analysed and the failure is reported.

Once you have a fresh set of refs, repeat runs are cheap and touch no network:

```console
$ git-ferret merged ~/src --no-fetch
```

A fetch failure never stops the run, and the staleness warning tells you what you are looking at.

## Configuration

`~/.git-ferret.toml`, optional:

```toml
# One identity, or several. They combine with OR: "all of my addresses".
author = ["you@example.com", "personal@gmail.com"]

[whitelist]
# Glob patterns. Suppresses "this branch exists and is fine" for local scans,
# and ignores the branch entirely for remote scans.
patterns = [
  "release/*",
  "user/feature-*",
]
```

A branch matching the whitelist is hidden from `local` **only when it is clean**, so a whitelisted
branch with unpushed commits or a dirty worktree still shows up. For `remote` and `merged` it is
ignored outright.

Identity resolves in this order, first match wins:

1. `--author` on the command line (repeatable, or comma-separated)
2. `author` in this file
3. `git config user.name` / `user.email`, read per repository

## Understanding the output

Output is markdown. It prints nicely in a terminal and stays valid markdown when redirected:

```console
$ git-ferret local ~/src > report.md
```

No ANSI escapes and no tables ever reach the file. Emoji are decorative only: the bracketed
marker always carries the meaning on its own, so a terminal without an emoji font loses nothing.
Git output is decoded as UTF-8 regardless of the console code page, and a glyph the destination
cannot encode is replaced rather than failing the run.

| Marker | Meaning |
|---|---|
| `[OK]` | Nothing to see, or clean |
| `[NOT PUSHED]` | Commits here that are not on the upstream |
| `[NOT MERGED]` | Changes not yet in the base branch |
| `[DIVERGED]` | Has both unpushed commits *and* missing upstream commits |
| `[UPSTREAM DELETED]` | The upstream branch no longer exists on the remote |
| `[CONFLICTS]` | Cannot be applied to the base branch cleanly |
| `[UNKNOWN]` | Cannot be determined: shallow clone, unrelated histories |
| `[DIRTY]` | Uncommitted changes in this worktree |
| `[DETACHED]` | Worktree HEAD is detached |
| `[STASH]` | Stashed work, with its message |
| `[UNREACHABLE]` | No remote configured, or the fetch failed |
| `[SAFE TO DELETE]` | Merged into the base branch, nothing local depends on it: a deletion candidate |
| `[UNSAFE TO DELETE]` | Merged, but a same-named local branch has unpushed work: keep it |
| `[NO BASE]` | No `main` or `master`; nothing to compare branches against |

`[UNKNOWN]` is deliberately distinct from `[CONFLICTS]`. A shallow clone may not have the merge base
locally, and reporting that as a conflict would invent a problem you do not have.

## Using it regularly

Findings alone never change the exit code, so a weekly cron job can alert on *new* findings by
diffing two reports rather than on exit status.

| Exit code | Meaning |
|---|---|
| `0` | The run completed. Findings do **not** change this. |
| `1` | Usage error: unknown command or flag, or a path that is not a directory. |
| `2` | Reserved for a failure that stopped the run before completing. |

A repository that cannot be read is reported and skipped, not fatal.

```console
$ git-ferret local ~/src --no-fetch > ~/reports/$(date +%F).md
$ diff ~/reports/yesterday.md ~/reports/today.md
```

## Development

Install the package with the dev tools, then run the checks. With uv, one command builds the
environment from the lockfile:

```console
$ make sync
$ make hooks
$ make check PYTHON=.venv/bin/python
```

`make sync` is `uv sync --all-extras --locked`. The `PYTHON` override points the Makefile at that
environment without requiring it to be active; once `.venv` is active, plain `make check` finds the
tools. The pip route still works: run `make install` in place of `make sync`, activate the
environment, then run `make hooks` and `make check`.

`make hooks` points this repository at the checked-in `.githooks`. It sets
`core.hooksPath` locally, so commits and pushes run the project's checks and
Conventional Commits validation; it does not change your global git
configuration. A Python file with unstaged changes is refused rather than
staged whole.

`make check` runs formatting, linting, the SPDX header check, type checking, and the test suite. The individual targets:

| Command | What it does |
|---|---|
| `make format` / `make format-check` | Format, or check formatting, with ruff |
| `make lint` / `make lint-fix` | Lint, or lint and apply safe fixes |
| `make check-spdx` | Check that every Python source file names its licence |
| `make typecheck` | Type check with pyright (strict) |
| `make test` | Run the test suite |
| `make coverage` | Run the suite and write HTML and XML coverage reports |
| `make build` | Build the sdist and wheel in `dist/` |
| `make audit` | Scan dependencies for known vulnerabilities with `pip-audit` |
| `make hooks` | Point this repository at the checked-in `.githooks` |
| `make sync` | Install every extra from `uv.lock`, failing if it is stale |
| `make clean` | Remove build artifacts and caches |

`make ci` runs everything the pipeline runs: the checks above plus `coverage`, `build`, and
`audit`. It reaches the network, so it is slower than `make check`.

`make audit` runs `pip-audit` twice, because a project path alone only covers the runtime
dependencies: once over `pyproject.toml`, and once over the installed environment, which in CI
is the `audit` extra's toolchain as well.

`make help` lists everything. Every target runs `python -m ...`, so `PYTHON` selects the
interpreter: `make check PYTHON=.venv/bin/python` when the environment is not active.

CI runs the same targets on every push and pull request: formatting and linting, the SPDX header
check, pyright, the test suite on Python 3.14, coverage, a wheel build with a CLI smoke test, and a
`pip-audit` scan.
Releases are cut by release-please from Conventional Commits.

The test suite builds real git repositories and runs real `git` commands, no mocked git, because
the behaviour worth protecting here is git's own.

## Licence

GPL-3.0-only. See [LICENSE](LICENSE).
