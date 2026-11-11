"""Small builders for constructing dgraph/1 documents in tests."""

from __future__ import annotations

import copy


def node(nid, kind="agent", tier="T1"):
    return {"id": nid, "kind": kind, "trust_tier": tier}


def edge(
    eid, parent, issuer, holder, *,
    tools=("tool.read",), actions=("data.read",), resources=("db/x/*",),
    data_classes=("internal",), issued_at="2026-01-01T00:00:00Z",
    expires_at="2026-06-01T00:00:00Z", redelegation=True, purposes=("read",),
    caps=(("spend_usd", 100),), evidence_kind="attestation", evidence_ref="att:1",
    depth_budget=None,
):
    caveats = {
        "issued_at": issued_at,
        "expires_at": expires_at,
        "redelegation": redelegation,
        "caps": [{"name": n, "limit": l} for n, l in caps],
        "purposes": list(purposes),
    }
    if depth_budget is not None:
        caveats["depth_budget"] = depth_budget
    ref = None if evidence_kind == "none" else evidence_ref
    return {
        "id": eid,
        "parent_edge": parent,
        "issuer": issuer,
        "holder": holder,
        "authority": {
            "tools": list(tools),
            "actions": list(actions),
            "resources": list(resources),
            "data_classes": list(data_classes),
        },
        "caveats": caveats,
        "evidence": {"kind": evidence_kind, "ref": ref},
    }


def base_chain():
    """A clean 2-edge chain (root e1 -> child e2), equal restatement."""
    return {
        "schema": "dgraph/1",
        "nodes": [node("n0", "human", "T0"), node("n1"), node("n2")],
        "edges": [
            edge("e1", None, "n0", "n1"),
            edge("e2", "e1", "n1", "n2"),
        ],
    }


def clone(d):
    return copy.deepcopy(d)
