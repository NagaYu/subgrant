"""Baseline verifiers scored against SubGrant on the same graphs (Phase 2 §4).

B0 — a naive per-edge subset checker (no fan-out aggregation, no tier/
reachability logic, no evidence check, depth vs the pack's ``max_depth`` only).
By construction it has recall 0 on D5 and D7, misses D2 cases planted via a root
``depth_budget``, and misses all D8.

B2 — a minimal UCAN 1.0 attenuation checker over UCAN payload chains directly
(not over ``dgraph/1``). It catches D1-analogues (scope/ability/resource
widening) and a D4-analogue (``exp`` exceeding the parent), and has no concept
of D5/D7/D8.
"""

from __future__ import annotations

from typing import Any

from .checks import Finding
from .graph import Graph
from .patterns import is_subsumed, set_subset


# --------------------------------------------------------------------------- #
# B0 — naive per-edge subset checker (operates on a dgraph/1 Graph)
# --------------------------------------------------------------------------- #

def b0_check(graph: Graph, pack: dict[str, Any]) -> list[Finding]:
    max_depth = int(pack["max_depth"])  # note: ignores the root's depth_budget
    findings: list[Finding] = []
    order_index = {eid: i for i, eid in enumerate(graph.order)}

    for eid in graph.order:
        e = graph.edges[eid]
        p = graph.parent_of(e)
        if p is not None:
            if (
                not e.tools <= p.tools
                or not e.actions <= p.actions
                or not e.data_classes <= p.data_classes
                or not set_subset(e.resources, p.resources)
            ):
                findings.append(Finding("D1", e.id))
            if p.redelegation is False:
                findings.append(Finding("D3", e.id))
            if not _window_contained(e, p):
                findings.append(Finding("D4", e.id))
            # D6 cap + purpose clauses only (naive: per-edge, no aggregation).
            weak = False
            for name, plimit in p.caps.items():
                if name not in e.caps or e.caps[name] > plimit:
                    weak = True
                    break
            if weak or not e.purposes <= p.purposes:
                findings.append(Finding("D6", e.id))
        # Depth vs the pack max_depth only (no root depth_budget tightening).
        if graph.depth[e.id] > max_depth:
            findings.append(Finding("D2", e.id))
        # No D5 (no fan-out aggregation), no D7 (no tier/reachability), no D8.

    findings.sort(key=lambda f: (order_index.get(f.edge, 1 << 30), f.cls))
    return findings


def _window_contained(child, parent) -> bool:
    if child.issued_at < parent.issued_at:
        return False
    if parent.expires_at is None:
        return True
    if child.expires_at is None:
        return False
    return child.expires_at <= parent.expires_at


# --------------------------------------------------------------------------- #
# B2 — UCAN 1.0 attenuation checker (operates on a UCAN payload chain)
# --------------------------------------------------------------------------- #

def _ability_covered(child_can: str, parent_cans: list[str]) -> bool:
    for pc in parent_cans:
        if pc == "*" or pc == child_can:
            return True
        if child_can.startswith(pc + "/"):  # parent ability is a path prefix
            return True
        if pc.endswith("/*") and (child_can == pc[:-2] or child_can.startswith(pc[:-1])):
            return True
    return False


def _with_covered(child_with: str, parent_withs: list[str]) -> bool:
    return any(is_subsumed(child_with, pw) for pw in parent_withs)


def b2_check(ucan_doc: dict) -> list[Finding]:
    """Check a ``{"chain": [...]}`` UCAN payload chain under UCAN 1.0 attenuation.

    Returns findings labeled with the SubGrant class they correspond to
    (``D1`` for scope/ability/resource widening, ``D4`` for an ``exp`` that
    exceeds the parent's). Edge ids are ``e{i+1}`` for link ``i``.
    """
    chain = ucan_doc["chain"]
    findings: list[Finding] = []
    for i, link in enumerate(chain):
        prf = link.get("prf", [])
        if i == 0 or not prf:
            continue
        parent = chain[prf[0]]
        p_att = parent.get("att", [])
        p_cans = [a["can"] for a in p_att]
        p_withs = [a["with"] for a in p_att]
        c_att = link.get("att", [])

        widened = False
        for cap in c_att:
            if not _ability_covered(cap["can"], p_cans):
                widened = True
            if not _with_covered(cap["with"], p_withs):
                widened = True
        if widened:
            findings.append(Finding("D1", f"e{i + 1}"))

        c_exp = link.get("exp", None)
        p_exp = parent.get("exp", None)
        if p_exp is not None and (c_exp is None or c_exp > p_exp):
            findings.append(Finding("D4", f"e{i + 1}"))

    return findings
