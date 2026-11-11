"""Each D-class with a positive and a negative case (§4), plus D5 conventions."""

from subgrant.checks import load_policy_pack, run_checks
from subgrant.graph import load_graph

from .helpers import base_chain, edge, node

PACK = load_policy_pack()


def findings_of(doc):
    g = load_graph(doc)
    return {(f.cls, f.edge) for f in run_checks(g, PACK)}


# --- D1 amplification --------------------------------------------------------

def test_d1_positive_tool():
    d = base_chain()
    d["edges"][1]["authority"]["tools"] = ["tool.read", "tool.write"]  # parent has only tool.read
    assert ("D1", "e2") in findings_of(d)


def test_d1_positive_resource():
    d = base_chain()
    d["edges"][1]["authority"]["resources"] = ["db/x/*", "logs/*"]
    assert ("D1", "e2") in findings_of(d)


def test_d1_negative_restatement():
    assert findings_of(base_chain()) == set()


def test_d1_negative_tightened_resource():
    d = base_chain()
    d["edges"][0]["authority"]["resources"] = ["db/*"]
    d["edges"][1]["authority"]["resources"] = ["db/x/*"]  # subsumed by db/*
    assert ("D1", "e2") not in findings_of(d)


# --- D2 depth breach ---------------------------------------------------------

def test_d2_positive():
    d = base_chain()
    d["edges"][0]["caveats"]["depth_budget"] = 1  # effective budget 1
    assert ("D2", "e2") in findings_of(d)


def test_d2_negative():
    d = base_chain()
    d["edges"][0]["caveats"]["depth_budget"] = 6
    assert not any(c == "D2" for c, _ in findings_of(d))


# --- D3 re-delegation breach -------------------------------------------------

def test_d3_positive():
    d = base_chain()
    d["edges"][0]["caveats"]["redelegation"] = False
    assert ("D3", "e2") in findings_of(d)


def test_d3_negative():
    d = base_chain()
    d["edges"][0]["caveats"]["redelegation"] = True
    assert not any(c == "D3" for c, _ in findings_of(d))


# --- D4 lifetime breach ------------------------------------------------------

def test_d4_positive_extends():
    d = base_chain()
    d["edges"][1]["caveats"]["expires_at"] = "2026-07-01T00:00:00Z"  # parent ends 2026-06-01
    assert ("D4", "e2") in findings_of(d)


def test_d4_negative():
    assert not any(c == "D4" for c, _ in findings_of(base_chain()))


# --- D5 fan-out recombination ------------------------------------------------

def _fanout(child_caps):
    """Root e1 (cap 100) with two children carrying the given caps lists."""
    d = {
        "schema": "dgraph/1",
        "nodes": [node("n0", "human", "T0"), node("n1"), node("n2"), node("n3")],
        "edges": [
            edge("e1", None, "n0", "n1", caps=(("spend_usd", 100),)),
            edge("e2", "e1", "n1", "n2", caps=child_caps[0]),
            edge("e3", "e1", "n1", "n3", caps=child_caps[1]),
        ],
    }
    return d


def test_d5_positive():
    d = _fanout([(("spend_usd", 60),), (("spend_usd", 60),)])  # sum 120 > 100
    assert ("D5", "e1") in findings_of(d)


def test_d5_negative_within_bound():
    d = _fanout([(("spend_usd", 40),), (("spend_usd", 50),)])  # sum 90 <= 100
    assert not any(c == "D5" for c, _ in findings_of(d))


def test_d5_missing_cap_convention_blocked_by_d6():
    # A child that omits a parent cap would consume the full limit under D5's
    # convention, but omitting the cap is itself a D6 weakening, so that child
    # fails D6 and D5 does not fire (per the pinned gate "every child passes D1/D6").
    d = _fanout([(("spend_usd", 60),), ()])  # second child drops the cap
    fs = findings_of(d)
    assert ("D6", "e3") in fs
    assert not any(c == "D5" for c, _ in fs)


def test_d5_single_child_never_fires():
    d = base_chain()
    d["edges"][0]["caveats"]["caps"] = [{"name": "spend_usd", "limit": 100}]
    d["edges"][1]["caveats"]["caps"] = [{"name": "spend_usd", "limit": 100}]
    assert not any(c == "D5" for c, _ in findings_of(d))


# --- D6 caveat drop / weakening ---------------------------------------------

def test_d6_positive_cap_raised():
    d = base_chain()
    d["edges"][1]["caveats"]["caps"] = [{"name": "spend_usd", "limit": 150}]
    assert ("D6", "e2") in findings_of(d)


def test_d6_positive_cap_dropped():
    d = base_chain()
    d["edges"][1]["caveats"]["caps"] = []
    assert ("D6", "e2") in findings_of(d)


def test_d6_positive_purpose_widened():
    d = base_chain()
    d["edges"][0]["caveats"]["purposes"] = ["read"]
    d["edges"][1]["caveats"]["purposes"] = ["read", "write"]
    assert ("D6", "e2") in findings_of(d)


def test_d6_negative_tightened():
    d = base_chain()
    d["edges"][0]["caveats"]["caps"] = [{"name": "spend_usd", "limit": 100}]
    d["edges"][0]["caveats"]["purposes"] = ["read", "write"]
    d["edges"][1]["caveats"]["caps"] = [{"name": "spend_usd", "limit": 50}]
    d["edges"][1]["caveats"]["purposes"] = ["read"]
    assert not any(c == "D6" for c, _ in findings_of(d))


# --- D7 confused-deputy reachability ----------------------------------------

def test_d7_positive():
    d = base_chain()
    # protected action present on root and child; child holder T2, issuer n1 (not root)
    d["nodes"][2]["trust_tier"] = "T2"
    d["edges"][0]["authority"]["actions"] = ["data.read", "data.delete"]
    d["edges"][1]["authority"]["actions"] = ["data.read", "data.delete"]
    assert ("D7", "e2") in findings_of(d)


def test_d7_negative_root_issuer():
    # Root issues the protected action directly to a T2 holder -> allowed (issuer is root).
    d = {
        "schema": "dgraph/1",
        "nodes": [node("n0", "human", "T0"), node("n1", "agent", "T2")],
        "edges": [edge("e1", None, "n0", "n1", actions=("data.read", "data.delete"))],
    }
    assert not any(c == "D7" for c, _ in findings_of(d))


def test_d7_negative_trusted_tier():
    d = base_chain()  # holder n1/n2 are T1
    d["edges"][0]["authority"]["actions"] = ["data.read", "data.delete"]
    d["edges"][1]["authority"]["actions"] = ["data.read", "data.delete"]
    assert not any(c == "D7" for c, _ in findings_of(d))


# --- D8 unbound delegation ---------------------------------------------------

def test_d8_positive():
    d = base_chain()
    d["edges"][1]["evidence"] = {"kind": "none", "ref": None}
    assert ("D8", "e2") in findings_of(d)


def test_d8_negative():
    assert not any(c == "D8" for c, _ in findings_of(base_chain()))
