# Fast-forward Unchecked-Out Branches Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `local --update` so a clean branch that is behind its upstream and not checked out is fast-forwarded by compare-and-swap, without touching diverged, checked-out, or protected branches.

**Architecture:** Turn the existing worktree updater into a combined entry point. It runs the worktree pass first, then a ref-only pass over local branches. The ref-only pass resolves each configured upstream to its full remote-tracking ref, verifies ancestry from the branch's current tip, and moves the branch with `update-ref` using that tip as the expected old value.

**Tech Stack:** Python 3.14, typer, git plumbing (`rev-parse`, `merge-base`, `update-ref`), pytest with real repositories, ruff, pyright strict.

**Spec:** `docs/superpowers/specs/2026-11-03-fast-forward-unchecked-branches-design.md`

## Global Constraints

- Python 3.14 or newer; git 2.38 or newer.
- Read-only by default. `local --update` is the only write path, and it may only fast-forward.
- Tests use real git repositories through `tests.helpers`; never mock git.
- Every Python file keeps the SPDX header. Keep pyright strict clean with explicit boundary types.
- Prose is ASCII and avoids em dashes. Use a hyphen or a comma.
- Commits use Conventional Commits, lowercase imperative, no trailing period, no `Co-Authored-By`.
- No new dependencies.
- The coverage floor is 95 in `pyproject.toml`; `make check` is the fast gate.
- Work on branch `feat/fast-forward-unchecked-branches`, already based on `main`.

## Review Focus

- A local branch named like the upstream, such as `origin/feat`, must not shadow the real remote-tracking ref. The ref-only pass must use `refs/remotes/<remote>/<branch>` explicitly.
- A branch that moves between inspection and the write must not be clobbered. The write must use the branch's read tip as the expected old value and accept a refusal.
- A branch checked out in a dirty or unreadable worktree must not be moved by the ref-only pass. Every checked-out branch is excluded from that pass, so the worktree gate cannot be bypassed.
- A diverged or ahead unchecked-out branch must be left alone and keep its existing finding.
- A branch deleted between listing and the write must not be recreated. The compare-and-swap must fail on a missing destination instead of creating it.

---

### Task 1: Ref-only fast-forward path

**Files:**
- Modify: `git_ferret/cli.py:34-35`, `git_ferret/cli.py:154-155`, `git_ferret/cli.py:344-383`
- Modify: `tests/test_update.py`
- Modify: `tests/test_update_reasons.py`

**Interfaces:**
- Consumes: `list_worktrees(repo: Path) -> list[tuple[Path, str | None]]`, `list_branches(repo: Path) -> list[BranchInfo]`, `run_git(repo: Path, *args: str, check: bool = False) -> CompletedProcess[str]`.
- Produces: `fast_forward_branches(repo: Path) -> list[str]`; internal helpers `_fast_forward_worktrees`, `_fast_forward_refs`, `_fast_forward_ref`, `_upstream_ref`, and `_move_ref`.
- `fast_forward_branches` replaces `fast_forward_worktrees` as the name imported by the CLI and tests. It returns only the branches that moved.

- [ ] **Step 1: Replace the old import in both update test modules**

In `tests/test_update.py`, change the CLI import to:

```python
from git_ferret.cli import _move_ref, build_parser, fast_forward_branches
```

In `tests/test_update_reasons.py`, change the CLI import to:

```python
from git_ferret.cli import fast_forward_branches
```

Replace every remaining call to `fast_forward_worktrees` in both files with `fast_forward_branches`. Do not change any assertion yet.

- [ ] **Step 2: Add the ref-only fixture and effect tests to `tests/test_update.py`**

Add `import shutil` to the standard-library imports, then add this fixture near `_behind_clone`:

```python
def _ref_only_behind_clone(tmp_path: Path) -> Path:
    """A clone whose local `feat` branch is behind origin/feat and not checked out."""
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "feat")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "branch", "--track", "feat", "origin/feat")
    run(src, "checkout", "feat")
    (src / "f.txt").write_text("a\nremote\n")
    commit(src, "remote work")
    run(src, "checkout", "main")
    run(clone, "fetch", "--all", "--prune")
    return clone
```

Add these tests after `test_fast_forwards_a_clean_worktree_behind_upstream`:

```python
def test_fast_forwards_an_unchecked_out_branch_behind_upstream(tmp_path: Path):
    clone = _ref_only_behind_clone(tmp_path)
    assert run(clone, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"
    assert run(clone, "rev-list", "--count", "feat..origin/feat").stdout.strip() == "1"

    assert fast_forward_branches(clone) == ["feat"]
    assert run(clone, "rev-parse", "feat").stdout == run(
        clone, "rev-parse", "origin/feat"
    ).stdout


def test_fast_forwards_an_unchecked_out_base_branch(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "checkout", "-b", "work")
    (src / "f.txt").write_text("a\nremote\n")
    commit(src, "remote work")
    run(clone, "fetch", "--all", "--prune")

    assert fast_forward_branches(clone) == ["main"]
    assert run(clone, "rev-parse", "main").stdout == run(
        clone, "rev-parse", "origin/main"
    ).stdout
```

- [ ] **Step 3: Add the safety and roll-up tests to `tests/test_update.py`**

Add these tests below the effect tests:

```python
def test_a_local_branch_named_like_the_upstream_does_not_shadow_it(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "feat")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "branch", "--track", "feat", "origin/feat")
    base = run(clone, "rev-parse", "HEAD").stdout.strip()
    run(clone, "branch", "origin/feat", base)
    run(src, "checkout", "feat")
    (src / "f.txt").write_text("a\nremote\n")
    commit(src, "remote work")
    run(src, "checkout", "main")
    run(clone, "fetch", "--all", "--prune")
    upstream = run(clone, "rev-parse", "refs/remotes/origin/feat").stdout.strip()
    assert upstream != base

    assert fast_forward_branches(clone) == ["feat"]
    assert run(clone, "rev-parse", "feat").stdout.strip() == upstream


def test_a_ref_that_moved_after_it_was_read_is_not_clobbered(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    stale = _head(repo)
    run(repo, "checkout", "-b", "feat")
    (repo / "feat.txt").write_text("feat\n")
    commit(repo, "feat work")
    moved = _head(repo)
    run(repo, "checkout", "main")
    run(repo, "merge", "--ff-only", "feat")
    (repo / "upstream.txt").write_text("upstream\n")
    commit(repo, "upstream work")
    new = _head(repo)

    assert _move_ref(repo, "feat", new, stale) is False
    assert run(repo, "rev-parse", "feat").stdout.strip() == moved


def test_a_missing_branch_is_not_recreated(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    old = _head(repo)
    new = _head(repo)
    run(repo, "branch", "gone")
    run(repo, "branch", "-D", "gone")

    assert _move_ref(repo, "gone", new, old) is False
    assert run(repo, "branch", "--list", "gone").stdout.strip() == ""


def test_an_unreadable_worktree_is_not_ref_updated(tmp_path: Path):
    clone = _ref_only_behind_clone(tmp_path)
    linked = tmp_path / "linked"
    run(clone, "worktree", "add", str(linked), "feat")
    shutil.rmtree(linked)
    before = run(clone, "rev-parse", "feat").stdout.strip()

    assert fast_forward_branches(clone) == []
    assert run(clone, "rev-parse", "feat").stdout.strip() == before


def test_rollup_reports_an_unchecked_out_branch(tmp_path: Path):
    _ref_only_behind_clone(tmp_path)

    res = CliRunner().invoke(build_parser(), ["local", str(tmp_path), "--no-fetch", "--update"])

    assert res.exit_code == 0, res.output
    assert "- clone: `feat` fast-forwarded\n" in res.output
```

- [ ] **Step 4: Add the ref-only refusal tests to `tests/test_update_reasons.py`**

Add this fixture and these tests after `test_diverged_branch_is_reported_as_diverged`:

```python
def _ref_only_diverged_clone(tmp_path: Path) -> Path:
    """A clone whose local `feat` branch is diverged and not checked out."""
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "feat")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "checkout", "-b", "feat", "origin/feat")
    (clone / "local.txt").write_text("local\n")
    commit(clone, "local work")
    run(clone, "checkout", "main")
    run(src, "checkout", "feat")
    (src / "f.txt").write_text("a\nremote\n")
    commit(src, "remote work")
    run(src, "checkout", "main")
    run(clone, "fetch", "--all", "--prune")
    return clone


def test_unchecked_out_diverged_branch_is_reported_as_diverged(tmp_path: Path):
    clone = _ref_only_diverged_clone(tmp_path)
    before = run(clone, "rev-parse", "feat").stdout.strip()

    assert fast_forward_branches(clone) == []
    assert run(clone, "rev-parse", "feat").stdout.strip() == before
    finding = _finding(clone, Status.DIVERGED)
    assert "1 ahead / 1 behind" in finding.detail
    assert "cannot fast-forward" in finding.detail


def test_unchecked_out_ahead_branch_is_not_moved(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "feat")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "checkout", "-b", "feat", "origin/feat")
    (clone / "local.txt").write_text("local\n")
    commit(clone, "local work")
    run(clone, "checkout", "main")
    before = run(clone, "rev-parse", "feat").stdout.strip()

    assert fast_forward_branches(clone) == []
    assert run(clone, "rev-parse", "feat").stdout.strip() == before
    finding = _finding(clone, Status.NOT_PUSHED)
    assert "1 commits ahead" in finding.detail


def test_unchecked_out_branch_with_no_upstream_is_not_moved(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    run(repo, "branch", "solo")
    run(repo, "checkout", "-b", "work")
    before = run(repo, "rev-parse", "solo").stdout.strip()

    assert fast_forward_branches(repo) == []
    assert run(repo, "rev-parse", "solo").stdout.strip() == before


def test_unchecked_out_branch_with_deleted_upstream_is_not_moved(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "feat")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "branch", "--track", "feat", "origin/feat")
    run(src, "branch", "-D", "feat")
    run(clone, "fetch", "--all", "--prune")
    before = run(clone, "rev-parse", "feat").stdout.strip()

    assert fast_forward_branches(clone) == []
    assert run(clone, "rev-parse", "feat").stdout.strip() == before
```

- [ ] **Step 5: Run the new tests and confirm they fail for the missing entry point**

Run: `uv run --no-sync python -m pytest tests/test_update.py tests/test_update_reasons.py -v`

Expected: FAIL at import time because `fast_forward_branches` and `_move_ref` do not exist yet.

- [ ] **Step 6: Implement the combined entry point in `git_ferret/cli.py`**

Add imports:

```python
from git_ferret.gitops import fetch_all, list_branches, resolve_base_ref
from git_ferret.models import BranchInfo, RepoReport
```

Replace the call at `git_ferret/cli.py:155` with:

```python
updated.extend((repo, branch) for branch in fast_forward_branches(repo))
```

Rename `fast_forward_worktrees` to `fast_forward_branches` and restructure it as follows. Keep the existing worktree loop body in `_fast_forward_worktrees` unchanged apart from taking the already-read worktree list:

```python
def fast_forward_branches(repo: Path) -> list[str]:
    """The branches fast-forwarded in *repo*, and nothing else.

    The worktree pass runs first and owns every checked-out branch. The ref-only
    pass then moves branches no worktree has checked out. Only branches that
    moved are returned; every refusal is already a finding in the report.
    """
    worktrees = list_worktrees(repo)
    updated = _fast_forward_worktrees(worktrees)
    checked_out = {branch for _, branch in worktrees if branch is not None}
    updated.extend(_fast_forward_refs(repo, checked_out))
    return updated


def _fast_forward_worktrees(worktrees: list[tuple[Path, str | None]]) -> list[str]:
    updated: list[str] = []
    for worktree, branch in worktrees:
        # Existing body from fast_forward_worktrees, unchanged.
        ...
    return updated
```

Add the ref-only helpers. Use these exact signatures and rules:

```python
def _fast_forward_refs(repo: Path, checked_out: set[str]) -> list[str]:
    """Move unchecked-out branches whose upstream descends from their tip."""


def _fast_forward_ref(repo: Path, branch: BranchInfo) -> bool:
    """Move one unchecked-out branch when the move is a genuine fast-forward."""


def _upstream_ref(branch: BranchInfo) -> str | None:
    """The full remote-tracking ref for *branch*, or None without one."""


def _move_ref(repo: Path, branch: str, new: str, old: str) -> bool:
    """Compare-and-swap refs/heads/<branch> from *old* to *new*."""
```

Implementation rules:

- `_fast_forward_refs` iterates `list_branches(repo)`. Skip a branch whose name is in `checked_out`. Skip a branch with no configured upstream. Append the branch name only when `_fast_forward_ref` returns true.
- Do not gate on `BranchInfo.ahead` or `BranchInfo.behind`. Those counts are measured against the short upstream name, which a local branch can shadow. The full upstream ref plus the ancestry check is authoritative.
- `_upstream_ref` requires `branch.remote` and `branch.upstream`. Return `None` when either is missing or when the remote is `"."`. Remove the `f"{remote}/"` prefix from `upstream`; return `None` if the prefix is absent. Return `f"refs/remotes/{remote}/{short}"`.
- `_fast_forward_ref` resolves `refs/heads/<branch.name>` and the full upstream ref with `git rev-parse --verify --quiet`. Return false if either command fails, or if either output is empty. Return false when the two object names are equal. Run `git merge-base --is-ancestor <old> <new>` and return false unless it exits 0. Then return `_move_ref(repo, branch.name, new, old)`.
- `_move_ref` runs `git update-ref refs/heads/<branch> <new> <old>` and returns whether the exit code is 0. Passing `old` is mandatory: it is the compare-and-swap that refuses a branch that moved or disappeared.

- [ ] **Step 7: Run the update tests and confirm they pass**

Run: `uv run --no-sync python -m pytest tests/test_update.py tests/test_update_reasons.py -v`

Expected: PASS for every test in both modules.

- [ ] **Step 8: Commit the implementation and tests**

```bash
git add git_ferret/cli.py tests/test_update.py tests/test_update_reasons.py
git commit -m "feat(cli): fast-forward unchecked-out branches"
```

### Task 2: Describe the widened update path

**Files:**
- Modify: `README.md:50-67`, `README.md:291`
- Modify: `AGENTS.md:11`, `AGENTS.md:48`
- Modify: `git_ferret/cli.py:10-11`, `git_ferret/cli.py:119-123`

**Interfaces:**
- Consumes: the behaviour and helper names from Task 1.
- Produces: user-facing copy that matches the new write path. No production logic changes.

- [ ] **Step 1: Update the README update section**

Change the sentence that currently reads "`--update` fast-forwards worktrees that are clean and behind their upstream, and reports what it did:" to say that it fast-forwards clean worktrees and clean unchecked-out branches behind their upstream.

After the paragraph about a dirty worktree being skipped, add a paragraph explaining that a branch no worktree has checked out has no working tree to protect; when it is behind its upstream the branch ref is moved by compare-and-swap from its own tip, a branch that moved in the meantime is refused rather than forced, and an ahead or diverged branch is left alone and reported as before.

In the command reference table, change the `--update` row to:

```markdown
| `--update` | `local` | Fast-forward clean worktrees and unchecked-out branches behind their upstream. The only write path. |
```

- [ ] **Step 2: Update the CLI help and module docstring**

Change the `--update` help text in `git_ferret/cli.py` to:

```python
help="Fast-forward clean worktrees and unchecked-out branches. This is the only write this tool performs.",
```

Change the module docstring's write-path sentence to name both writes: `git merge --ff-only` in a clean worktree, and a compare-and-swap `git update-ref` for a clean branch that is not checked out. Keep the surrounding explanation that this is off unless `local --update` asks for it.

- [ ] **Step 3: Update the agent constraints**

In `AGENTS.md`, change the "only write path" sentence near the top and the hard constraint to say `local --update` fast-forwards a clean worktree or a clean unchecked-out branch behind its upstream. Do not weaken the rule that no other write is permitted.

- [ ] **Step 4: Verify the help surface and formatting**

Run: `uv run --no-sync python -m pytest tests/test_cli.py -v`

Expected: PASS, including `test_local_help_lists_update_flag`.

Run: `uv run --no-sync make format-check lint`

Expected: PASS with no formatting or lint changes requested.

- [ ] **Step 5: Commit the documentation**

```bash
git add README.md AGENTS.md git_ferret/cli.py
git commit -m "docs: describe ref-only updates"
```

### Task 3: Verify the branch

**Files:**
- No production files expected to change.

**Interfaces:**
- Consumes: all work from Tasks 1 and 2.
- Produces: a branch that passes the repository's fast gate and coverage floor.

- [ ] **Step 1: Run the fast gate**

Run: `uv run --no-sync make check`

Expected: format-check, lint, check-spdx, typecheck, and the full pytest suite all pass.

- [ ] **Step 2: Run the coverage gate**

Run: `uv run --no-sync make coverage`

Expected: the suite passes and the reported total coverage is at least 95 percent.

- [ ] **Step 3: Fix any failure and re-run**

If a check fails, fix the smallest cause, re-run the failing command, then re-run `uv run --no-sync make check`. Commit the fix with the appropriate Conventional Commit type, for example:

```bash
git add git_ferret tests README.md AGENTS.md
git commit -m "fix(cli): handle ref-only update edge case"
```

- [ ] **Step 4: Confirm the working tree is clean**

Run: `git status --short --branch`

Expected: the branch name is shown with no modified or untracked files.
