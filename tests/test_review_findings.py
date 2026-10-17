"""Tests for gaps the whole-branch review found in already-shipped behaviour.

Each maps to a finding: a marker that misleads, a feature the spec requires and
the plan assigned but never wired, or a correctness bug reachable in ordinary use.
"""

from pathlib import Path

import pytest

from git_ferret.analysis.health import report_remote_health
from git_ferret.analysis.local import analyse_local, worktree_status
from git_ferret.analysis.merged import merge_verdict
from git_ferret.analysis.remote import analyse_merged_candidates, analyse_remote
from git_ferret.config import Config, identity_matches, resolve_identities
from git_ferret.gitops import resolve_base_ref
from git_ferret.models import BranchInfo, RepoReport, Status
from tests.helpers import clone_local, commit, make_repo, run


def _base(repo: Path) -> str | None:
    return resolve_base_ref(repo)


# --- I1: a remote branch is fully pushed by construction -----------------------


def test_unmerged_remote_branch_is_not_reported_as_not_pushed(tmp_path: Path):
    # `merged` iterates remote refs, so every branch it lists is pushed.
    # [NOT PUSHED] would read as "you have unpushed work".
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\nb\nc\n")
    commit(src, "base")
    run(src, "checkout", "-b", "open")
    (src / "f.txt").write_text("a\nOPEN\nc\n")
    commit(src, "work")
    run(src, "checkout", "main")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "fetch", "--all", "--prune")
    rep = analyse_merged_candidates(clone, Config(), _base(clone), [], None)
    f = next(x for x in rep.findings if x.branch == "origin/open")
    assert f.status is not Status.NOT_PUSHED
    assert f.status.MARKER == "[NOT MERGED]"


# --- I2: a second remote's main/master is a real branch -----------------------


def test_other_remotes_main_is_not_silently_dropped(tmp_path: Path):
    origin_src = make_repo(tmp_path / "origin-src")
    (origin_src / "f.txt").write_text("a\n")
    commit(origin_src, "base")

    mirror_src = make_repo(tmp_path / "mirror-src")
    (mirror_src / "m.txt").write_text("m\n")
    commit(mirror_src, "mirror base")

    clone = clone_local(origin_src, tmp_path / "clone")
    run(clone, "remote", "add", "mirror", f"file://{mirror_src}")
    run(clone, "fetch", "--all", "--prune")

    assert _base(clone) == "origin/main"
    rep = analyse_remote(clone, Config(), _base(clone), [], None)
    names = {f.branch for f in rep.findings}
    # origin/main is the base and is excluded; mirror/main is a different
    # branch and must still be listed.
    assert "origin/main" not in names
    assert "mirror/main" in names


# --- I3: unreachable remote ----------------------------------------------------


def test_fetch_failure_produces_an_unreachable_finding(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    run(repo, "remote", "add", "origin", "/nonexistent/path.git")
    report = RepoReport(path=repo, fetch_attempted=True, fetch_failed=True)
    report_remote_health(repo, report)
    assert any(f.status is Status.UNREACHABLE for f in report.findings)


def test_repo_without_a_remote_is_reported_unreachable(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    report = RepoReport(path=repo, fetch_attempted=False)
    report_remote_health(repo, report)
    assert any(f.status is Status.UNREACHABLE for f in report.findings)


def test_remote_and_merged_report_a_repo_without_a_remote(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    # `local` reported a missing remote but `remote` and `merged` stayed silent:
    # a repository with no remote produced a heading and nothing else, which
    # reads as "nothing to clean" rather than "could not look".
    from git_ferret.cli import run_command

    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")

    for command in ("remote", "merged"):
        run_command(command, tmp_path, False, [], None)
        out = capsys.readouterr().out
        assert "[UNREACHABLE]" in out, command
        assert "no remote configured" in out, command


# --- I4: stashes ----------------------------------------------------------------


def test_stashes_are_reported(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    (repo / "f.txt").write_text("wip\n")
    run(repo, "stash", "push", "-m", "half-finished work")
    rep = analyse_local(repo, Config(), _base(repo))
    assert any(f.status is Status.STASH for f in rep.findings)
    stash = next(f for f in rep.findings if f.status is Status.STASH)
    assert "half-finished work" in stash.detail


def test_no_stash_is_not_reported(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    rep = analyse_local(repo, Config(), _base(repo))
    assert not any(f.status is Status.STASH for f in rep.findings)


# --- I5: last commit age and the supporting detail ----------------------------


def test_last_commit_age_is_carried_on_a_finding(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "feat")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "checkout", "-b", "feat", "origin/feat")
    rep = analyse_local(clone, Config(), _base(clone))
    f = next(x for x in rep.findings if x.branch == "feat")
    assert "ago" in f.detail


def test_upstream_deleted_reports_unpushed_count(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "gone-branch")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "checkout", "-b", "gone-branch", "origin/gone-branch")
    # Work that exists nowhere on the remote, then lose the upstream.
    (clone / "local.txt").write_text("mine\n")
    commit(clone, "local only")
    run(clone, "update-ref", "-d", "refs/remotes/origin/gone-branch")
    rep = analyse_local(clone, Config(), _base(clone))
    f = next(x for x in rep.findings if x.branch == "gone-branch")
    assert f.status is Status.UPSTREAM_DELETED
    assert "unpushed" in f.detail.lower()


# --- I6/I7: identity parsing ---------------------------------------------------


def test_comma_separated_author_is_split(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    got = resolve_identities(["a@x.com,b@y.com"], Config(), repo)
    assert got == ["a@x.com", "b@y.com"]


def test_comma_separated_toml_author_is_split(tmp_path: Path):
    path = tmp_path / "c.toml"
    path.write_text('author = "a@x.com,b@y.com"\n')
    assert Config.load(path).author == ["a@x.com", "b@y.com"]


def test_toml_list_author_is_split_too(tmp_path: Path):
    path = tmp_path / "c.toml"
    path.write_text('author = ["a@x.com", "b@y.com"]\n')
    assert Config.load(path).author == ["a@x.com", "b@y.com"]


def test_empty_author_string_never_matches(tmp_path: Path):
    # `--author ""` resolves to [""], a non-empty list whose sole member is the
    # empty substring, which would match every commit.
    assert identity_matches(["Someone <x@y.com>"], [""]) is False


def test_empty_author_is_dropped_during_resolution(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    got = resolve_identities(["", "  "], Config(), repo)
    assert got == []


def test_blank_entries_are_dropped_but_real_ones_kept(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    assert resolve_identities(["", "real@x.com"], Config(), repo) == ["real@x.com"]


# --- I8: the gate must not re-list branches per candidate ----------------------


def test_merged_does_not_rescan_branches_per_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import git_ferret.analysis.remote as remote_mod

    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\nb\n")
    commit(src, "base")
    for i in range(6):
        run(src, "checkout", "-b", f"done{i}", "main")
        (src / f"f{i}.txt").write_text(f"{i}\n")
        commit(src, f"work {i}")
        run(src, "checkout", "main")
        run(src, "merge", "--squash", f"done{i}")
        commit(src, f"merge {i}")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "fetch", "--all", "--prune")

    calls: list[Path] = []
    original = remote_mod.list_branches

    def counting(repo: Path) -> list[BranchInfo]:
        calls.append(repo)
        return original(repo)

    monkeypatch.setattr(remote_mod, "list_branches", counting)
    analyse_merged_candidates(clone, Config(), _base(clone), [], None)
    # Once for the shared snapshot, not once per merged candidate.
    assert len(calls) <= 2, f"list_branches called {len(calls)} times"


# --- I11: the cleanliness gate must fail closed --------------------------------


def test_worktree_status_does_not_report_unreadable_as_clean(tmp_path: Path):
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    dirty, _ = worktree_status(not_a_repo)
    assert dirty is True, "an unreadable worktree must not be reported clean"


# --- M1: shallow granularity ---------------------------------------------------


def test_shallow_repo_reports_unknown_rather_than_conflicts(tmp_path: Path):
    # A depth-1 clone genuinely lacks the merge base, so UNKNOWN is the honest
    # verdict. What matters is that it is never CONFLICTS, which would be a
    # fabricated conflict, and never MERGED.
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\nb\nc\n")
    commit(src, "base")
    run(src, "checkout", "-b", "open")
    (src / "f.txt").write_text("a\nOPEN\nc\n")
    commit(src, "work")
    run(src, "checkout", "main")
    clone = clone_local(src, tmp_path / "shallow", depth=1)
    assert merge_verdict(clone, "origin/main", "origin/open").value == "UNKNOWN"


def test_deep_clone_of_same_history_is_not_unknown(tmp_path: Path):
    # The counterpart: when the objects are present the merge resolves, so the
    # shallow handling must not blanket-UNKNOWN every repository.
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\nb\nc\n")
    commit(src, "base")
    run(src, "checkout", "-b", "open")
    (src / "f.txt").write_text("a\nOPEN\nc\n")
    commit(src, "work")
    run(src, "checkout", "main")
    clone = clone_local(src, tmp_path / "full")
    assert merge_verdict(clone, "origin/main", "origin/open").value == "NOT_MERGED"
