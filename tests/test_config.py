"""Tests for config loading, identity resolution, and whitelist globbing."""

from pathlib import Path

from git_ferret.config import (
    Config,
    identity_matches,
    is_always_excluded,
    resolve_identities,
)
from tests.helpers import make_repo, run


def test_whitelist_supports_glob_star():
    c = Config(whitelist=["release/*"])
    assert c.is_whitelisted("release/2.1") is True
    assert c.is_whitelisted("feat/release") is False


def test_whitelist_supports_glob_question_mark():
    c = Config(whitelist=["hotfix-?"])
    assert c.is_whitelisted("hotfix-1") is True
    assert c.is_whitelisted("hotfix-10") is False


def test_whitelist_is_case_sensitive():
    c = Config(whitelist=["Release/*"])
    assert c.is_whitelisted("release/1") is False


def test_empty_whitelist_excludes_nothing():
    c = Config(whitelist=[])
    assert c.is_whitelisted("anything") is False


def test_always_excluded_covers_main_and_master():
    assert is_always_excluded("main", None) is True
    assert is_always_excluded("master", None) is True
    assert is_always_excluded("feat/x", "origin/main") is False


def test_always_excluded_covers_the_resolved_base_ref():
    assert is_always_excluded("origin/trunk", "origin/trunk") is True


def test_identity_precedence_cli_beats_toml(tmp_path: Path):
    repo = _repo(tmp_path)
    cfg = Config(author=["toml@example.com"])
    got = resolve_identities(["cli@example.com"], cfg, repo)
    assert got == ["cli@example.com"]


def test_identity_precedence_toml_beats_git_config(tmp_path: Path):
    repo = _repo(tmp_path)
    cfg = Config(author=["toml@example.com"])
    assert resolve_identities([], cfg, repo) == ["toml@example.com"]


def test_identity_falls_back_to_git_config(tmp_path: Path):
    repo = _repo(tmp_path)
    assert resolve_identities([], Config(author=[]), repo) == ["Dev <dev@example.com>"]


def test_identity_falls_back_to_the_email_when_there_is_no_name(tmp_path: Path):
    # Plenty of checkouts have an email and no name; refusing to resolve would
    # report every branch as somebody else's.
    repo = _repo(tmp_path)
    run(repo, "config", "--unset", "user.name")
    assert resolve_identities([], Config(author=[]), repo) == ["dev@example.com"]


def test_identity_is_empty_when_git_config_has_neither(tmp_path: Path):
    # An empty identity must never reach git's --author: an empty pattern
    # matches every commit.
    repo = _repo(tmp_path)
    run(repo, "config", "--unset", "user.name")
    run(repo, "config", "--unset", "user.email")
    assert resolve_identities([], Config(author=[]), repo) == []


def test_identity_is_resolved_per_repository(tmp_path: Path):
    repo_a = _repo(tmp_path / "a")
    repo_b = _repo(tmp_path / "b")
    run(repo_b, "config", "user.email", "other@example.com")
    cfg = Config(author=[])
    assert resolve_identities([], cfg, repo_a) != resolve_identities([], cfg, repo_b)


def test_multiple_identities_combine_as_a_list(tmp_path: Path):
    repo = _repo(tmp_path)
    cfg = Config(author=["a@x.com", "b@y.com"])
    assert resolve_identities([], cfg, repo) == ["a@x.com", "b@y.com"]


def test_empty_identity_never_matches_everything():
    # An unset identity must not match every commit the way git's own
    # `--author=""` does, which would report all branches as the user's.
    assert identity_matches(["Dev <dev@example.com>"], []) is False


def test_identity_matches_any_commit_any_identity():
    commits = ["Someone Else <x@y.com>", "Fran <fran@z.com>"]
    assert identity_matches(commits, ["fran@z.com"]) is True
    assert identity_matches(commits, ["nobody@nowhere"]) is False


def test_identity_matching_is_case_sensitive():
    assert identity_matches(["Dev <dev@example.com>"], ["DEV"]) is False


def test_load_reads_list_form(tmp_path: Path):
    path = tmp_path / "c.toml"
    path.write_text('author = ["a@x.com", "b@y.com"]\n\n[whitelist]\npatterns = ["release/*"]\n')
    c = Config.load(path)
    assert c.author == ["a@x.com", "b@y.com"]
    assert c.is_whitelisted("release/9") is True


def test_load_accepts_bare_string_author(tmp_path: Path):
    path = tmp_path / "c.toml"
    path.write_text('author = "solo@x.com"\n')
    assert Config.load(path).author == ["solo@x.com"]


def test_load_missing_file_is_empty_not_an_error(tmp_path: Path):
    c = Config.load(tmp_path / "absent.toml")
    assert c.author == [] and c.whitelist == []


def _repo(tmp_path: Path):
    return make_repo(tmp_path / "r")
