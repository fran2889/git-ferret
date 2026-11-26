# CI comparison: git-ferret and flix-monkey

- git-ferret: `/home/fran/Projects/git-ferret` at `7303d73`
- flix-monkey: `/home/fran/Projects/flix-monkey` at `ebbb63c`
- Compared: 2026-11-26
- Scope: `.github/` in both repositories, plus the local tooling each CI job calls
  (`Makefile`, `package.json`, hook and coverage configuration).

Both projects come from the same owner and follow the same house style: Conventional Commits,
release-please with a draft release, SHA-pinned actions, a merge-gate job aggregating the
required checks, grouped Dependabot updates with a cooldown, dependency review at moderate
severity, and a local commit hook for commit messages. The differences below are about depth,
not about philosophy.

## Workflow inventory

| | git-ferret | flix-monkey |
|---|---|---|
| Workflows | 4 | 7 |
| `ci.yml` jobs | lint, type-check, test, coverage, build, audit, merge-gate | type-check, lint-and-audit, doc-links, build, test-unit, test-ui, test-coverage, merge-gate |
| `dependency-review.yml` | yes | yes |
| `dependabot-auto-merge.yml` | yes | yes |
| `release-please.yml` | yes, publishes artifacts | yes, publishes artifacts |
| `nightly.yml` | no | yes (live API integration plus remote doc links) |
| Store publishing | n/a | `publish-to-stores.yml`, `update-store-description.yml` |
| Shared setup action | `.github/actions/setup/action.yml` | none; `setup-node` repeated inline in six jobs |

## What flix-monkey has that git-ferret is missing

1. Workflow linting. flix-monkey runs `raven-actions/actionlint@v2.2.0` (actionlint 1.7.12) in
   `lint-and-audit`. git-ferret's workflow YAML is never linted, so a broken expression or a
   misspelled input is only discovered at run time.

2. Documentation link checking. flix-monkey runs lychee over `*.md`, `docs`, and `.github` on
   every pull request, offline by default so local files and heading anchors are validated
   without network access. The nightly job repeats it with `--offline=false` for remote URLs.
   git-ferret has `README.md`, `CONTRIBUTING.md`, `AGENTS.md`, and `docs/superpowers/` with no
   link or anchor check at all.

3. A scheduled workflow. flix-monkey runs live API integration tests with repository secrets and
   an external-link pass on a cron, plus `workflow_dispatch`. git-ferret has no scheduled job.
   The direct analogue is weaker here (git-ferret has no external API), but a nightly run against
   the newest git release, or against the next Python pre-release, would exercise the portability
   claims the project makes.

4. A GitHub App token for release-please. flix-monkey mints a token from `RELEASE_APP_ID` and
   `RELEASE_APP_PRIVATE_KEY`, so release PRs are created by an app identity and can trigger other
   workflows. git-ferret uses `GITHUB_TOKEN`, which depends on the "Allow GitHub Actions to create
   and approve pull requests" repository setting and does not cause downstream workflow runs.

5. Bug reports as a GitHub issue form (`ISSUE_TEMPLATE/bug-report.yml`) rather than freeform
   markdown. Not CI, but part of the same repository hygiene.

## What git-ferret has that flix-monkey is missing

1. Retryable, idempotent release publishing. git-ferret deliberately does not gate publishing on
   `steps.release.outputs.release_created`. It derives the tag from
   `.release-please-manifest.json`, checks out that tag, uploads with `--clobber`, publishes the
   draft, and supports `workflow_dispatch`. flix-monkey gates every publish step on
   `release_created`, builds from the branch head, has no manual dispatch, no branch guard, and no
   `--clobber`. A build failure after release-please creates the draft therefore cannot be
   finished by re-running the workflow.

2. A fork guard in `pull_request_target` auto-merge. git-ferret fails loudly when the pull
   request head is not this repository, which is the documented guard for that trigger.
   flix-monkey has no such guard.

3. Conservative auto-merge scope. git-ferret auto-approves only `uv` semver-patch updates and
   explicitly leaves GitHub Actions bumps for a person, because merging an action bump executes
   new code in every workflow. flix-monkey approves every semver-patch update, including action
   bumps.

4. `persist-credentials: false` on the dependency-review checkout. git-ferret keeps the token out
   of the worktree. flix-monkey's dependency review leaves the checkout credential in place.

5. A cross-OS test matrix. git-ferret runs pytest on Ubuntu, macOS, and Windows. flix-monkey runs
   everything on Ubuntu only, even though the build pulls in native code (`sharp`) and the suite
   is Node/TypeScript.

6. Coverage in the run summary. git-ferret renders `coverage.xml` into `$GITHUB_STEP_SUMMARY`
   through `scripts/coverage_summary.py`, listing the files below 100 percent. flix-monkey only
   uploads the `coverage` directory as an artifact.

7. An artifact smoke test. git-ferret installs the built wheel in a clean virtual environment and
   runs `--version` and `--help`. flix-monkey builds the extension and runs `web-ext lint`, but
   never loads the packages it built. It also does not upload `dist/` from CI, whereas git-ferret
   uploads its distributions.

8. A composite setup action. One place pins the toolchain and installs the locked environment;
   flix-monkey repeats `setup-node` plus `npm ci` in six jobs.

9. Exact toolchain pinning. git-ferret pins Python 3.14 and uv 0.9.26 in the setup action.
   flix-monkey uses `node-version: '24.x'`, a moving value that can drift from `.nvmrc` (24) and
   from the npm release the lockfile was produced with.

10. One test invocation. flix-monkey's `test-unit` and `test-ui` suites are both re-run inside
    `test-coverage`, so the suite executes three times per run. git-ferret runs it twice (test,
    then coverage). The separate jobs give faster failure isolation, but the duplicated work is
    real.

## Same goals, different implementations

| Concern | git-ferret | flix-monkey |
|---|---|---|
| Toolchain setup | composite action, pinned uv 0.9.26 and Python 3.14 | inline `setup-node`, `24.x`, npm cache |
| Format and lint | `ruff format --check`, `ruff check`, `scripts/check_spdx.py` | Prettier check, ESLint, SPDX through `eslint-plugin-headers` |
| Type checking | pyright strict | `tsc --noEmit` |
| Dependency audit | `pip-audit` against project metadata (`--strict`) and `--local` | `better-npm-audit` at moderate, with notes and expiry required |
| Tests | one pytest run on three operating systems, Python 3.14 only | unit and UI split, Ubuntu only; integration only nightly |
| Coverage gate | `fail_under = 95` in `pyproject.toml`, summary in job output | vitest thresholds 90 for branches, statements, and functions |
| Release credentials | `GITHUB_TOKEN` plus repository settings | GitHub App token |
| Auto-merge | uv patches only, fork guard, action bumps reviewed | every patch including action bumps, no guard |
| Concurrency | `ci-${{ github.ref }}`, cancels every run | `ci-${{ github.workflow }}-${{ github.ref }}`, cancels only pull request runs |
| CI triggers | push to `main`, pull requests to any branch | push to `main`, pull requests to any branch |
| Job timeouts | 10 to 15 minutes, except auto-merge which has none | 5 to 15 minutes on every job |
| Build artifact | wheel plus sdist uploaded, wheel smoke-tested | extension built and linted, not uploaded |

The merge-gate pattern, trigger semantics, dependency-review severity, Dependabot grouping and
cooldown, and SHA-pinned actions are effectively identical. The store-publishing and
description-sync workflows have no git-ferret analogue; they are product-specific.

## Shared gaps

- Neither validates pull request titles or commit messages in CI. Both rely on a local hook
  (`scripts/check_commit_msg.py` and Husky plus commitlint respectively). release-please is driven
  by PR titles, and a squash merge through the web UI bypasses both hooks.
- Neither checks workflows for security issues such as excessive permissions or
  `pull_request_target` misuse. flix-monkey at least gets actionlint's syntax and shellcheck
  coverage.
- Neither signs release artifacts, for example with build provenance or Sigstore.
- Both use `ubuntu-latest` rather than a pinned image.

## Recommendations

### git-ferret

1. Add actionlint to the lint job. It is a small step and catches the class of error the Python
   checks cannot see.
2. Add lychee in offline mode to the lint job and cover `*.md`, `docs`, and `.github`. The project
   carries a lot of prose and internal links.
3. Decide whether a scheduled job is worth it. The most useful version is a nightly run against the
   newest git release or a Python pre-release, to give the stated minimums early warning.
4. Consider a GitHub App token for release-please if release PRs triggering other workflows
   matters. The current flow works, but it depends on a repository setting that is invisible in
   the code.

### flix-monkey

1. Make release publishing retryable: add `workflow_dispatch`, guard on `refs/heads/main`,
   derive the tag from the manifest, check out the tag, and upload with `--clobber`.
2. Add the fork guard to the auto-merge workflow and stop auto-approving `github-actions` patch
   bumps.
3. Set `persist-credentials: false` on the dependency-review checkout.
4. Add at least the unit suite to a three-OS matrix; the packaged extension depends on a native
   module.
5. Print the coverage total in the job summary, not only the artifact.
6. Smoke-test a built package, and upload `dist/` from the build job.
7. Factor the repeated `setup-node` plus `npm ci` into a composite action, pinned to the version
   in `.nvmrc`.
8. Consider removing the duplicated test execution: the coverage job already runs both suites.

### Both

- Validate the PR title in CI, or add a workflow that runs the same commit-message checker on the
  squash-merge title. This is the one rule both projects rely on release-please to enforce and
  neither verifies after the local hook is bypassed.

## Status

Changes landed after this comparison:

- git-ferret added actionlint, lychee (local links on pull requests, remote links nightly), a
  GitHub App token for release-please, and a nightly macOS and Windows test run. The coverage floor
  dropped from 95 to 90 to match flix-monkey.
- Still open in git-ferret: a nightly run against a newer git or Python, and PR-title validation.
- flix-monkey is unchanged.

The comparison above stays as the snapshot at the commits named at the top.

