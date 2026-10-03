from __future__ import annotations

import hashlib
import json
import socket

import httpx
import pytest

from scripts.benchmark_evidence import FIXTURES, load, matches, replay_client, score
from scripts.build_evidence_annotations import build, sha
from src.models import Finding
from src.models.knowledge_contract import (
    SourceFindingSnapshot,
    snapshot_id,
    source_key,
    stable_hash,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Benchmark tests must run offline")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def test_real_corpus_has_unique_sources_and_frozen_provenance():
    cases = load("cases.json")
    assert len(cases) == 35
    assert len({(c["source"], c["finding"]["id"]) for c in cases}) == 35
    assert sum(c["source"] == "solodit" for c in cases) == 20
    assert sum(c["source"] == "code4rena" for c in cases) == 15
    acquisitions = {a["file"]: a for a in load("acquisitions.json")}
    for artifact, info in acquisitions.items():
        assert (
            hashlib.sha256((FIXTURES / artifact).read_bytes()).hexdigest()
            == info["sha256"]
        )
    raw_rows = [
        json.loads(line)
        for line in (FIXTURES / "raw/solodit-local.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    for case in cases:
        assert case["fixture_kind"] == "real"
        Finding.model_validate(case["finding"])
        assert case["provenance"]["artifact"] in acquisitions
        if case["source"] == "solodit":
            raw = raw_rows[case["provenance"]["line"] - 1]["source_payload"]
            if isinstance(raw, str):
                raw = json.loads(raw)
            assert raw == case["finding"]
        else:
            # The stable finding ID suffix comes from an actual HTML heading.
            slug = case["provenance"]["artifact"].split("/")[-1].removesuffix(".html")
            heading = case["case_id"].removeprefix(f"c4-{slug}-")
            assert f'id="{heading}"' in (
                FIXTURES / case["provenance"]["artifact"]
            ).read_text(encoding="utf-8")


def test_real_samples_can_enter_phase_one_snapshot_contract():
    for case in load("cases.json"):
        finding = case["finding"]
        key = source_key(case["source"], finding["id"])
        raw = (
            finding
            if case["source"] == "solodit"
            else (FIXTURES / case["provenance"]["artifact"]).read_text(encoding="utf-8")
        )
        digest = stable_hash(raw)
        snapshot = SourceFindingSnapshot(
            snapshot_id=snapshot_id(key, digest),
            source_key=key,
            source=case["source"],
            source_id=finding["id"],
            source_url=case["provenance"]["source_url"],
            title=finding["title"],
            content=finding["content"],
            payload_kind=case["provenance"]["payload_kind"],
            raw_payload=raw,
            raw_payload_hash=digest,
            captured_at="2026-09-29T00:00:00Z",
        )
        assert (
            snapshot.canonical_finding_id is None
        )  # No invented real duplicate assignments.


def test_reviewed_annotations_are_anchored_and_reproducible():
    cases = {c["case_id"]: c for c in load("cases.json")}
    annotations = load("annotations.json")
    assert annotations == build()
    assert len(annotations) == len(cases)
    assert [a["case_id"] for a in annotations if a["status"] == "quarantined"] == [
        "solodit-66925"
    ]
    for annotation in annotations:
        finding = cases[annotation["case_id"]]["finding"]
        assert annotation["input_sha256"] == sha(
            json.dumps(finding, sort_keys=True, ensure_ascii=False)
        )
        if annotation["status"] != "quarantined":
            assert annotation["expected"]
        for target in annotation["expected"]:
            loc = target["report_location"]
            quoted = finding[loc["field"]][loc["start_offset"] : loc["end_offset"]]
            assert quoted == target.get("snippet", target.get("url"))
            if target["type"] == "snippet":
                assert sha(quoted.strip()) == target["snippet_sha256"]
                assert target["role"] in {
                    "vulnerable",
                    "fix",
                    "context",
                    "poc",
                    "unknown",
                }


def test_evaluator_detects_missing_and_forbidden_without_penalizing_unlabelled():
    cases = [{"case_id": "case-1", "source": "solodit"}]
    annotation = [
        {
            "case_id": "case-1",
            "status": "report_reviewed",
            "expected": [
                {
                    "type": "snippet",
                    "kind": "inline_snippet",
                    "snippet_sha256": "wanted",
                }
            ],
            "forbidden": [{"type": "url", "url": "https://example.invalid/report.md"}],
        }
    ]
    missing = score(cases, annotation, {"case-1": []})
    assert missing["recall"] == 0
    actual = {
        "case-1": [
            {"snippet_sha256": "wanted"},
            {"url": "https://example.invalid/report.md"},
            {"snippet_sha256": "unlabelled"},
        ]
    }
    result = score(cases, annotation, actual)
    assert result["recall"] == 1
    assert result["forbidden_matches"] == 1
    assert "global precision" in result["not_scored"]


def test_range_matching_does_not_accept_file_only_for_line_target():
    target = {
        "type": "url",
        "url": "https://github.com/a/b/blob/main/C.sol#LL640C9-L650C15",
        "start_line": 640,
        "end_line": 650,
    }
    observation = {
        "url": "https://github.com/a/b/blob/main/C.sol",
        "start_line": None,
        "end_line": None,
    }
    assert not matches(target, observation)
    assert matches(target, observation | {"start_line": 640, "end_line": 650})


def test_recorded_http_hashes_and_replay_are_exact():
    with replay_client() as client:
        for row in load("http/index.json"):
            response = client.get(row["url"])
            assert response.status_code == row["status_code"]
            assert hashlib.sha256(response.content).hexdigest() == row["sha256"]
        with pytest.raises(AssertionError, match="Unrecorded request"):
            client.get("https://example.invalid/not-recorded")


def test_recorded_source_range_gist_and_diff_have_expected_content():
    with replay_client() as client:
        url = "https://raw.githubusercontent.com/code-423n4/2023-01-astaria/1bfc58b42109b839528ab1c21dc9803d663df898/src/LienToken.sol"
        source = client.get(url).text.splitlines()
        assert (
            "s.TRANSFER_PROXY.tokenTransferFrom(stack.lien.token, payer, payee, amount);"
            in source[848]
        )
        gist = client.get(
            "https://api.github.com/gists/06238839330315780b90d9202042ea0f"
        ).json()
        file = gist["files"]["2023-04-caviar-Audit.t.sol"]
        assert file["truncated"] is False
        assert "test_PrivatePool_flashLoan_IncorrectFee" in file["content"]
        assert gist["history"][0]["version"]
        diff = client.get(
            "https://github.com/outdoteth/caviar-private-pools/pull/6.diff"
        ).text
        assert "-        return changeFee;" in diff
        assert "+        return feePerNft;" in diff


@pytest.mark.parametrize(
    "name", ["not-found", "rate-limited", "upstream-failure", "timeout"]
)
def test_synthetic_transport_controls_are_explicit_and_offline(name):
    controls = load("controls.json")
    assert controls["fixture_kind"] == "synthetic"
    scenario = next(s for s in controls["http_scenarios"] if s["name"] == name)

    def handler(request):
        if scenario.get("exception"):
            raise httpx.ReadTimeout("Synthetic timeout", request=request)
        return httpx.Response(
            scenario["status_code"],
            text=scenario["body"],
            headers=scenario.get("headers", {}),
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        if name == "timeout":
            with pytest.raises(httpx.ReadTimeout):
                client.get("https://example.invalid/control")
        else:
            response = client.get("https://example.invalid/control")
            assert response.status_code == scenario["status_code"]
            if name == "rate-limited":
                assert response.headers["Retry-After"] == "60"


def test_synthetic_duplicate_control_keeps_source_identities_separate():
    group = load("controls.json")["duplicate_groups"][0]
    keys = {source_key(m["source"], m["source_id"]) for m in group["members"]}
    assert len(keys) == 2
    assert group["report_url"].startswith("https://example.invalid/")
