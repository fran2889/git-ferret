# Releasing

Releases are cut by [release-please](https://github.com/googleapis/release-please) from
Conventional Commits. Nobody edits the version by hand.

## The normal flow

1. Merge a pull request to `main` with a Conventional Commit title. `feat:` and `fix:` produce a
   minor or patch release; `feat!:` or a `BREAKING CHANGE:` footer produces a major one.
2. release-please opens or updates a release pull request. It updates the version in
   `pyproject.toml`, `git_ferret/__init__.py`, `.release-please-manifest.json`, and the root package
   entry in `uv.lock`; the last one keeps `uv sync --locked` valid on the release commit.
3. Review and merge that pull request. The release workflow then:
   - creates a draft GitHub release with the tag and no assets;
   - checks out the tag being released, not whatever `main` has become since;
   - builds the sdist and wheel and runs `twine check`;
   - smoke-tests the wheel in a clean uv environment by running `git-ferret --version` and
     `git-ferret --help`;
   - uploads the artifacts to the draft release; and
   - publishes the draft.
4. The README badge and the GitHub releases page now show the new version.

The build runs from the tag, so the artifacts match what the release promises even if another commit
lands on `main` while the workflow is starting.

## Retrying a failed build

Re-run the Release Please workflow from `main` with `workflow_dispatch`. It derives the tag from
`.release-please-manifest.json`, finds the draft release for that tag, rebuilds from the tag, and
uploads with `--clobber`, so a half-finished upload is replaced rather than colliding with itself.
Publishing the same tag twice is prevented by the draft check.

A re-run fixes a transient failure: a network problem, a registry outage, or a runner that died. It
does not fix a defect in the tagged commit. If the build fails because the code at that tag is
wrong, merge a fix and cut the next patch release. If the draft was never published and you need to
reuse the version, delete the draft and the tag, then let release-please recreate the release pull
request; do this only while the tag is unpublished.

## What is deliberately still manual

Publishing to PyPI is not automatic. The workflow exists at
`.github/workflows/publish-pypi.yml`, but it runs only when a person dispatches it with a release
tag. That is the step that stays manual until the project decides to publish.

To enable it:

1. On PyPI, add a trusted publisher for the `git-ferret` project: owner `fran2889`, repository
   `git-ferret`, workflow `publish-pypi.yml`, environment `pypi`.
2. In the GitHub repository, create an environment named `pypi` and protect it with the reviewers
   you want. There is no stored token; the workflow uses OpenID Connect.
3. Dispatch **Publish to PyPI** with the tag of a published GitHub release, for example `v0.2.0`.

The workflow validates the tag format before doing anything else, refuses a draft release, downloads
the artifacts already attached to the GitHub release, and publishes those exact files. It does not
rebuild them, so what reaches PyPI is what was tested on GitHub.

Once PyPI publishing is live, switch the primary install instruction in the README to
`uv tool install git-ferret`; keep the checkout path for contributors.

## Repository settings this relies on

- Actions are allowed to create and approve pull requests, for release-please.
- The `extra-files` entry in `release-please-config.json` matches the root package by its
  distribution name, `git-ferret`. If that name changes, update the JSONPath as well.
- The `pypi` environment exists and is protected before the publish workflow is used.
- The workflow files stay on `main`; release-please reads the branch it is dispatched from, and a
  manual release run from anywhere else is a no-op.
