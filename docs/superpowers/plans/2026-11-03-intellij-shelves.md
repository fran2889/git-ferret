# IntelliJ Shelf Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Report IntelliJ shelves in `local`, with name and modification time, while ignoring IntelliJ's auto-generated churn.

**Architecture:** Add `Status.SHELF` to the finding model, then scan `.idea/shelf/` inside the existing per-worktree loop in `analyse_local`. The scan is plain `pathlib`, read-only, and filters `Uncommitted_changes_before_*`.

**Tech Stack:** Python 3.14, `pathlib`, pytest, real git repositories through `tests.helpers`.

**Spec:** `docs/superpowers/specs/2026-11-03-intellij-shelves-design.md`

## Global Constraints

- Python 3.14 or newer; the repository runs 3.14.4.
- Read-only. No unshelving, deletion, or other write.
- No new dependency and no git command for the shelf scan.
- pyright strict, ruff clean, ASCII prose.
- Tests build real repositories with `tests.helpers`; do not mock git.
- Conventional Commits, lowercase imperative description, no trailing period.

## Review Focus

- `.idea/shelf` is a regular file, not a directory: no finding, no crash.
- A loose file directly under `.idea/shelf`: ignored, because only directories are shelves.
- Several shelves: one finding each, sorted by name so reports stay diffable.
- A shelf name containing spaces: preserved exactly in the finding.
- A shelf in a detached linked worktree: found, and named by the worktree path because there is no branch.

---

### Task 1: Add the shelf status

**Files:**
- Modify: `git_ferret/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Status.SHELF` whose `MARKER` is `[SHELF]` and whose `EMOJI` is `🗄️`.

- [ ] **Step 1: Write the failing model tests**

In `tests/test_models.py`, add `"SHELF"` to the expected set in
`test_status_values_are_exactly_the_documented_set`, and add this assertion to
`test_status_marker_texts`:

```python
    assert Status.SHELF.MARKER == "[SHELF]"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_models.py -q`

Expected: FAIL because `Status.SHELF` does not exist.

- [ ] **Step 3: Add the status and its glyph**

In `git_ferret/models.py`, add `SHELF = "SHELF"` beside `STASH`, and add
`Status.SHELF: "🗄️"` to `EMOJI_FOR` beside `Status.STASH`. The existing
`test_every_status_has_an_emoji` and `test_no_two_statuses_share_an_emoji`
must keep passing.

- [ ] **Step 4: Run the model tests**

Run: `.venv/bin/python -m pytest tests/test_models.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add git_ferret/models.py tests/test_models.py
git commit -m "feat: add a shelf finding status"
```

---

### Task 2: Detect shelves in every worktree

**Files:**
- Modify: `git_ferret/analysis/local.py`
- Test: `tests/test_local.py`

**Interfaces:**
- Consumes: `Status.SHELF` from Task 1.
- Produces: `_report_shelves(worktree: Path, branch: str | None, report: RepoReport) -> None`,
  called once per worktree from `analyse_local`. It appends one `Finding` per
  non-auto-generated shelf directory.

- [ ] **Step 1: Write the failing shelf tests**

In `tests/test_local.py`, add `import os`, `from datetime import datetime`, and
`Finding` to the existing `git_ferret.models` import. Then add this helper and
the tests below:

```python
def _make_shelf(repo: Path, name: str, modified: float | None = None) -> Path:
    shelf = repo / ".idea" / "shelf" / name
    shelf.mkdir(parents=True)
    (shelf / "shelved.patch").write_text("diff --git a/f.txt b/f.txt\n", encoding="utf-8")
    if modified is not None:
        os.utime(shelf, (modified, modified))
    return shelf


def _shelf_findings(rep: RepoReport) -> list[Finding]:
    return [f for f in rep.findings if f.status is Status.SHELF]


def test_reports_a_shelf_by_name_and_mtime(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    stamp = 1_700_000_000
    _make_shelf(repo, "my-shelf", modified=stamp)
    expected = datetime.fromtimestamp(stamp).strftime("%Y-%m-%d %H:%M")
    shelves = _shelf_findings(_report(repo))
    assert len(shelves) == 1
    assert 'IntelliJ shelf "my-shelf"' in shelves[0].detail
    assert f"modified {expected}" in shelves[0].detail


def test_shelf_finding_says_contents_were_not_inspected(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    _make_shelf(repo, "my-shelf")
    assert "contents not inspected" in _shelf_findings(_report(repo))[0].detail


def test_ignores_auto_generated_shelves(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    _make_shelf(repo, "Uncommitted_changes_before_Checkout_at_2026-11-03")
    assert _shelf_findings(_report(repo)) == []


def test_absent_shelf_directory_reports_nothing(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    assert _shelf_findings(_report(repo)) == []


def test_reports_a_shelf_in_a_linked_worktree(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    linked = tmp_path / "linked"
    run(repo, "worktree", "add", "-b", "linked-branch", str(linked))
    _make_shelf(linked, "linked-shelf")
    shelves = _shelf_findings(_report(repo))
    assert len(shelves) == 1
    assert 'IntelliJ shelf "linked-shelf"' in shelves[0].detail
    assert shelves[0].branch == "linked-branch"


def test_reports_one_finding_per_shelf_in_name_order(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    _make_shelf(repo, "zebra")
    _make_shelf(repo, "alpha")
    names = [f.detail.split('"')[1] for f in _shelf_findings(_report(repo))]
    assert names == ["alpha", "zebra"]


def test_a_loose_file_under_the_shelf_directory_is_not_a_shelf(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    shelf_root = repo / ".idea" / "shelf"
    shelf_root.mkdir(parents=True)
    (shelf_root / "shelved.patch").write_text("diff --git a/f.txt b/f.txt\n", encoding="utf-8")
    assert _shelf_findings(_report(repo)) == []


def test_a_shelf_path_that_is_a_file_reports_nothing(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    idea = repo / ".idea"
    idea.mkdir()
    (idea / "shelf").write_text("not a directory\n", encoding="utf-8")
    assert _shelf_findings(_report(repo)) == []


def test_a_shelf_name_with_spaces_is_preserved(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    _make_shelf(repo, "before refactor")
    assert 'IntelliJ shelf "before refactor"' in _shelf_findings(_report(repo))[0].detail


def test_reports_a_shelf_in_a_detached_linked_worktree(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    linked = tmp_path / "detached"
    run(repo, "worktree", "add", "--detach", str(linked))
    _make_shelf(linked, "detached-shelf")
    shelves = _shelf_findings(_report(repo))
    assert len(shelves) == 1
    assert 'IntelliJ shelf "detached-shelf"' in shelves[0].detail
    assert shelves[0].branch == str(linked)
```

- [ ] **Step 2: Run the shelf tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_local.py -q -k "shelf"`

Expected: FAIL because no shelf finding is produced.

- [ ] **Step 3: Implement the shelf scan**

In `git_ferret/analysis/local.py`, add these constants near `NO_BASE_REASON`:

```python
SHELF_ROOT = Path(".idea") / "shelf"
AUTO_SHELF_PREFIX = "Uncommitted_changes_before_"
SHELF_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"
```

Add `from datetime import datetime` with the imports. Then add:

```python
def _report_shelves(worktree: Path, branch: str | None, report: RepoReport) -> None:
    """Report IntelliJ shelves: work parked where no git command can see it."""
    try:
        entries = sorted((worktree / SHELF_ROOT).iterdir(), key=lambda entry: entry.name)
    except OSError:
        # No shelf directory, or one that cannot be read. Neither is a shelf.
        return
    for shelf in entries:
        if not shelf.is_dir() or shelf.name.startswith(AUTO_SHELF_PREFIX):
            continue
        try:
            modified = datetime.fromtimestamp(shelf.stat().st_mtime).strftime(
                SHELF_TIMESTAMP_FORMAT
            )
        except OSError:
            modified = "unknown"
        report.findings.append(
            Finding(
                branch=branch or str(worktree),
                status=Status.SHELF,
                detail=f'IntelliJ shelf "{shelf.name}", modified {modified}, '
                "contents not inspected",
            )
        )
```

Call `_report_shelves(path, branch_name, report)` once per worktree inside
`analyse_local`, immediately after the existing `if dirty:` block.

- [ ] **Step 4: Run the shelf tests**

Run: `.venv/bin/python -m pytest tests/test_local.py -q -k "shelf"`

Expected: PASS.

- [ ] **Step 5: Run the whole local test module**

Run: `.venv/bin/python -m pytest tests/test_local.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add git_ferret/analysis/local.py tests/test_local.py
git commit -m "feat(local): report IntelliJ shelves"
```

---

### Task 3: Document the marker and run the full gate

**Files:**
- Modify: `README.md`
- Add: `docs/superpowers/specs/2026-11-03-intellij-shelves-design.md`
- Add: `docs/superpowers/plans/2026-11-03-intellij-shelves.md`

**Interfaces:**
- Consumes: the `[SHELF]` marker and finding shape from Tasks 1 and 2.
- Produces: user-facing documentation; no code interface.

- [ ] **Step 1: Update the `local` section**

In `README.md`, change the line under "### `local`: what am I sitting on?" to:

```markdown
Branches checked out locally, plus worktree state: uncommitted changes, detached HEADs, stashes,
IntelliJ shelves.
```

Add this finding to the `local` example, after the `[STASH]` line:

```markdown
- 🗄️ `api-server` [SHELF] IntelliJ shelf "refactor-storage", modified 2026-10-14 18:30, contents not inspected
```

Add this paragraph after the example block:

```markdown
IntelliJ shelves are listed with their name and modification time, and the finding says the
contents were not inspected. IntelliJ's auto-generated `Uncommitted_changes_before_*` shelf
directories are churn rather than parked work, so they are skipped.
```

- [ ] **Step 2: Update the marker table and the feature list**

In the marker table, add this row after `[STASH]`:

```markdown
| `[SHELF]` | IntelliJ shelf directories, with name and modification time |
```

In "Additional features", add this bullet after stash reporting:

```markdown
- **IntelliJ shelf reporting** in `local`, with modification times and auto-generated shelves
  filtered out.
```

- [ ] **Step 3: Run the full fast gate**

Run: `make PYTHON=.venv/bin/python check`

Expected: format-check, lint, SPDX check, pyright, and the pytest suite all pass.

- [ ] **Step 4: Commit the documentation**

```bash
git add README.md docs/superpowers/specs/2026-11-03-intellij-shelves-design.md docs/superpowers/plans/2026-11-03-intellij-shelves.md
git commit -m "docs: document IntelliJ shelf findings"
```
