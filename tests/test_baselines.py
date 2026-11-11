"""Baseline B0/B2 behavior (Phase 2 §4 / §7)."""

from subgrant.baselines import b0_check, b2_check
from subgrant.checks import load_policy_pack, run_checks
from subgrant.graph import load_graph

from .helpers import edge, node

PACK = load_policy_pack()


def _fanout_d5():
    return {
        "schema": "dgraph/1",
        "nodes": [node("n0", "human", "T0"), node("n1"), node("n2"), node("n3")],
        "edges": [
            edge("e1", None, "n0", "n1", caps=(("spend", 100),)),
            edge("e2", "e1", "n1", "n2", caps=(("spend", 60),)),
            edge("e3", "e1", "n1", "n3", caps=(("spend", 60),)),
        ],
    }


def _d7_chain():
    return {
        "schema": "dgraph/1",
        "nodes": [node("n0", "human", "T0"), node("n1", "agent", "T1"), node("n2", "agent", "T2")],
        "edges": [
            edge("e1", None, "n0", "n1", actions=("data.read", "data.delete")),
            edge("e2", "e1", "n1", "n2", actions=("data.read", "data.delete")),
        ],
    }


def _d1_tools():
    return {
        "schema": "dgraph/1",
        "nodes": [node("n0", "human", "T0"), node("n1"), node("n2")],
        "edges": [
            edge("e1", None, "n0", "n1", tools=("t1",)),
            edge("e2", "e1", "n1", "n2", tools=("t1", "t2")),
        ],
    }


def _classes(findings):
    return {f.cls for f in findings}


def test_b0_misses_d5_fanout():
    g = load_graph(_fanout_d5())
    assert ("D5", "e1") in {(f.cls, f.edge) for f in run_checks(g, PACK)}  # SubGrant catches it
    assert "D5" not in _classes(b0_check(g, PACK))  # B0 does not (no aggregation)


def test_b0_does_not_flag_d7_chain():
    g = load_graph(_d7_chain())
    assert ("D7", "e2") in {(f.cls, f.edge) for f in run_checks(g, PACK)}  # SubGrant catches it
    assert "D7" not in _classes(b0_check(g, PACK))  # B0 has no tier/reachability logic


def test_b0_flags_d1():
    g = load_graph(_d1_tools())
    assert ("D1", "e2") in {(f.cls, f.edge) for f in b0_check(g, PACK)}


def test_b0_misses_d8():
    d = _d1_tools()
    d["edges"][1]["evidence"] = {"kind": "none", "ref": None}
    g = load_graph(d)
    assert "D8" not in _classes(b0_check(g, PACK))  # B0 has no evidence check


# --- B2 (UCAN-spec) ---------------------------------------------------------

def test_b2_catches_scope_widening():
    doc = {"chain": [
        {"iss": "n0", "aud": "n1", "exp": 1000, "att": [{"with": "db/*", "can": "crm/read"}], "prf": []},
        {"iss": "n1", "aud": "n2", "exp": 900, "att": [{"with": "db/*", "can": "pay/transfer"}], "prf": [0]},
    ]}
    assert ("D1", "e2") in {(f.cls, f.edge) for f in b2_check(doc)}


def test_b2_clean_on_narrowing():
    doc = {"chain": [
        {"iss": "n0", "aud": "n1", "exp": 1000, "att": [{"with": "db/*", "can": "crm/*"}], "prf": []},
        {"iss": "n1", "aud": "n2", "exp": 900, "att": [{"with": "db/x", "can": "crm/read"}], "prf": [0]},
    ]}
    assert b2_check(doc) == []  # crm/read under crm/*, db/x under db/*, exp narrows


def test_b2_catches_exp_exceed():
    doc = {"chain": [
        {"iss": "n0", "aud": "n1", "exp": 1000, "att": [{"with": "db/*", "can": "crm/read"}], "prf": []},
        {"iss": "n1", "aud": "n2", "exp": 2000, "att": [{"with": "db/*", "can": "crm/read"}], "prf": [0]},
    ]}
    assert ("D4", "e2") in {(f.cls, f.edge) for f in b2_check(doc)}
