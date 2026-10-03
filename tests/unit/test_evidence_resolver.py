from __future__ import annotations

import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from src.models.knowledge_contract import (
    SourceFindingSnapshot,
    snapshot_id,
    source_key,
    stable_hash,
)
from src.repositories.knowledge_store import SQLiteKnowledgeStore
from src.services.evidence.discovery import discover
from src.services.evidence.replay import replay_transport
from src.services.evidence.resolver import (
    PIPELINE_VERSION,
    EvidenceResolver,
    ResolverConfig,
    parse_unified_diff,
)
from src.services.evidence.resolver_http import ResolutionError, ResolverHTTP
from src.services.knowledge_processing import (
    KnowledgeProcessingService,
    ResolutionResult,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/evidence_benchmark_v1"
BASE = "a" * 40
HEAD = "b" * 40


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Resolver tests must stay offline")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def make_snapshot(body, native_id="1", source="solodit"):
    raw = {"content": body, "id": native_id}
    key = source_key(source, native_id)
    return SourceFindingSnapshot(
        snapshot_id=snapshot_id(key, stable_hash(raw)),
        source_key=key,
        source=source,
        source_id=native_id,
        source_url="https://example.invalid/report",
        title="Report",
        content=body,
        payload_kind="api_json",
        raw_payload=raw,
        raw_payload_hash=stable_hash(raw),
        captured_at=datetime.now(UTC),
    )


def setup_run(tmp_path, body, handler=None, config=None):
    config = config or ResolverConfig(context_lines=0).model_dump()
    store = SQLiteKnowledgeStore(tmp_path / "resolver.db")
    now = [datetime.now(UTC)]
    service = KnowledgeProcessingService(store, clock=lambda: now[0], jitter=lambda: 0)
    snapshot = make_snapshot(body)
    state = service.enqueue(snapshot, pipeline_version=PIPELINE_VERSION, config=config)

    def denied(request):
        raise AssertionError(f"Unexpected request: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler or denied))
    resolver = EvidenceResolver(client, config=config, store=store)
    return service, store, now, state, resolver, client


def test_ast_discovery_handles_reference_links_tildes_and_mislabeled_code():
    body = """## Proof of Concept
[source][code]

~~~js
function exploit() external { uint a = 1; }
~~~

```solidity
[PASS] testExploit()
```

[code]: https://github.com/a/b/blob/main/A.sol#LL2C1-L3C9
"""
    nodes = discover(body)
    assert len(nodes) == 2
    assert nodes[0].start_line == 2 and nodes[0].end_line == 3
    assert nodes[1].role == "poc" and nodes[1].role_basis
    assert "function exploit" in nodes[1].snippet
    assert not discover("[report](https://github.com/a/b/blob/main/report.md)")


def test_inline_diff_keeps_both_sides_and_does_not_infer_vulnerability(tmp_path):
    body = "## Recommended Mitigation\n\n```diff\n-uint x = 1;\n+uint x = 2;\n```"
    service, store, _, state, resolver, client = setup_run(tmp_path, body)
    with client:
        done = service.run_batch([state.processing_key], resolver, worker="test")[0]
    assert done.status == "succeeded" and done.candidate_count == 2
    links = store.links(done.processing_key)
    evidence = [store.read("code_evidence", row["evidence_id"]) for row in links]
    assert {row["normalized_snippet"] for row in evidence} == {
        "uint x = 1;\n",
        "uint x = 2;\n",
    }
    assert all("-uint x = 1;" in row["raw_snippet"] for row in evidence)
    assert {row["role"] for row in links} == {"fix", "unknown"}
    assert all(row["syntax_status"] == "not_checked" for row in evidence)


def test_branch_resolved_to_sha_and_context_does_not_change_reported_range(tmp_path):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if "/commits/main" in str(request.url):
            return httpx.Response(200, json={"sha": HEAD})
        assert f"/{HEAD}/A.sol" in str(request.url)
        return httpx.Response(200, text="contract A {\nuint x;\n}\n")

    config = ResolverConfig(context_lines=1).model_dump()
    service, store, _, state, resolver, client = setup_run(
        tmp_path, "https://github.com/a/b/blob/main/A.sol#LL2C1-L2C9", handler, config
    )
    with client:
        done = service.run_batch([state.processing_key], resolver, worker="test")[0]
    link = store.links(done.processing_key)[0]
    evidence = store.read("code_evidence", link["evidence_id"])
    assert link["reported_range"]["start_line"] == 2
    assert evidence["source_range"]["start_line"] == 1
    assert evidence["source_range"]["end_line"] == 3
    assert evidence["commit_sha"] == HEAD and HEAD in evidence["origin_url"]
    assert len(seen) == 2


@pytest.mark.parametrize("anchor", ["L0-L2", "L5-L2", "L1-L99", "bad-anchor"])
def test_bad_source_range_is_unavailable_not_clamped(tmp_path, anchor):
    handler = lambda request: httpx.Response(200, text="uint x;\n")
    service, store, _, state, resolver, client = setup_run(
        tmp_path, f"https://github.com/a/b/blob/{HEAD}/A.sol#{anchor}", handler
    )
    with client:
        done = service.run_batch([state.processing_key], resolver, worker="test")[0]
    assert done.status == "partial" and done.unresolved_count == 1
    assert store.links(done.processing_key)[0]["evidence_id"] is None


def test_slash_branch_and_percent_encoded_path(tmp_path):
    seen = []

    def handler(request):
        url = str(request.url)
        seen.append(url)
        if "/commits/feature%2Ffix" in url:
            return httpx.Response(200, json={"sha": HEAD})
        if f"/{HEAD}/src/A%20B.sol" in url:
            return httpx.Response(200, text="contract A {}\n")
        return httpx.Response(404)

    service, _, _, state, resolver, client = setup_run(
        tmp_path, "https://github.com/a/b/blob/feature%2Ffix/src/A%20B.sol", handler
    )
    with client:
        assert (
            service.run_batch([state.processing_key], resolver, worker="test")[0].status
            == "succeeded"
        )
    assert any("feature%2Ffix" in url for url in seen)


DIFF = """diff --git a/A.sol b/Renamed.sol
similarity index 50%
--- a/A.sol
+++ b/Renamed.sol
@@ -1,3 +1,3 @@
 contract A {
-uint x = 1;
+uint x = 2;
 }
"""


def diff_handler(request):
    url = str(request.url)
    if "/commits/" in url:
        return httpx.Response(200, json={"sha": HEAD, "parents": [{"sha": BASE}]})
    if url.endswith(".diff"):
        return httpx.Response(200, text=DIFF)
    if f"/{BASE}/A.sol" in url:
        return httpx.Response(200, text="contract A {\nuint x = 1;\n}\n")
    if f"/{HEAD}/Renamed.sol" in url:
        return httpx.Response(200, text="contract A {\nuint x = 2;\n}\n")
    raise AssertionError(url)


def test_commit_diff_uses_parent_for_before_and_preserves_rename(tmp_path):
    service, store, _, state, resolver, client = setup_run(
        tmp_path,
        f"## Recommended Mitigation\nhttps://github.com/a/b/commit/{HEAD}",
        diff_handler,
    )
    with client:
        done = service.run_batch([state.processing_key], resolver, worker="test")[0]
    assert done.status == "succeeded" and done.candidate_count == 2
    evidence = [
        store.read("code_evidence", link["evidence_id"])
        for link in store.links(done.processing_key)
    ]
    assert {(row["commit_sha"], row["path"]) for row in evidence} == {
        (BASE, "A.sol"),
        (HEAD, "Renamed.sol"),
    }
    assert all(row["source_range"]["end_line"] == 3 for row in evidence)


def test_pull_diff_is_pinned_to_merge_base_and_head(tmp_path):
    seen = []

    def handler(request):
        url = str(request.url)
        seen.append(url)
        if "/pulls/7" in url:
            return httpx.Response(
                200, json={"base": {"sha": "c" * 40}, "head": {"sha": HEAD}}
            )
        if "api.github.com" in url and "/compare/" in url:
            return httpx.Response(200, json={"merge_base_commit": {"sha": BASE}})
        return diff_handler(request)

    service, _, _, state, resolver, client = setup_run(
        tmp_path, "https://github.com/a/b/pull/7", handler
    )
    with client:
        assert (
            service.run_batch([state.processing_key], resolver, worker="test")[0].status
            == "succeeded"
        )
    assert f"https://github.com/a/b/compare/{BASE}...{HEAD}.diff" in seen
    assert "https://github.com/a/b/pull/7.diff" not in seen


def test_diff_truncation_and_source_mismatch_fail_closed(tmp_path):
    with pytest.raises(ResolutionError, match="truncated_diff"):
        parse_unified_diff(DIFF.replace(" }\n", ""))

    def handler(request):
        if "raw.githubusercontent.com" in str(request.url):
            return httpx.Response(200, text="wrong source\n")
        return diff_handler(request)

    service, store, _, state, resolver, client = setup_run(
        tmp_path, f"https://github.com/a/b/commit/{HEAD}", handler
    )
    with client:
        done = service.run_batch([state.processing_key], resolver, worker="test")[0]
    assert done.status == "partial"
    assert store.links(done.processing_key)[0]["error_code"] == "diff_source_mismatch"


def test_gist_multiple_files_truncated_content_uses_pinned_raw(tmp_path):
    seen = []

    def handler(request):
        url = str(request.url)
        seen.append(url)
        if "api.github.com" in url:
            return httpx.Response(
                200,
                json={
                    "history": [{"version": HEAD}],
                    "owner": {"login": "alice"},
                    "files": {
                        "A.sol": {"content": "contract A {}", "truncated": False},
                        "B.sol": {
                            "content": "partial",
                            "truncated": True,
                            "raw_url": "https://untrusted.invalid/x",
                        },
                        "README.md": {"content": "not source"},
                    },
                },
            )
        assert url == f"https://gist.githubusercontent.com/alice/abcde/raw/{HEAD}/B.sol"
        return httpx.Response(200, text="contract B {}")

    service, store, _, state, resolver, client = setup_run(
        tmp_path, "https://gist.github.com/alice/abcde", handler
    )
    with client:
        done = service.run_batch([state.processing_key], resolver, worker="test")[0]
    assert done.status == "succeeded" and done.candidate_count == 2
    assert len(seen) == 2
    for link in store.links(done.processing_key):
        assert store.read("code_evidence", link["evidence_id"])["gist_revision"] == HEAD


def test_retry_expands_inventory_and_reuses_successful_inline(tmp_path):
    attempts = [0]

    def handler(request):
        attempts[0] += 1
        if attempts[0] == 1:
            return httpx.Response(429, headers={"Retry-After": "120"})
        return diff_handler(request)

    service, store, now, state, resolver, client = setup_run(
        tmp_path,
        f"```solidity\nuint y;\n```\nhttps://github.com/a/b/commit/{HEAD}",
        handler,
    )
    with client:
        first = service.run_batch([state.processing_key], resolver, worker="test")[0]
        assert first.status == "partial" and first.candidate_count == 2
        assert first.next_retry_at >= now[0] + timedelta(seconds=120)
        old = {link["link_id"] for link in store.links(state.processing_key)}
        now[0] = first.next_retry_at
        second = service.run_batch([state.processing_key], resolver, worker="test")[0]
    assert second.status == "succeeded" and second.candidate_count == 3
    assert old.issubset({link["link_id"] for link in store.links(state.processing_key)})


def test_retry_cannot_drop_failed_link(tmp_path):
    # Inventory expansion is additive; it must not allow false success by omission.
    service, _, _, state, resolver, client = setup_run(
        tmp_path,
        "https://github.com/a/b/blob/main/A.sol",
        lambda request: httpx.Response(503),
    )
    with client:
        lease = service.claim(state.processing_key, worker="test")
        partial = service.complete(
            lease,
            resolver(make_snapshot("https://github.com/a/b/blob/main/A.sol"), lease),
        )
    service.clock = lambda: partial.next_retry_at
    lease = service.claim(state.processing_key, worker="test")
    with pytest.raises(ValueError, match="cannot drop"):
        service.complete(
            lease, ResolutionResult(0, [], [], allow_inventory_expansion=True)
        )


@pytest.mark.parametrize(
    "status,retryable", [(404, False), (403, False), (429, True), (503, True)]
)
def test_http_errors_remain_per_candidate_and_inline_is_kept(
    tmp_path, status, retryable
):
    service, store, _, state, resolver, client = setup_run(
        tmp_path,
        "```solidity\nuint x;\n```\nhttps://github.com/a/b/blob/main/A.sol",
        lambda request: httpx.Response(status),
    )
    with client:
        done = service.run_batch([state.processing_key], resolver, worker="test")[0]
    assert done.status == "partial" and done.resolved_count == 1
    assert done.retryable is retryable
    assert len(store.links(state.processing_key)) == 2


def test_timeout_is_retryable_and_size_limit_is_explicit():
    def timeout(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(ResolutionError) as error:
            ResolverHTTP(client).text("https://api.github.com/test")
        assert error.value.retryable
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, text="a" * 101)
            )
        ) as client,
        pytest.raises(ResolutionError, match="response_too_large"),
    ):
        ResolverHTTP(client, max_bytes=100).text("https://api.github.com/test")


def test_redirect_does_not_leak_credentials_or_access_unknown_host():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            302, headers={"Location": "https://untrusted.invalid/secret"}
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ResolutionError, match="unsupported_host"),
    ):
        ResolverHTTP(client, token="test-token").text(
            "https://raw.githubusercontent.com/a/b/main/A.sol"
        )
    assert len(seen) == 1 and "authorization" not in seen[0].headers


def test_recorded_real_file_and_gist_resolve_offline(tmp_path):
    body = (
        "https://github.com/code-423n4/2023-01-astaria/blob/1bfc58b42109b839528ab1c21dc9803d663df898/src/LienToken.sol#L849\n\n"
        "https://gist.github.com/alice/06238839330315780b90d9202042ea0f"
    )
    service, store, _, state, _, unused = setup_run(tmp_path, body)
    unused.close()
    with httpx.Client(transport=replay_transport(FIXTURES / "http")) as client:
        resolver = EvidenceResolver(
            client, config=ResolverConfig(context_lines=0).model_dump(), store=store
        )
        done = service.run_batch([state.processing_key], resolver, worker="test")[0]
    assert done.status == "succeeded" and done.candidate_count == 2
    evidence = [
        store.read("code_evidence", link["evidence_id"])
        for link in store.links(done.processing_key)
    ]
    assert any(
        "TRANSFER_PROXY.tokenTransferFrom" in row["raw_snippet"] for row in evidence
    )
    assert any(
        "test_PrivatePool_flashLoan_IncorrectFee" in row["raw_snippet"]
        for row in evidence
    )


def test_no_code_and_config_mismatch(tmp_path):
    service, _, _, state, resolver, client = setup_run(
        tmp_path, "Plain report without source references"
    )
    with client:
        done = service.run_batch([state.processing_key], resolver, worker="test")[0]
    assert done.completion_reason == "no_candidates"
    resolver.config_hash = "0" * 64
    with pytest.raises(ValueError, match="fingerprint"):
        resolver(make_snapshot("Plain report without source references"), state)


def test_budget_exhaustion_is_explicit_and_not_success(tmp_path):
    config = ResolverConfig(max_candidates=1).model_dump()
    body = "```solidity\nuint x;\n```\n\n```solidity\nuint y;\n```"
    service, store, _, state, resolver, client = setup_run(
        tmp_path, body, config=config
    )
    with client:
        done = service.run_batch([state.processing_key], resolver, worker="test")[0]
    assert done.status == "partial" and done.candidate_count == 2
    assert any(
        link["error_code"] == "candidate_budget_exceeded"
        for link in store.links(done.processing_key)
    )


def test_same_source_evidence_can_be_shared_across_sources(tmp_path):
    body = f"https://github.com/a/b/blob/{HEAD}/A.sol"
    service, store, _, state, resolver, client = setup_run(
        tmp_path, body, lambda request: httpx.Response(200, text="contract A {}\n")
    )
    other = service.enqueue(
        make_snapshot(body, source="code4rena"),
        pipeline_version=PIPELINE_VERSION,
        config=ResolverConfig(context_lines=0).model_dump(),
    )
    with client:
        done = service.run_batch(
            [state.processing_key, other.processing_key], resolver, worker="test"
        )
    first, second = [store.links(row.processing_key)[0] for row in done]
    assert first["snapshot_id"] != second["snapshot_id"]
    assert first["evidence_id"] == second["evidence_id"]
    assert first["link_id"] != second["link_id"]


def test_added_and_deleted_files_and_no_final_newline():
    patch = "diff --git a/A.sol b/A.sol\n--- /dev/null\n+++ b/A.sol\n@@ -0,0 +1 @@\n+uint x;\n\\ No newline at end of file\n"
    added = parse_unified_diff(patch)[0]
    assert added.old_path is None and added.before == "" and added.after == "uint x;"
    deleted = parse_unified_diff(
        "diff --git a/A.sol b/A.sol\n--- a/A.sol\n+++ /dev/null\n@@ -1 +0,0 @@\n-uint x;\n"
    )[0]
    assert (
        deleted.new_path is None
        and deleted.before == "uint x;\n"
        and deleted.after == ""
    )


def test_request_budget_rate_limit_and_approved_redirect():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.host == "api.github.com":
            return httpx.Response(
                302,
                headers={
                    "Location": "https://raw.githubusercontent.com/a/b/main/A.sol"
                },
            )
        return httpx.Response(200, text="uint x;")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        http = ResolverHTTP(client, token="test-token", max_requests=2)
        assert http.text("https://api.github.com/test") == "uint x;"
        assert seen[0].headers["authorization"] == "Bearer test-token"
        assert "authorization" not in seen[1].headers
        with pytest.raises(ResolutionError, match="request_budget_exceeded"):
            http.text("https://api.github.com/other")
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(403, headers={"Retry-After": "60"})
        )
    ) as client:
        with pytest.raises(ResolutionError) as error:
            ResolverHTTP(client).text("https://api.github.com/test")
        assert error.value.retryable and error.value.retry_after == 60
