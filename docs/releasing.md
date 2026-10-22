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

## Publishing to PyPI

Publishing is not automated yet. The release workflow leaves the artifacts on the GitHub release;
putting them on an index is a separate decision, tracked in
[issue #22](https://github.com/fran2889/git-ferret/issues/22). Until that is enabled, install from a
checkout or from git as the README describes.

## Repository settings this relies on

- Actions are allowed to create and approve pull requests, for release-please.
- The `extra-files` entry in `release-please-config.json` matches the root package by its
  distribution name, `git-ferret`. If that name changes, update the JSONPath as well.
- The workflow files stay on `main`; release-please reads the branch it is dispatched from, and a
  manual release run from anywhere else is a no-op.
