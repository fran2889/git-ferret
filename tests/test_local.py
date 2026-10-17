"""Tests for local branch and worktree analysis."""

from pathlib import Path

from git_ferret.analysis.local import analyse_local
from git_ferret.config import Config
from git_ferret.gitops import resolve_base_ref
from git_ferret.models import RepoReport, Status
from tests.helpers import commit, make_repo, run


def _report(repo: Path, config: Config | None = None) -> RepoReport:
    return analyse_local(repo, config or Config(), resolve_base_ref(repo))


def _statuses(rep: RepoReport) -> list[Status]:
    return [f.status for f in rep.findings]


def _cloned_with_branch(tmp_path: Path, name: str) -> Path:
    """A clone with local *name* tracking a pushed branch: genuinely clean."""
    from tests.helpers import clone_local

    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", name)
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "checkout", "-b", name, f"origin/{name}")
    return clone


def test_reports_clean_branch_as_ok(tmp_path: Path):
    clone = _cloned_with_branch(tmp_path, "clean-branch")
    rep = _report(clone)
    f = next(x for x in rep.findings if x.branch == "clean-branch")
    assert f.status is Status.OK


def test_ok_says_nothing_beyond_the_marker(tmp_path: Path):
    # [OK] already means "nothing to see". Restating it in words gives a
    # branch that is fine the same visual weight as one that needs work.
    clone = _cloned_with_branch(tmp_path, "clean-branch")
    rep = _report(clone)
    f = next(x for x in rep.findings if x.branch == "clean-branch")
    assert "pushed" not in f.detail
    assert f.detail.startswith("last commit")


def test_branch_without_upstream_is_not_pushed(tmp_path: Path):
    # A branch that was never pushed is [NOT PUSHED], not clean.
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    run(repo, "branch", "never-pushed")
    rep = _report(repo)
    f = next(x for x in rep.findings if x.branch == "never-pushed")
    assert f.status is Status.NOT_PUSHED
    assert "no upstream" in f.detail


def test_main_is_never_listed(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    run(repo, "branch", "some-branch")
    rep = _report(repo)
    assert "main" not in {f.branch for f in rep.findings}


def test_whitelisted_clean_branch_is_hidden(tmp_path: Path):
    clone = _cloned_with_branch(tmp_path, "release/1.0")
    rep = _report(clone, Config(whitelist=["release/*"]))
    assert "release/1.0" not in {f.branch for f in rep.findings}


def test_whitelisted_dirty_branch_is_still_reported(tmp_path: Path):
    # The whitelist suppresses "this branch exists and is fine", never a problem.
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    run(repo, "checkout", "-b", "release/1.0")
    (repo / "f.txt").write_text("dirty\n")
    rep = _report(repo, Config(whitelist=["release/*"]))
    assert Status.DIRTY in _statuses(rep)


def test_whitelisted_unpushed_branch_is_still_reported(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    run(repo, "checkout", "-b", "release/1.0")
    (repo / "f.txt").write_text("a\nb\n")
    commit(repo, "work")
    rep = _report(repo, Config(whitelist=["release/*"]))
    not_pushed = next(
        f for f in rep.findings if f.branch == "release/1.0" and f.status is Status.NOT_PUSHED
    )
    assert not_pushed is not None


def test_reports_dirty_worktree(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    (repo / "untracked.txt").write_text("x\n")
    rep = _report(repo)
    assert Status.DIRTY in _statuses(rep)


def test_dirty_detail_counts_untracked_files(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    (repo / "new.txt").write_text("x\n")
    rep = _report(repo)
    dirty = next(f for f in rep.findings if f.status is Status.DIRTY)
    assert "1" in dirty.detail


def test_clean_worktree_is_not_dirty(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    rep = _report(repo)
    assert Status.DIRTY not in _statuses(rep)


def test_reports_unpushed_commits(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    run(repo, "checkout", "-b", "feat")
    (repo / "f.txt").write_text("a\nb\n")
    commit(repo, "work")
    rep = _report(repo)
    f = next(x for x in rep.findings if x.branch == "feat")
    assert f.status is Status.NOT_PUSHED


def test_reports_detached_head(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    sha = run(repo, "rev-parse", "HEAD").stdout.strip()
    run(repo, "checkout", sha)
    rep = _report(repo)
    assert Status.DETACHED in _statuses(rep)


def test_reports_upstream_deleted(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "gone-branch")
    from tests.helpers import clone_local

    clone = clone_local(src, tmp_path / "clone")
    run(clone, "checkout", "-b", "gone-branch", "origin/gone-branch")
    run(clone, "update-ref", "-d", "refs/remotes/origin/gone-branch")
    rep = _report(clone)
    f = next(x for x in rep.findings if x.branch == "gone-branch")
    assert f.status is Status.UPSTREAM_DELETED


def test_reports_diverged_when_ahead_and_behind(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "feat")
    from tests.helpers import clone_local

    clone = clone_local(src, tmp_path / "clone")
    run(clone, "checkout", "-b", "feat", "origin/feat")
    (clone / "f.txt").write_text("a\nlocal\n")
    commit(clone, "local work")
    run(src, "checkout", "feat")
    (src / "f.txt").write_text("a\nremote\n")
    commit(src, "remote work")
    run(src, "checkout", "main")
    run(clone, "fetch", "--all", "--prune")
    rep = _report(clone)
    f = next(x for x in rep.findings if x.branch == "feat")
    assert f.status is Status.DIVERGED


def test_no_base_branch_does_not_skip_the_branch_listing(tmp_path: Path):
    # Local branch status (pushed, dirty, ...) does not need a base branch, so
    # `local` keeps listing branches. The missing base is still reported, but
    # only `remote` and `merged`, which genuinely skip, may say "skipped".
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    run(repo, "branch", "-m", "main", "trunk")
    rep = analyse_local(repo, Config(), None)
    assert rep.skipped_reason is None
    assert any(f.status is Status.NO_BASE for f in rep.findings)
    assert "trunk" in {f.branch for f in rep.findings}


def test_worktrees_are_recorded_on_the_report(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    rep = _report(repo)
    assert len(rep.worktrees) == 1
    assert rep.worktrees[0].branch == "main"


def test_analysis_stamps_the_age_of_the_refs(tmp_path: Path):
    from tests.helpers import clone_local

    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    clone = clone_local(src, tmp_path / "clone")

    # The analysis reports on state already in .git and stamps when that state
    # was last refreshed. Whether a fetch was attempted this run, and whether it
    # succeeded, is the CLI's to record (test_freshness_and_exit.py).
    rep = _report(clone)
    assert rep.fetched_at is not None
    assert rep.fetch_failed is False
