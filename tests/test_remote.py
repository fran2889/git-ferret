"""Tests for remote branch filtering and safe-to-delete gating."""

from pathlib import Path

from git_ferret.analysis.remote import (
    analyse_merged_candidates,
    analyse_remote,
    local_branch_unpushed_map,
)
from git_ferret.config import Config
from git_ferret.gitops import resolve_base_ref
from git_ferret.models import RepoReport, Status
from tests.helpers import clone_local, commit, make_repo, run

FRAN = "Fran <fran@z.com>"
OTHER = "Other <o@x.com>"


def _repo_with_branches(tmp_path: Path, branches: list[tuple[str, str]]) -> Path:
    """*branches* is a list of (name, author) pairs pushed to origin."""
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\nb\nc\n")
    commit(src, "base")
    for name, author in branches:
        run(src, "checkout", "-b", name, "main")
        (src / f"{name.replace('/', '-')}.txt").write_text(f"{name}\n")
        commit(src, f"work on {name}", author=author)
        run(src, "checkout", "main")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "fetch", "--all", "--prune")
    return clone


def _names(rep: RepoReport) -> set[str]:
    return {f.branch for f in rep.findings}


def test_remote_filters_by_branch_name(tmp_path: Path):
    clone = _repo_with_branches(tmp_path, [("ABC-123-add-thing", FRAN), ("ZZZ-other", OTHER)])
    rep = analyse_remote(clone, Config(), resolve_base_ref(clone), [], "ABC-123")
    assert "origin/ABC-123-add-thing" in _names(rep)
    assert "origin/ZZZ-other" not in _names(rep)


def test_remote_filters_by_author(tmp_path: Path):
    clone = _repo_with_branches(tmp_path, [("by-fran", FRAN), ("by-someone", OTHER)])
    rep = analyse_remote(clone, Config(), resolve_base_ref(clone), ["fran@z.com"], None)
    assert "origin/by-fran" in _names(rep)
    assert "origin/by-someone" not in _names(rep)


def test_both_filters_combine_with_and(tmp_path: Path):
    clone = _repo_with_branches(tmp_path, [("by-fran", FRAN), ("by-someone", OTHER)])
    rep = analyse_remote(clone, Config(), resolve_base_ref(clone), ["fran@z.com"], "by-fran")
    assert _names(rep) == {"origin/by-fran"}


def test_remote_ignores_whitelisted_branches(tmp_path: Path):
    clone = _repo_with_branches(tmp_path, [("release/9", FRAN)])
    rep = analyse_remote(clone, Config(whitelist=["release/*"]), resolve_base_ref(clone), [], None)
    assert "origin/release/9" not in _names(rep)


def test_remote_never_lists_the_base_ref(tmp_path: Path):
    clone = _repo_with_branches(tmp_path, [("feature", FRAN)])
    rep = analyse_remote(clone, Config(), resolve_base_ref(clone), [], None)
    assert "origin/main" not in _names(rep)


def test_empty_identities_lists_all_remote_branches(tmp_path: Path):
    clone = _repo_with_branches(tmp_path, [("someone-elses", OTHER)])
    rep = analyse_remote(clone, Config(), resolve_base_ref(clone), [], None)
    assert "origin/someone-elses" in _names(rep)


def _merged_repo(tmp_path: Path):
    """src with `done` squash-merged into main; clone has origin/done merged."""
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\nb\n")
    commit(src, "base")
    run(src, "checkout", "-b", "done")
    (src / "f.txt").write_text("a\nDONE\n")
    commit(src, "work")
    run(src, "checkout", "main")
    run(src, "merge", "--squash", "done")
    commit(src, "merge done")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "fetch", "--all", "--prune")
    return clone


def test_merged_branch_marked_safe_when_no_local_unpushed(tmp_path: Path):
    clone = _merged_repo(tmp_path)
    assert local_branch_unpushed_map(clone).get("done", False) is False
    rep = analyse_merged_candidates(clone, Config(), resolve_base_ref(clone), [], None)
    f = next(x for x in rep.findings if x.branch == "origin/done")
    assert f.status is Status.SAFE_TO_DELETE


def test_merged_branch_marked_unsafe_when_local_unpushed(tmp_path: Path):
    # The gate that matters most: the remote branch is merged, but the user's
    # local copy of it holds work that exists nowhere else.
    clone = _merged_repo(tmp_path)
    run(clone, "checkout", "-b", "done", "origin/done")
    (clone / "local-only.txt").write_text("mine\n")
    commit(clone, "local only")
    assert local_branch_unpushed_map(clone)["done"] is True
    rep = analyse_merged_candidates(clone, Config(), resolve_base_ref(clone), [], None)
    f = next(x for x in rep.findings if x.branch == "origin/done")
    # Merged is not the claim being made here, so the marker must not be [OK].
    assert f.status is Status.UNSAFE_TO_DELETE
    assert "unpushed" in f.detail.lower()


def test_unpushed_map_has_no_entry_for_an_absent_branch(tmp_path: Path):
    clone = _merged_repo(tmp_path)
    assert "no-such-branch" not in local_branch_unpushed_map(clone)


def test_local_branch_with_no_upstream_counts_as_unpushed(tmp_path: Path):
    # A branch that was never pushed has no upstream, so `ahead` cannot be
    # computed and reads as 0. It still holds work that exists nowhere else,
    # which is exactly what the deletion gate exists to protect.
    clone = _merged_repo(tmp_path)
    run(clone, "branch", "--no-track", "done", "origin/done")
    assert local_branch_unpushed_map(clone)["done"] is True


def test_merged_branch_unsafe_when_local_branch_has_no_upstream(tmp_path: Path):
    # The remote branch is merged, but the local branch of the same name was
    # never pushed. Recommending deletion here would lose the local work.
    clone = _merged_repo(tmp_path)
    run(clone, "branch", "--no-track", "done", "origin/done")
    run(clone, "checkout", "done")
    (clone / "local-only.txt").write_text("mine\n")
    commit(clone, "local only")

    rep = analyse_merged_candidates(clone, Config(), resolve_base_ref(clone), [], None)
    f = next(x for x in rep.findings if x.branch == "origin/done")
    assert f.status is Status.UNSAFE_TO_DELETE
    assert "unpushed" in f.detail.lower()


def test_merged_unmerged_branch_is_not_safe(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\nb\nc\n")
    commit(src, "base")
    run(src, "checkout", "-b", "open-work")
    (src / "f.txt").write_text("a\nOPEN\nc\n")
    commit(src, "work")
    run(src, "checkout", "main")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "fetch", "--all", "--prune")
    rep = analyse_merged_candidates(clone, Config(), resolve_base_ref(clone), [], None)
    f = next(x for x in rep.findings if x.branch == "origin/open-work")
    assert f.status is Status.NOT_MERGED


def test_merged_conflicting_branch_is_not_safe(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\nb\nc\n")
    commit(src, "base")
    run(src, "checkout", "-b", "conflict")
    (src / "f.txt").write_text("SIDE-A\nb\nc\n")
    commit(src, "side a")
    run(src, "checkout", "main")
    (src / "f.txt").write_text("SIDE-B\nb\nc\n")
    commit(src, "side b")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "fetch", "--all", "--prune")
    rep = analyse_merged_candidates(clone, Config(), resolve_base_ref(clone), [], None)
    f = next(x for x in rep.findings if x.branch == "origin/conflict")
    assert f.status is Status.CONFLICTS


def test_merged_never_marks_unknown_as_safe(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "checkout", "--orphan", "orphan")
    (src / "f.txt").write_text("zzz\n")
    run(src, "add", "-A")
    commit(src, "orphan")
    run(src, "checkout", "main")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "fetch", "--all", "--prune")
    rep = analyse_merged_candidates(clone, Config(), resolve_base_ref(clone), [], None)
    f = next(x for x in rep.findings if x.branch == "origin/orphan")
    assert f.status is Status.UNKNOWN


def test_safe_to_delete_against_a_local_base_ref_is_marked_weaker(tmp_path: Path):
    # The one override: the claim is right, but it rests on a local main that may
    # lag the server, so the glyph says "verify" rather than "safe".
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\nb\n")
    commit(src, "base")
    run(src, "checkout", "-b", "done")
    (src / "f.txt").write_text("a\nDONE\n")
    commit(src, "work")
    run(src, "checkout", "main")
    run(src, "merge", "--squash", "done")
    commit(src, "merge done")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "fetch", "--all", "--prune")
    # Strip origin/main from the clone so the base ref falls back to local main,
    # which is a weaker claim than the remote's own.
    run(clone, "update-ref", "-d", "refs/remotes/origin/main")
    rep = analyse_merged_candidates(clone, Config(), resolve_base_ref(clone), [], None)
    f = next(x for x in rep.findings if x.branch == "origin/done")
    assert f.status is Status.SAFE_TO_DELETE
    assert f.emoji == Status.UNKNOWN.EMOJI
    assert "verify against the remote" in f.detail


def test_merged_respects_branch_filter(tmp_path: Path):
    clone = _merged_repo(tmp_path)
    rep = analyse_merged_candidates(clone, Config(), resolve_base_ref(clone), [], "nomatch")
    assert "origin/done" not in _names(rep)
