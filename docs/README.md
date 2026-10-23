# Documentation

The [README](../README.md) is the front door and the user manual: install, the three commands,
output semantics, configuration, and regular use. These documents go deeper.

## Guides

- [Contributing](../CONTRIBUTING.md): development setup, branches, commits, and the pull request
  process.
- [AGENTS.md](../AGENTS.md): the same contract for AI agents, with the hard constraints and testing
  rules.
- [Troubleshooting](troubleshooting.md): a broken venv, fetch failures, shallow clones, missing base
  branches, and Windows console encoding.
- [Development](development.md): the local workflow, Make targets, git hooks, testing philosophy,
  and repository layout.

## Design notes

The files under `docs/superpowers/` record decisions at the time they were made. They are history,
not a second manual; do not rewrite them to match later code.

- [Product design](superpowers/specs/2026-10-16-git-ferret-design.md): the original goals,
  commands, analysis rules, and anti-goals.
- [Implementation plan](superpowers/plans/2026-10-16-git-ferret-implementation.md): the plan the
  first implementation followed.
- [Project setup roadmap](superpowers/specs/2026-10-22-git-ferret-project-setup-roadmap-design.md):
  the templates, documentation, hooks, CI, and release work that turned the repository into a
  maintainable project.
