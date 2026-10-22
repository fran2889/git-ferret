# git-ferret project setup roadmap

## Intent

git-ferret's product behaviour is in good shape. What it lacks is the project
scaffolding around it: the issue and pull request surfaces that shape incoming
reports, the contributor and agent documentation that tells someone how to
work here, the local hooks that catch what CI would catch, and the release and
documentation structure that makes the project maintainable over time.

This roadmap closes that gap, using flix-monkey as the reference. It is about
setup, not features. No product behaviour changes except the one small CLI
addition the bug report template requires.

## Deliverables

This task delivers three things, and nothing else:

1. This roadmap document, committed under `docs/superpowers/specs/`.
2. Phase 0, executed immediately: the GitHub templates, the conventions,
   `--version`, the README troubleshooting anchor, repository metadata, and
   the existing issues rewritten into the new shape.
3. One issue per item in Phases 1 to 4, written in the enhancement template.

Phases 1 to 4 are not implemented here. They are the backlog the issues
describe, to be picked up later.

## Goals

- Incoming bugs and feature requests arrive in a shape that can be acted on.
- A new contributor (human or agent) can set up, run the checks, and submit a
  change without reading the source first.
- Local gates catch the same problems CI does, before pushing.
- CI covers dependency review, multiple operating systems, and a locked,
  reproducible install.
- Releases are produced by a documented, repeatable pipeline. Publishing to
  PyPI is planned but not enabled yet.
- Documentation has a structure: a user manual, a troubleshooting guide, a
  development guide, a contributing guide, an agent guide, and a releasing
  runbook.

## Non-goals

- New product features. Code changes are limited to `git-ferret --version`,
  the commit-message checker the hooks run, and the portability fixes the
  cross-platform suite needs: encoding-safe subprocess decoding, path
  handling, and Unicode output.
- Publishing to PyPI now. The workflow is designed in this roadmap and
  implemented later, behind a manual trigger.
- Publishing to any other index or package manager.
- Reopening or renumbering existing issues. Issue numbers and links survive.
- Working around the unmerged `release-readiness` branch. It is ignored for
  now; if it lands first, overlapping items here are dropped rather than
  merged twice.

## Anti-goals

- Copying instructions that already live in a file. Flix-monkey's AGENTS.md
  says "read package.json rather than trusting a copy"; the same discipline
  applies to the Makefile, `pyproject.toml`, and the workflows.
- Ceremony for its own sake. A template line that no reporter can fill in is
  removed, not kept for symmetry with flix-monkey.
- Making the checks slower without making them catch more.

## Constraints

- The tool must stay installable from a checkout with `uv`, and runnable with
  `uvx --from git+https://github.com/fran2889/git-ferret git-ferret`.
- `requires-python = ">=3.14"`, so CI's interpreter matrix stays on one
  version unless that floor changes.
- No Node.js in the repository. Anything flix-monkey does with husky,
  lint-staged, or commitlint is translated to a Python-native equivalent
  rather than bolted on with npm.
- Existing behaviours that the README promises (read-only, exit codes,
  markdown output) must not change.

## Phase 0: GitHub surface (done as part of this roadmap)

This phase is executed immediately, because every issue created afterwards
uses it.

- `.github/ISSUE_TEMPLATE/bug-report.md`, translated from flix-monkey.
- `.github/ISSUE_TEMPLATE/enhancement.md`, translated with CLI-flavoured
  Scope and Requirements sections.
- `.github/ISSUE_TEMPLATE/config.yml` with blank issues disabled and contact
  links for troubleshooting and private vulnerability reporting.
- `.github/PULL_REQUEST_TEMPLATE.md` with Summary and Test Plan.
- `.github/CODEOWNERS`.
- `git-ferret --version`, so the bug template can ask for a version.
- README gains a `## Troubleshooting` heading, so the contact link resolves.
- Repository settings: description, topics, homepage, private vulnerability
  reporting enabled.
- Issues #4 to #9 rewritten into the enhancement template while keeping their
  numbers, intent, and labels.

### Template shapes

**Bug report**

- Description
- Steps to Reproduce (numbered, starting from a fresh shell)
- Expected Behavior
- Actual Behavior
- Environment: git-ferret version, Python version, git version, operating
  system, exact command, and the full report or error output
- Additional Context

**Enhancement request**

- Description: what is missing or wrong today, and why it matters
- Scope: which commands and flags it applies to; optional
- Requirements: checkable acceptance criteria, one per bullet, phrased so each
  can be verified from the CLI
- Open Questions: decisions wanted before work starts

**Pull request**

- Summary: one to three bullets, one behaviour change each
- Test Plan: automated check that covers it, plus a manual command when the
  behaviour is hard to assert
- Optional Breaking Changes and Notes sections, with the same limits as
  flix-monkey

### Conventions adopted from flix-monkey

- Issue titles are imperative, descriptive, and have no trailing period.
- Issue templates apply `bug` and `enhancement`; other labels are deliberate.
- Branches are `type/kebab-case-slug`, with `type` matching the Conventional
  Commits type in the PR title.
- PR titles are squash-merged and parsed by release-please, so they use
  Conventional Commits.
- `gh pr create` does not apply the template; pass a filled copy with
  `--body-file`.
- Do not hand-apply Dependabot's automation labels.
- No `Generated by` or `Co-Authored-By` footers in commit messages.

## Phase 1: Contributor and agent documentation

### `CONTRIBUTING.md`

Translated from flix-monkey:

- Development setup: clone, `uv sync` or `make install`, run `make check`.
- Pull request process: branch name, Conventional Commits, tests required,
  the local command that mirrors CI, and the PR body template.
- Pointer to `AGENTS.md` for AI agents.
- Licensing: contributions are GPL-3.0-only.

### `AGENTS.md`

Translated with Python equivalents:

- What the project is and the stack: Python 3.14, typer, pytest, ruff,
  pyright, uv.
- Commands: install, format, lint, typecheck, test, coverage, build, audit,
  the full pre-PR command.
- Hard constraints: read-only by default; `--update` is the only write path;
  real git repositories in tests, never mocked git; the report is markdown
  with no ANSI escapes; emoji are decorative and the bracketed marker carries
  the meaning; findings never change the exit code.
- Conventions: SPDX headers, docstrings at module and public-function
  boundaries, strict typing, imports, ASCII prose with no em-dashes,
  Conventional Commits, README updated when behaviour is user-facing.
- Testing: where a test belongs, fixtures build real repositories, coverage
  floor of 95, no duplicated coverage.
- GitHub: issue and PR body shape comes from the templates, not from this
  file; merge gate jobs; release-please is the only release path.
- Where to look: `Makefile`, `pyproject.toml`, `git_ferret/`, `tests/`,
  `scripts/`, `.github/`.

### Documentation structure

- `README.md` keeps the user manual: install (including `uv` and `uvx`),
  the three commands, output semantics, configuration, and regular use. It
  gains a table of contents.
- `docs/troubleshooting.md` takes the venv-breakage section plus guidance on
  fetch failures, shallow clones, missing base branches, and Windows console
  encoding. The README links to it and keeps a short summary.
- `docs/development.md` takes the development workflow, Make targets, hooks,
  and the testing philosophy.
- `docs/releasing.md` is written in Phase 4.
- `docs/README.md` indexes the docs and the existing `superpowers/` notes.

The README stays the front door. Splitting it into a docs site is a later
decision; a CLI tool of this size does not need one yet.

## Phase 2: Local quality gates

### Git hooks

Flix-monkey uses husky, lint-staged, and commitlint. The Python translation is
a checked-in `.githooks/` directory plus `make hooks`, which sets
`core.hooksPath` for this repository only:

- `pre-commit`: `ruff format` and `ruff check --fix` on staged Python files,
  then re-stage them. Mirrors lint-staged.
- `pre-push`: `make typecheck test`. Mirrors the type-check gate and catches
  a failing suite before CI does.
- `commit-msg`: `python scripts/check_commit_msg.py "$1"`.

Hooks chain to a configured global `core.hooksPath` before running their own
work, the way flix-monkey's do, because setting `core.hooksPath` otherwise
hides the global hooks.

`scripts/check_commit_msg.py` enforces:

- `type(scope)?: description` with the Conventional Commits types.
- Imperative, lowercase description, no trailing period.
- Merge, revert, fixup, and squash commits pass through.

It gets unit tests, since it is code that runs on every commit.

### SPDX headers

Flix-monkey puts an SPDX header on every `{src,tests}/**/*.ts` file and lets
lint enforce it. git-ferret adopts the same convention:

- Every `git_ferret/**/*.py`, `tests/**/*.py`, and `scripts/**/*.py` file
  starts with the GPL-3.0-only SPDX identifier and the copyright line.
- A check in `make check` enforces the header, so a new file cannot land
  without one. The check is a small tested script if ruff's preview rules do
  not cover it.
- The headers are added in one mechanical commit before the rule is switched
  on, so the enforcement commit starts from a clean tree.

### Locked installs with uv

- Commit a `uv.lock`.
- `make install` keeps working with pip; add `make sync` for
  `uv sync --all-extras --locked`.
- CI installs with `astral-sh/setup-uv`, pinned by commit SHA, and runs
  `uv sync --locked`, so the lockfile is verified on every pull request.
- Dependabot moves to the `uv` ecosystem so its pull requests update the
  lockfile as well as `pyproject.toml`. A `pip` bump that leaves the lockfile
  stale would make `uv sync --locked` fail on every automated PR.
- Document the `uvx` invocation and what it downloads.

## Phase 3: CI hardening

- Run the suite on macOS and Windows. This is a portability pass, not just two
  more jobs: subprocess output must be decoded as UTF-8 rather than with the
  locale encoding, paths must not assume `/`, and the report must survive a
  console that cannot render emoji. Product and test changes go in the same
  pull request as the jobs, and both jobs become required merge checks.
- Add `.github/workflows/dependency-review.yml`, failing at moderate severity,
  as flix-monkey does. It becomes a required check in the repository ruleset,
  not just a red X beside the merge button.
- Add a scheduled compatibility job: weekly, run the suite against the newest
  Python and git available, and open an issue on failure. It is a canary, not
  a merge gate, and never runs on pull requests.
- Keep the existing merge gate and the SHA-pinned actions.
- Verify `uv sync --locked` and `make check` produce the same result, so a
  contributor can use either.

## Phase 4: Release and distribution

### Now

- The release workflow continues to create a draft release, build the sdist
  and wheel, check them with twine, attach them, and publish the draft.
- Add a wheel smoke test that installs the built wheel with `uv` and runs
  `git-ferret --version`.
- `docs/releasing.md` documents the flow: Conventional Commits, the
  release-please PR, the draft release, how to retry a failed build, and the
  manual step that is deliberately not automated yet.
- README gains a release badge and a "releases are cut by release-please"
  line; it already has the latter in Development.

### Later: PyPI

- A `workflow_dispatch` workflow that publishes a chosen release tag using
  PyPI trusted publishing, with a protected `pypi` environment and no stored
  token.
- It downloads the artifacts attached to the GitHub release rather than
  rebuilding them, so what is published is what was tested.
- Guarded by a tag-format check, like flix-monkey's store workflow.
- README install instructions switch the primary path to
  `uv tool install git-ferret` once it is live; the checkout path stays.
- An issue tracks this and stays open until enabled.

## Issue plan

Phase 0 is executed now and is not filed as issues. Every other item gets one
issue, written in the enhancement template, with the phase in the body and a
label where one applies.

| Phase | Issue | Labels |
|---|---|---|
| 1 | docs: add CONTRIBUTING.md | documentation |
| 1 | docs: add AGENTS.md for AI agents | documentation |
| 1 | docs: restructure README and split troubleshooting and development guides | documentation |
| 2 | chore: add Conventional Commits and git hooks | |
| 2 | chore: adopt SPDX headers and enforce them in make check | |
| 2 | build: add uv lockfile and uv-based install path | |
| 3 | ci: run the test suite on macOS and Windows | |
| 3 | ci: add dependency review as a required check | |
| 3 | ci: add weekly compatibility canary | |
| 4 | docs: add releasing runbook | documentation |
| 4 | ci: publish to PyPI with trusted publishing | enhancement |

Dependencies: the hooks issue depends on the commit-message script, which ships
inside it; the README restructure depends on `docs/troubleshooting.md`
existing; the cross-platform issue includes the product fixes, so it is not
just a workflow file; the PyPI issue is blocked until the decision to publish
is made and is not scheduled.

## What is left to the builder

- Whether to use `pre-commit` (the framework) instead of `.githooks/`. The
  roadmap prefers `.githooks/` because it needs no new dependency and can
  chain global hooks, but a builder may argue otherwise.
- The exact wording of the translated templates, provided the sections and
  the guidance comments survive.
- How much of the README moves versus stays, provided the front door still
  answers install, usage, and output semantics.
- The canary's definition of "compatible": current tests only, or a small
  smoke scan over a fixed set of generated repositories.
- Whether the SPDX header check is a ruff preview rule or a small script, and
  the exact copyright line.

