"""Normalizer tests (Phase 2 §2 / §7): shape, mappings, and verify findings."""

import json
import os

import pytest

from subgrant.checks import load_policy_pack, run_checks
from subgrant.graph import load_graph
from subgrant.normalizers import NormalizeError, normalize

PACK = load_policy_pack()
FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures", "attenu")


def findings(graph_dict):
    return {(f.cls, f.edge) for f in run_checks(load_graph(graph_dict), PACK)}


# --- UCAN -------------------------------------------------------------------

def test_ucan_basic_clean():
    doc = {"chain": [
        {"iss": "n0", "aud": "n1", "exp": 1000, "nbf": 0, "att": [{"with": "db/x/*", "can": "data.read"}], "prf": []},
        {"iss": "n1", "aud": "n2", "exp": 900, "nbf": 0, "att": [{"with": "db/x/y", "can": "data.read"}], "prf": [0]},
    ]}
    g = normalize("ucan", doc)
    assert g["schema"] == "dgraph/1"
    assert [e["id"] for e in g["edges"]] == ["e1", "e2"]
    assert g["edges"][0]["evidence"] == {"kind": "signature", "ref": "ucan:0"}
    assert g["edges"][1]["authority"]["actions"] == ["data.read"]
    assert findings(g) == set()  # db/x/y subset-of db/x/*


def test_ucan_amplification_is_d1():
    doc = {"chain": [
        {"iss": "n0", "aud": "n1", "exp": 1000, "nbf": 0, "att": [{"with": "db/x/*", "can": "data.read"}], "prf": []},
        {"iss": "n1", "aud": "n2", "exp": 900, "nbf": 0,
         "att": [{"with": "db/x/*", "can": "data.read"}, {"with": "db/x/*", "can": "data.write"}], "prf": [0]},
    ]}
    assert ("D1", "e2") in findings(normalize("ucan", doc))


def test_ucan_nbf_inheritance():
    # Root has no nbf -> 2026-01-01; child has no nbf -> inherits root's issued_at.
    doc = {"chain": [
        {"iss": "n0", "aud": "n1", "exp": None, "att": [{"with": "db/x/*", "can": "data.read"}], "prf": []},
        {"iss": "n1", "aud": "n2", "exp": None, "att": [{"with": "db/x/*", "can": "data.read"}], "prf": [0]},
    ]}
    g = normalize("ucan", doc)
    assert g["edges"][0]["caveats"]["issued_at"] == "2026-01-01T00:00:00Z"
    assert g["edges"][1]["caveats"]["issued_at"] == "2026-01-01T00:00:00Z"


def test_ucan_scheme_stripped_and_star():
    doc = {"chain": [
        {"iss": "n0", "aud": "n1", "exp": None, "nbf": 0, "att": [{"with": "https://db/x/*", "can": "a"}], "prf": []},
    ]}
    g = normalize("ucan", doc)
    assert g["edges"][0]["authority"]["resources"] == ["db/x/*"]


def test_ucan_bad_proof_index():
    doc = {"chain": [
        {"iss": "n0", "aud": "n1", "exp": None, "nbf": 0, "att": [{"with": "*", "can": "a"}], "prf": []},
        {"iss": "n1", "aud": "n2", "exp": None, "nbf": 0, "att": [{"with": "*", "can": "a"}], "prf": [5]},
    ]}
    with pytest.raises(NormalizeError, match="earlier link"):
        normalize("ucan", doc)


def test_ucan_multiple_proofs_rejected():
    doc = {"chain": [
        {"iss": "n0", "aud": "n1", "exp": None, "nbf": 0, "att": [{"with": "*", "can": "a"}], "prf": []},
        {"iss": "n1", "aud": "n2", "exp": None, "nbf": 0, "att": [{"with": "*", "can": "a"}], "prf": [0, 0]},
    ]}
    with pytest.raises(NormalizeError, match="exactly one proof"):
        normalize("ucan", doc)


# --- RFC 8693 ---------------------------------------------------------------

def test_rfc8693_single_edge_no_act():
    doc = {"iss": "a", "sub": "b", "scope": "data.read", "iat": 0, "exp": 3600}
    g = normalize("rfc8693", doc)
    assert [e["id"] for e in g["edges"]] == ["e1"]
    assert g["edges"][0]["issuer"] == "a" and g["edges"][0]["holder"] == "b"
    assert g["edges"][0]["authority"]["actions"] == ["data.read"]
    assert findings(g) == set()


def test_rfc8693_act_chain_and_inherit_scope():
    doc = {"iss": "a", "sub": "b", "scope": "data.read data.write", "iat": 0, "exp": 3600,
           "act": {"sub": "c", "act": {"sub": "d", "scope": "data.read"}}}
    g = normalize("rfc8693", doc)
    assert [e["id"] for e in g["edges"]] == ["e1", "e2", "e3"]
    # e2 has no scope -> inherits e1's actions.
    assert g["edges"][1]["authority"]["actions"] == ["data.read", "data.write"]
    assert g["edges"][2]["authority"]["actions"] == ["data.read"]
    assert findings(g) == set()


def test_rfc8693_scope_widening_is_d1():
    doc = {"iss": "a", "sub": "b", "scope": "data.read", "iat": 0, "exp": 3600,
           "act": {"sub": "c", "scope": "data.read data.write"}}
    assert ("D1", "e2") in findings(normalize("rfc8693", doc))


# --- attenu -----------------------------------------------------------------

def test_attenu_valid_vector_clean():
    doc = json.load(open(os.path.join(FIX, "valid_chain.json")))
    assert findings(normalize("attenu", doc)) == set()


def test_attenu_widened_scope_is_d1():
    doc = json.load(open(os.path.join(FIX, "reject_widened_scope.json")))
    assert ("D1", "e3") in findings(normalize("attenu", doc))


def test_attenu_depth_exceeded_is_d2():
    doc = json.load(open(os.path.join(FIX, "reject_depth_exceeded.json")))
    assert ("D2", "e3") in findings(normalize("attenu", doc))


# --- descriptor -------------------------------------------------------------

def _descriptor(cred, evidence="logged attestation", gens=None, protected=False):
    if gens is None:
        act = ["data.read", "funds.transfer"] if protected else ["data.read"]
        gens = [
            {"node": "g0", "tools": ["t1"], "actions": list(act),
             "resources": ["db/*"], "caps": [{"name": "spend", "limit": 100}], "purposes": ["read"]},
            {"node": "g1", "tools": ["t1"], "actions": ["data.read"],
             "resources": ["db/*"], "caps": [{"name": "spend", "limit": 50}], "purposes": ["read"]},
            {"node": "g2", "tools": ["t1"], "actions": ["data.read"],
             "resources": ["db/*"], "caps": [{"name": "spend", "limit": 10}], "purposes": ["read"]},
        ]
    return {"framework": "fw", "version": "1", "scenario": "s", "generations": gens,
            "child_credentials": cred, "handoff_evidence": evidence, "source_refs": []}


def test_descriptor_scoped_narrowing_clean():
    g = normalize("descriptor", _descriptor("scoped"))
    assert [e["id"] for e in g["edges"]] == ["e1", "e2", "e3"]
    # scoped: each edge uses its generation's authority; caps narrow -> clean (plus no D8, attestation).
    assert findings(g) == set()


def test_descriptor_inherit_propagates_protected_to_d7():
    # inherit: generation 0's full authority (incl. funds.transfer) propagates down,
    # reaching g2 (T2) via non-root issuer g1.
    assert ("D7", "e3") in findings(normalize("descriptor", _descriptor("inherit", protected=True)))


def test_descriptor_none_is_empty_authority():
    g = normalize("descriptor", _descriptor("none"))
    for e in g["edges"]:
        assert e["authority"]["actions"] == [] and e["authority"]["resources"] == []
    assert findings(g) == set()


def test_descriptor_evidence_none_is_d8():
    g = normalize("descriptor", _descriptor("scoped", evidence="none"))
    assert ("D8", "e1") in findings(g) and ("D8", "e3") in findings(g)


def test_descriptor_bad_child_credentials():
    with pytest.raises(NormalizeError, match="child_credentials"):
        normalize("descriptor", _descriptor("partial"))


def test_descriptor_signed_evidence_kind():
    g = normalize("descriptor", _descriptor("scoped", evidence="signed token"))
    assert g["edges"][0]["evidence"]["kind"] == "signature"


def test_unknown_format():
    with pytest.raises(NormalizeError, match="unknown format"):
        normalize("saml", {})
