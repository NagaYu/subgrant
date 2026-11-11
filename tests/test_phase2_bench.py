"""Phase 2 bench + audit regression (dev_ext, baselines, fixtures, descriptors)."""

import glob
import hashlib
import json
import os

from bench import generate_dev_ext, score_baselines, score_ext
from subgrant.checks import load_policy_pack, run_checks
from subgrant.graph import load_graph
from subgrant.normalizers import normalize

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES_SHA256 = "6858bed2b96ecd855cc862f7cf69e684e32ae982b5781dd7b7574da5ccf3c706"
PACK = load_policy_pack()


def test_cases_jsonl_sha256_anchor_unchanged():
    data = open(os.path.join(REPO, "bench", "dev", "cases.jsonl"), "rb").read()
    assert hashlib.sha256(data).hexdigest() == CASES_SHA256


def test_dev_ext_regenerates_byte_identical():
    manifest, files = generate_dev_ext.build()
    # Manifest on disk matches.
    on_disk = open(os.path.join(REPO, "bench", "dev_ext", "manifest.json"), encoding="utf-8").read()
    assert json.dumps(manifest, sort_keys=True, indent=2) + "\n" == on_disk
    # Each representation file matches.
    for rel, doc in files.items():
        path = os.path.join(REPO, "bench", "dev_ext", rel)
        assert json.dumps(doc, sort_keys=True, indent=2) + "\n" == open(path, encoding="utf-8").read()


def test_dev_ext_round_trip_all_pass():
    result = score_ext.score()
    assert result["all_pass"] is True
    assert result["mismatches"] == []
    # Every format expresses at least some cases.
    for fmt in ("ucan", "rfc8693", "descriptor"):
        assert result["per_format"][fmt]["expressible"] > 0
        assert result["per_format"][fmt]["failed"] == 0


def test_dev_ext_selection_is_24():
    assert len(generate_dev_ext.select_case_ids()) == 24


def test_b0_baseline_expected_misses():
    cases = score_baselines.load_cases()
    b0 = score_baselines.score_b0(cases, PACK)
    assert b0["recall"]["D5"] == 0.0
    assert b0["recall"]["D7"] == 0.0
    assert b0["recall"]["D1"] == 1.0
    assert b0["recall"]["D3"] == 1.0
    assert b0["d8_detected"] == 0  # B0 has no evidence check
    assert b0["clean_fp_cases"] == 0


def test_b1_attenu_agreement_profile():
    b1 = score_baselines.score_b1_attenu(PACK)
    by_vec = {r["vector"]: r for r in b1}
    assert by_vec["valid_chain.json"]["agree"] is True
    assert by_vec["reject_widened_scope.json"]["agree"] is True
    assert by_vec["reject_depth_exceeded.json"]["agree"] is True
    assert by_vec["reject_nonmonotonic_exp.json"]["agree"] is True
    # The one honest divergence: SubGrant cannot see a corrupted signature.
    assert by_vec["reject_bad_signature.json"]["agree"] is False


def test_all_descriptors_normalize_and_verify():
    for f in sorted(glob.glob(os.path.join(REPO, "audit", "descriptors", "*.json"))):
        doc = json.load(open(f))
        g = normalize("descriptor", doc)
        load_graph(g)  # must be valid dgraph/1
        findings = {(x.cls, x.edge) for x in run_checks(load_graph(g), PACK)}
        # Every modeled scenario records no delegation binding -> D8 on every edge.
        assert ("D8", "e1") in findings


def test_inherit_frameworks_flag_d7():
    for name in ("langgraph-deepagents", "claude-agent-sdk"):
        doc = json.load(open(os.path.join(REPO, "audit", "descriptors", f"{name}.json")))
        findings = {(x.cls, x.edge) for x in run_checks(load_graph(normalize("descriptor", doc)), PACK)}
        assert ("D7", "e3") in findings
