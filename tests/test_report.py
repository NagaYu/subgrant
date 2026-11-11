"""Evidence-pack hash chain verifies and detects tampering."""

import copy
import json

from subgrant.checks import Finding, load_policy_pack, run_checks
from subgrant.graph import load_graph
from subgrant.report import build_pack, to_markdown, verify_pack

from .helpers import base_chain

PACK = load_policy_pack()


def _pack_for(doc):
    raw = json.dumps(doc).encode("utf-8")
    g = load_graph(doc)
    findings = run_checks(g, PACK)
    return build_pack(raw, findings, PACK, source="test"), findings


def test_pack_verifies_clean():
    pack, findings = _pack_for(base_chain())
    assert findings == []
    assert verify_pack(pack) is True
    assert pack["entries"][0]["type"] == "header"


def test_pack_verifies_with_findings():
    d = base_chain()
    d["edges"][1]["authority"]["tools"] = ["tool.read", "tool.write"]
    pack, findings = _pack_for(d)
    assert len(findings) == 1
    assert verify_pack(pack) is True


def test_tamper_payload_detected():
    d = base_chain()
    d["edges"][1]["authority"]["tools"] = ["tool.read", "tool.write"]
    pack, _ = _pack_for(d)
    tampered = copy.deepcopy(pack)
    tampered["entries"][1]["payload"]["edge"] = "e1"  # change the finding
    assert verify_pack(tampered) is False


def test_tamper_drop_entry_detected():
    d = base_chain()
    d["edges"][1]["authority"]["tools"] = ["tool.read", "tool.write"]
    pack, _ = _pack_for(d)
    tampered = copy.deepcopy(pack)
    del tampered["entries"][1]  # drop the finding entry; chain_tip no longer matches
    assert verify_pack(tampered) is False


def test_tamper_reorder_detected():
    # Build a pack with two findings, swap them.
    raw = b"{}"
    findings = [Finding("D1", "e2"), Finding("D6", "e3")]
    pack = build_pack(raw, findings, PACK, source="t")
    assert verify_pack(pack) is True
    pack["entries"][1], pack["entries"][2] = pack["entries"][2], pack["entries"][1]
    assert verify_pack(pack) is False


def test_tamper_header_detected():
    pack, _ = _pack_for(base_chain())
    tampered = copy.deepcopy(pack)
    tampered["entries"][0]["payload"]["graph_sha256"] = "0" * 64
    assert verify_pack(tampered) is False


def test_markdown_renders():
    pack, _ = _pack_for(base_chain())
    md = to_markdown(pack)
    assert "SubGrant evidence pack" in md
    assert "No findings" in md
