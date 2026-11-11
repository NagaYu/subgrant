"""Graph loading, window containment, and input-error handling."""

import pytest

from subgrant.checks import _window_contained
from subgrant.graph import GraphError, load_graph

from .helpers import base_chain, clone, edge, node


def _edges_by_id(graph):
    return graph.edges


# --- window containment (§3) ------------------------------------------------

@pytest.mark.parametrize(
    "c_iss,c_exp,p_iss,p_exp,expected",
    [
        # equal windows -> contained
        ("2026-01-01T00:00:00Z", "2026-06-01T00:00:00Z", "2026-01-01T00:00:00Z", "2026-06-01T00:00:00Z", True),
        # child starts later, ends earlier -> contained
        ("2026-02-01T00:00:00Z", "2026-05-01T00:00:00Z", "2026-01-01T00:00:00Z", "2026-06-01T00:00:00Z", True),
        # child starts before parent -> not contained
        ("2025-12-01T00:00:00Z", "2026-05-01T00:00:00Z", "2026-01-01T00:00:00Z", "2026-06-01T00:00:00Z", False),
        # child ends after parent -> not contained
        ("2026-01-01T00:00:00Z", "2026-07-01T00:00:00Z", "2026-01-01T00:00:00Z", "2026-06-01T00:00:00Z", False),
        # parent unbounded, child bounded -> contained
        ("2026-01-01T00:00:00Z", "2026-06-01T00:00:00Z", "2026-01-01T00:00:00Z", None, True),
        # parent unbounded, child unbounded -> contained
        ("2026-01-01T00:00:00Z", None, "2026-01-01T00:00:00Z", None, True),
        # parent bounded, child unbounded -> not contained
        ("2026-01-01T00:00:00Z", None, "2026-01-01T00:00:00Z", "2026-06-01T00:00:00Z", False),
    ],
)
def test_window_containment(c_iss, c_exp, p_iss, p_exp, expected):
    d = base_chain()
    d["edges"][0] = edge("e1", None, "n0", "n1", issued_at=p_iss, expires_at=p_exp)
    d["edges"][1] = edge("e2", "e1", "n1", "n2", issued_at=c_iss, expires_at=c_exp)
    g = load_graph(d)
    assert _window_contained(g.edges["e2"], g.edges["e1"]) is expected


# --- valid load -------------------------------------------------------------

def test_load_valid_sets_depth_and_root():
    g = load_graph(base_chain())
    assert g.root.id == "e1"
    assert g.depth == {"e1": 1, "e2": 2}
    assert g.children["e1"][0].id == "e2"


def test_duplicate_resource_patterns_deduped():
    d = base_chain()
    d["edges"][0]["authority"]["resources"] = ["db/x/*", "db/x/*"]
    g = load_graph(d)
    assert g.edges["e1"].resources == ["db/x/*"]


# --- input errors (exit 2 class) --------------------------------------------

def test_two_roots():
    d = base_chain()
    d["edges"][1]["parent_edge"] = None  # now two roots
    with pytest.raises(GraphError, match="exactly one root"):
        load_graph(d)


def test_zero_roots():
    d = base_chain()
    d["edges"][0]["parent_edge"] = "e2"  # cycle-ish, but first: no null root
    with pytest.raises(GraphError):
        load_graph(d)


def test_dangling_parent():
    d = base_chain()
    d["edges"][1]["parent_edge"] = "e999"
    with pytest.raises(GraphError, match="missing edge"):
        load_graph(d)


def test_duplicate_edge_id():
    d = base_chain()
    d["edges"].append(edge("e2", "e1", "n1", "n2"))
    with pytest.raises(GraphError, match="duplicate id"):
        load_graph(d)


def test_cycle():
    d = {
        "schema": "dgraph/1",
        "nodes": [node("n0", "human", "T0"), node("n1"), node("n2")],
        "edges": [
            edge("e1", None, "n0", "n1"),
            edge("e2", "e3", "n1", "n2"),
            edge("e3", "e2", "n2", "n1"),
        ],
    }
    with pytest.raises(GraphError, match="cycle"):
        load_graph(d)


def test_bad_pattern_is_input_error():
    d = base_chain()
    d["edges"][0]["authority"]["resources"] = ["db/*/x"]
    with pytest.raises(GraphError, match="illegal resource pattern"):
        load_graph(d)


def test_bad_data_class_enum():
    d = base_chain()
    d["edges"][0]["authority"]["data_classes"] = ["top-secret"]
    with pytest.raises(GraphError, match="not in"):
        load_graph(d)


def test_bad_purpose_enum():
    d = base_chain()
    d["edges"][0]["caveats"]["purposes"] = ["read", "ponder"]
    with pytest.raises(GraphError, match="not in"):
        load_graph(d)


def test_bad_timestamp():
    d = base_chain()
    d["edges"][0]["caveats"]["issued_at"] = "2026-01-01 00:00:00"
    with pytest.raises(GraphError, match="YYYY-MM-DD"):
        load_graph(d)


def test_depth_budget_only_on_root():
    d = base_chain()
    d["edges"][1]["caveats"]["depth_budget"] = 3
    with pytest.raises(GraphError, match="only the root edge"):
        load_graph(d)


def test_evidence_ref_required_when_signed():
    d = base_chain()
    d["edges"][1]["evidence"] = {"kind": "signature", "ref": None}
    with pytest.raises(GraphError, match="non-empty string when kind"):
        load_graph(d)


def test_unknown_issuer_node():
    d = base_chain()
    d["edges"][1]["issuer"] = "ghost"
    with pytest.raises(GraphError, match="not a declared node"):
        load_graph(d)


def test_duplicate_cap_name():
    d = base_chain()
    d["edges"][0]["caveats"]["caps"] = [{"name": "spend_usd", "limit": 100}, {"name": "spend_usd", "limit": 50}]
    with pytest.raises(GraphError, match="duplicate cap name"):
        load_graph(d)


def test_bad_schema_tag():
    d = base_chain()
    d["schema"] = "dgraph/2"
    with pytest.raises(GraphError, match="schema"):
        load_graph(d)
