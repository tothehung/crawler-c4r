from __future__ import annotations

from src.services.evidence.dedup import Deduplicator, evidence_fingerprint


def test_fingerprint_is_stable_for_same_inputs() -> None:
    kwargs = dict(
        repo="acme/vaults",
        path="src/Vault.sol",
        ref_sha="deadbeef",
        start_line=10,
        end_line=20,
        snippet="contract Vault {}",
    )

    assert evidence_fingerprint(**kwargs) == evidence_fingerprint(**kwargs)


def test_fingerprint_ignores_whitespace_differences() -> None:
    base = dict(repo="", path=None, ref_sha=None, start_line=None, end_line=None)

    left = evidence_fingerprint(**base, snippet="a = 1;\nb = 2;")
    right = evidence_fingerprint(**base, snippet="a = 1;      \nb   = 2;")

    assert left == right


def test_fingerprint_changes_with_location() -> None:
    base = dict(repo="r", path="p", ref_sha="s", snippet="x")

    assert evidence_fingerprint(**base, start_line=1, end_line=2) != evidence_fingerprint(
        **base,
        start_line=3,
        end_line=4,
    )


def test_deduplicator_returns_duplicate_id_for_repeat() -> None:
    dedup = Deduplicator()

    first = dedup.register("fp-1", "evidence-1")
    second = dedup.register("fp-1", "evidence-2")

    assert first is None
    assert second == "evidence-1"


def test_deduplicator_tracks_distinct_fingerprints() -> None:
    dedup = Deduplicator()

    assert dedup.register("fp-1", "e-1") is None
    assert dedup.register("fp-2", "e-2") is None
    assert "fp-1" in dedup
