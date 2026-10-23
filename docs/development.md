# Development

This is the working guide for the repository.

The metadata in `pyproject.toml` and the targets in the `Makefile` are the source of truth. This page
explains what they are for and how the pieces fit together; it does not repeat every flag.

## Setup

You need Python 3.14 or newer, git 2.38 or newer, and uv (recommended) or pip.

```console
$ git clone https://github.com/fran2889/git-ferret
$ cd git-ferret
$ uv sync --all-extras --locked
$ make hooks
$ make check
```

`make install` is the pip route: it installs every optional-dependency group at once. `make sync` is
the uv route. The lockfile is committed, and CI installs with `uv sync --locked`, so a dependency
change has to update `uv.lock` in the same pull request. Dependabot uses the `uv` ecosystem for that
reason.

## Make targets

`make help` lists every target, and the `Makefile` is authoritative. The ones you will use most:

| Target | What it does |
|---|---|
| `make check` | The fast local gate: formatting, lint, SPDX headers, types, tests |
| `make test` | The pytest suite |
| `make typecheck` | pyright in strict mode over the package, tests, and scripts |
| `make coverage` | The suite plus terminal, XML, and HTML coverage reports |
| `make build` | Build the sdist and wheel, then run `twine check` |
| `make audit` | Scan dependencies with `pip-audit` |
| `make ci` | Everything CI runs, including coverage, build, and audit |
| `make hooks` | Point this repository at `.githooks` |
| `make clean` | Remove build artifacts and caches |

Every Python target runs `python -m ...`, so `PYTHON` selects the interpreter. When the environment
is not active:

```console
$ make check PYTHON=.venv/bin/python
```

`uv run --no-sync make check` does the same thing from the locked environment without activating it.

## Git hooks

`make hooks` sets `core.hooksPath` to `.githooks` for this repository only. It does not change your
global git configuration, and it does not install anything outside the checkout.

- `pre-commit` runs `ruff format` and `ruff check --fix` on staged Python files, then re-stages
  them. Only the staged files are touched.
- `pre-push` runs `make typecheck test`, so the two slower gates fail before CI sees them.
- `commit-msg` runs `scripts/check_commit_msg.py`, which enforces the Conventional Commits shape
  and rejects a description that is uppercase, non-imperative, or ends with a period.

The hooks call a configured global `core.hooksPath` first, because setting a local path otherwise
hides the hooks a person already had. The global hook must succeed before the local work runs.

The commit-message checker has unit tests in `tests/test_check_commit_msg.py`. It is code that runs
on every commit, so its edge cases are worth covering.

## Testing philosophy

- The suite builds real git repositories and runs real git commands. Mocking git would test the
  mock, and the behaviour worth protecting here is git's own.
- Fixture builders live in `tests/helpers.py`: `make_repo`, `commit`, `clone_local`, and `run`.
  There is no `conftest.py`; a test calls the builder at the exact path it wants.
- Tests are named for the module they cover, `tests/test_<module>.py`.
- Coverage is measured over `git_ferret/` with a floor of 95 in `pyproject.toml`. Cover a distinct
  path or failure mode rather than duplicating an existing test to move the number.
- The suite runs on Linux, macOS, and Windows. Subprocess output is decoded as UTF-8, paths are
  built with `pathlib`, and the report survives a console that cannot render emoji.
- New scripts under `scripts/` need unit tests. `scripts/check_spdx.py` and
  `scripts/check_commit_msg.py` are both covered.

## Layout

- `git_ferret/cli.py`: typer commands, usage errors, and the run loop.
- `git_ferret/gitcmd.py`: the only module that calls `subprocess`; every git invocation goes here.
- `git_ferret/discovery.py`: finding repositories and worktrees without descending into them.
- `git_ferret/gitops.py`: fetch, base refs, branch state, and the merge test.
- `git_ferret/analysis/`: the verdicts for `local`, `remote`, and `merged`.
- `git_ferret/report.py`: markdown rendering and the TTY-only rich path.
- `tests/`: the suite and its fixture builders.
- `scripts/`: coverage summary, commit-message checker, and SPDX checker.
- `.github/`: CI, release automation, and the issue and pull request templates.

## CI

The merge gate in `.github/workflows/ci.yml` requires lint, type-check, the cross-platform test job,
coverage, build, and audit. release-please is the only release path; do not hand-edit versions or
tags.
