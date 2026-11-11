"""SARIF 2.1.0 emitter structure (Phase 2 §5 / §7)."""

from subgrant.checks import Finding
from subgrant.sarif import ALL_RULES, build_sarif


def test_sarif_structure():
    findings = [Finding("D1", "e2"), Finding("D8", "e3")]
    doc = build_sarif(findings, "graph.json")
    assert doc["version"] == "2.1.0"
    assert len(doc["runs"]) == 1
    run = doc["runs"][0]
    assert run["tool"]["driver"]["name"] == "SubGrant"
    rule_ids = [r["id"] for r in run["tool"]["driver"]["rules"]]
    assert rule_ids == ALL_RULES  # D1..D8
    assert len(run["results"]) == 2


def test_sarif_levels_and_locations():
    doc = build_sarif([Finding("D1", "e2"), Finding("D8", "e3")], "my/graph.json")
    results = doc["runs"][0]["results"]
    by_rule = {r["ruleId"]: r for r in results}
    assert by_rule["D1"]["level"] == "error"
    assert by_rule["D8"]["level"] == "note"
    loc = by_rule["D1"]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert loc == "my/graph.json"
    assert by_rule["D1"]["properties"]["edge"] == "e2"
    assert "D1 on edge e2" in by_rule["D1"]["message"]["text"]


def test_sarif_empty_findings():
    doc = build_sarif([], "g.json")
    assert doc["runs"][0]["results"] == []
    # rules are always declared even with no results
    assert len(doc["runs"][0]["tool"]["driver"]["rules"]) == 8
