from __future__ import annotations

from pathlib import Path
from src.clients.code4rena_client import Code4renaClient, Code4renaContest
from src.mappers.finding_mapper import finding_to_bigquery_row
from src.models import Finding

SAMPLE_REPORTS_HTML = """
<!DOCTYPE html><html><body>
<script>
self.__next_f.push([1,"{\\\"alt_url\\\":null,\\\"contest\\\":237,\\\"date\\\":\\\"2023-07-26\\\",\\\"findings\\\":\\\"https://github.com/code-423n4/2023-05-juicebox-findings/issues\\\",\\\"slug\\\":\\\"2023-05-juicebox\\\",\\\"sponsor\\\":\\\"Juicebox\\\",\\\"title\\\":\\\"Juicebox Buyback Delegate\\\"}"]);
self.__next_f.push([1,"{\\\"alt_url\\\":null,\\\"contest\\\":230,\\\"date\\\":\\\"2023-05-18\\\",\\\"findings\\\":\\\"https://github.com/code-423n4/2023-04-caviar-findings/issues\\\",\\\"slug\\\":\\\"2023-04-caviar\\\",\\\"sponsor\\\":\\\"Caviar\\\",\\\"title\\\":\\\"Caviar Private Pools\\\"}"]);
</script>
</body></html>
"""

SAMPLE_FINDINGS_HTML = """
<div class="report-contents markdown-body">
<h1 id="overview">Overview</h1>
<p>About C4</p>
<h1 id="medium-risk-findings-3">Medium Risk Findings (3)</h1>
<h2 id="m-01-delegate-architecture"><a href="https://github.com/code-423n4/2023-05-juicebox-findings/issues/232">[M-01] Delegate architecture forces users to set zero slippage</a></h2>
<p><em>Submitted by <a href="https://github.com/adriro">adriro</a>, also found by <a href="https://github.com/rbserver">rbserver</a></em></p>
<p>The design of the delegate forces users to set zero.</p>
<pre data-language="solidity"><code>function payParams() external returns (uint256 weight) {}</code></pre>
<h2 id="m-02-low-liquidity"><a href="https://github.com/code-423n4/2023-05-juicebox-findings/issues/100">[M-02] Low Liquidity in Uniswap V3 Pool</a></h2>
<p><em>Submitted by <a href="https://github.com/0xRobocop">0xRobocop</a></em></p>
<p>Low liquidity explanation here.</p>
<h1 id="gas-optimizations">Gas Optimizations</h1>
<h2 id="g-01-state-variables">[G-01] State variables can be packed</h2>
<p><em>Submitted by <a href="https://github.com/K42">K42</a></em></p>
<p>Pack state variables to save gas.</p>
</div>
"""


def test_parse_contests_from_html() -> None:
    contests = Code4renaClient.parse_contests_from_html(SAMPLE_REPORTS_HTML)
    assert len(contests) == 2
    assert contests[0].slug == "2023-05-juicebox"
    assert contests[0].title == "Juicebox Buyback Delegate"
    assert contests[0].sponsor == "Juicebox"
    assert contests[0].date == "2023-07-26"
    assert contests[0].contest_id == "237"

    assert contests[1].slug == "2023-04-caviar"
    assert contests[1].sponsor == "Caviar"


def test_parse_report_findings_and_validate_models() -> None:
    contest = Code4renaContest(
        slug="2023-05-juicebox",
        title="Juicebox Buyback Delegate",
        sponsor="Juicebox",
        date="2023-07-26",
        findings_url="https://github.com/code-423n4/2023-05-juicebox-findings/issues",
        contest_id="237",
    )

    raw_findings = Code4renaClient.parse_report_findings_from_html(
        SAMPLE_FINDINGS_HTML, contest
    )
    assert len(raw_findings) == 3

    # Check M-01
    m1 = raw_findings[0]
    assert m1["id"] == "c4-2023-05-juicebox-m-01-delegate-architecture"
    assert m1["impact"] == "MEDIUM"
    assert m1["title"] == "[M-01] Delegate architecture forces users to set zero slippage"
    assert "Submitted by [adriro]" in m1["content"]
    assert "```solidity" in m1["content"]
    assert m1["finders_count"] == 2
    assert [
        f["wardens_warden"]["handle"] for f in m1["issues_issue_finders"]
    ] == ["adriro", "rbserver"]
    assert m1["github_link"] == "https://github.com/code-423n4/2023-05-juicebox-findings/issues/232"

    # Validate against Finding Pydantic model
    finding_obj = Finding.model_validate(m1)
    assert finding_obj.id == m1["id"]
    assert finding_obj.impact == "MEDIUM"

    # Check BigQuery mapping
    bq_row = finding_to_bigquery_row(finding_obj)
    assert bq_row["id"] == m1["id"]
    assert bq_row["impact"] == "MEDIUM"
    assert bq_row["firm_name"] == "Code4rena"
    assert bq_row["protocol_name"] == "Juicebox"
    assert bq_row["finder_handles"] == ["adriro", "rbserver"]
    assert bq_row["source_payload_hash"] != ""

    # Check Gas finding
    g1 = raw_findings[2]
    assert g1["impact"] == "GAS"
    assert g1["title"] == "[G-01] State variables can be packed"
    finding_g = Finding.model_validate(g1)
    assert finding_g.impact == "GAS"
