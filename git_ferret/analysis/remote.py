# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""Remote branch enumeration, filtering, and the safe-to-delete verdict.

Two subcommands share this enumeration. ``remote`` answers "which remote
branches match X" and does not judge deletion safety at all; ``merged`` adds
the merge verdict and the gate that keeps a live branch out of the deletable
set.
"""

from __future__ import annotations

from pathlib import Path

from git_ferret.analysis.local import NO_BASE_REASON, branch_status_is_clean
from git_ferret.analysis.merged import (
    MergeVerdict,
    branch_name_from_ref,
    commits_in_range,
    merge_verdict,
    remote_branches,
)
from git_ferret.config import Config, identity_matches, split_identities
from git_ferret.gitops import (
    base_ref_is_remote,
    list_branches,
    refs_updated_at,
)
from git_ferret.models import Finding, RepoReport, Status

_STATUS_FOR_VERDICT = {
    # `merged` only ever iterates remote refs, so every branch it lists is
    # already pushed. Calling an unmerged remote branch "[NOT PUSHED]" would
    # tell the user they have unpushed work, which is a different claim.
    MergeVerdict.NOT_MERGED: Status.NOT_MERGED,
    MergeVerdict.CONFLICTS: Status.CONFLICTS,
    MergeVerdict.UNKNOWN: Status.UNKNOWN,
}


def local_branch_unpushed_map(repo: Path) -> dict[str, bool]:
    """``{branch: holds unpushed work}`` for every local branch, in one pass.

    Taken once per run rather than per candidate: re-listing branches for each
    remote branch is quadratic, and the branches this tool reports are exactly
    the merged ones, so the cost lands on the hot path.

    "Unpushed" is the negation of a clean branch, which includes a branch with
    no upstream at all. Such a branch has no ``ahead`` count (there is nothing
    to compare against) but still holds work that exists nowhere on the remote,
    which is precisely what this gate exists to protect.
    """
    return {b.name: not branch_status_is_clean(b) for b in list_branches(repo)}


def _candidate_refs(repo: Path, config: Config, base_ref: str | None) -> list[str]:
    """Remote branch refs worth analysing.

    Excludes the base ref itself and ``main``/``master`` **on the base's own
    remote**. A second remote's ``main`` is a different branch, often a fork's
    trunk and exactly the kind of divergence worth reporting, so it must not
    be dropped just because its short name is "main".
    """
    base_remote = base_ref.split("/")[0] if base_ref and "/" in base_ref else None
    candidates: list[str] = []
    for ref in remote_branches(repo):
        name = branch_name_from_ref(ref)
        remote = ref.split("/")[0] if "/" in ref else None
        if base_ref is not None and ref == base_ref:
            continue
        if name in ("main", "master") and remote == base_remote:
            continue
        # For remote scans the whitelist is absolute: ignored entirely.
        if config.is_whitelisted(name):
            continue
        candidates.append(ref)
    return candidates


def _passes_filters(
    repo: Path,
    ref: str,
    base_ref: str,
    identities: list[str],
    branch_filter: str | list[str] | None,
) -> bool:
    """Apply OR within branch patterns and AND with the optional author filter."""
    patterns = split_identities(
        [branch_filter] if isinstance(branch_filter, str) else branch_filter or []
    )
    if patterns and not any(pattern in ref for pattern in patterns):
        return False
    if identities:
        # The range matters: the user's commits sit in the base history and are
        # therefore reachable from every branch.
        authors = commits_in_range(repo, base_ref, ref)
        if not identity_matches(authors, identities):
            return False
    return True


def _new_report(repo: Path, base_ref: str | None) -> RepoReport:
    report = RepoReport(path=repo, base_ref=base_ref)
    # The age of the last successful fetch, so a stale answer is visibly stale;
    # whether this run attempted or failed a fetch is the caller's to record.
    report.fetched_at = refs_updated_at(repo)
    if base_ref is None:
        report.skipped_reason = NO_BASE_REASON
        report.findings.append(
            Finding(
                branch=repo.name,
                status=Status.NO_BASE,
                detail=NO_BASE_REASON,
            )
        )
    return report


def analyse_remote(
    repo: Path,
    config: Config,
    base_ref: str | None,
    identities: list[str],
    branch_filter: str | list[str] | None,
) -> RepoReport:
    """List remote branches matching the filters. No deletion verdict here."""
    report = _new_report(repo, base_ref)
    if base_ref is None:
        return report

    for ref in _candidate_refs(repo, config, base_ref):
        if not _passes_filters(repo, ref, base_ref, identities, branch_filter):
            continue
        report.findings.append(
            Finding(
                branch=ref,
                status=Status.OK,
                detail="remote branch",
            )
        )
    return report


def analyse_merged_candidates(
    repo: Path,
    config: Config,
    base_ref: str | None,
    identities: list[str],
    branch_filter: str | list[str] | None,
) -> RepoReport:
    """Remote branches, each marked a deletion candidate or not.

    Merged-ness and deletability are separate claims, so they get separate
    markers. A branch is a candidate when the merge is clean *and* no same-named
    local branch holds unpushed work; the first is the merge test, the second is
    the gate. Both merged outcomes are reported, because a branch that is merged
    and must be kept is exactly the one a reader needs to see and not delete.
    """
    report = _new_report(repo, base_ref)
    if base_ref is None:
        return report

    unpushed = local_branch_unpushed_map(repo)

    for ref in _candidate_refs(repo, config, base_ref):
        if not _passes_filters(repo, ref, base_ref, identities, branch_filter):
            continue

        verdict = merge_verdict(repo, base_ref, ref)
        name = branch_name_from_ref(ref)

        if verdict is not MergeVerdict.MERGED:
            report.findings.append(
                Finding(
                    branch=ref,
                    status=_STATUS_FOR_VERDICT[verdict],
                    detail=_detail_for(verdict),
                )
            )
            continue

        if unpushed.get(name, False):
            report.findings.append(
                Finding(
                    branch=ref,
                    status=Status.UNSAFE_TO_DELETE,
                    detail=f"merged into {base_ref}, but local '{name}' has unpushed changes",
                )
            )
            continue

        report.findings.append(
            Finding(
                branch=ref,
                status=Status.SAFE_TO_DELETE,
                detail=_safe_detail(base_ref),
                # A safe-to-delete claim resting on a local base ref is weaker
                # than one resting on the remote's, and is marked as such. This
                # is the one place a status is not quite the verdict.
                emoji=(
                    Status.SAFE_TO_DELETE.EMOJI
                    if base_ref_is_remote(base_ref)
                    else Status.UNKNOWN.EMOJI
                ),
            )
        )
    return report


def _safe_detail(base_ref: str | None) -> str:
    """Why the branch is safe, flagging the lower-confidence local fallback.

    Comparing against a local base ref is a weaker claim than comparing against
    the remote's: the local copy may lag the server, and a branch the server
    already has would then look unmerged. That fallback is called out rather
    than presented with the same confidence as a remote comparison.
    """
    if base_ref_is_remote(base_ref):
        return f"safe to delete: merged into {base_ref}, no unpushed local changes"
    return (
        f"merged into local {base_ref} (no remote ref to compare against), "
        "verify against the remote before deleting"
    )


def _detail_for(verdict: MergeVerdict) -> str:
    if verdict is MergeVerdict.CONFLICTS:
        return "conflicts with base branch"
    if verdict is MergeVerdict.UNKNOWN:
        return "cannot determine (no merge base, or shallow clone)"
    return "not merged"
