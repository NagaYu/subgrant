"""The D1-D8 delegation checks (pinned definitions, §4 of the Phase 1 spec).

Each finding names a check class and the edge id the pinned definition points
at. Checks run over a validated :class:`~subgrant.graph.Graph`; root edges skip
the parent-relative checks (D1, D3, D4, D6).
"""

from __future__ import annotations

import json
import os
from typing import Any

from .graph import Graph, Edge
from .patterns import set_subset

_DEFAULT_PACK_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "packs",
    "delegation-policy-v1.json",
)


class Finding:
    """A single check result: a class label plus the edge it is reported on."""

    __slots__ = ("cls", "edge")

    def __init__(self, cls: str, edge: str) -> None:
        self.cls = cls
        self.edge = edge

    def as_dict(self) -> dict[str, str]:
        return {"class": self.cls, "edge": self.edge}

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Finding) and other.cls == self.cls and other.edge == self.edge
        )

    def __hash__(self) -> int:
        return hash((self.cls, self.edge))

    def __repr__(self) -> str:
        return f"Finding({self.cls!r}, {self.edge!r})"


def load_policy_pack(path: str | None = None) -> dict[str, Any]:
    """Load a policy pack JSON. Defaults to ``packs/delegation-policy-v1.json``."""
    with open(path or _DEFAULT_PACK_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def effective_budget(graph: Graph, pack: dict[str, Any]) -> int:
    """Pack ``max_depth`` tightened by the root edge's ``depth_budget`` (min)."""
    budget = int(pack["max_depth"])
    if graph.root.depth_budget is not None:
        budget = min(budget, graph.root.depth_budget)
    return budget


def _window_contained(child: Edge, parent: Edge) -> bool:
    """Child window subset-of parent window (§3)."""
    if child.issued_at < parent.issued_at:
        return False
    if parent.expires_at is None:
        return True
    if child.expires_at is None:
        return False
    return child.expires_at <= parent.expires_at


# --- Individual per-edge predicates (used by checks and by D5's gating) -------

def _d1_amplifies(e: Edge, p: Edge) -> bool:
    if not e.tools <= p.tools:
        return True
    if not e.actions <= p.actions:
        return True
    if not e.data_classes <= p.data_classes:
        return True
    if not set_subset(e.resources, p.resources):
        return True
    return False


def _d6_weakens(e: Edge, p: Edge) -> bool:
    for name, plimit in p.caps.items():
        if name not in e.caps:
            return True  # cap present in parent, absent in child
        if e.caps[name] > plimit:
            return True  # same-name cap raised
    if not e.purposes <= p.purposes:
        return True
    return False


def run_checks(graph: Graph, pack: dict[str, Any] | None = None) -> list[Finding]:
    """Run D1-D8 and return findings in a deterministic order."""
    if pack is None:
        pack = load_policy_pack()
    protected = frozenset(pack.get("protected_actions", []))
    budget = effective_budget(graph, pack)
    root_issuer = graph.root.issuer

    findings: list[Finding] = []
    order_index = {eid: i for i, eid in enumerate(graph.order)}

    for eid in graph.order:
        e = graph.edges[eid]
        p = graph.parent_of(e)

        # Parent-relative checks (skip for root).
        if p is not None:
            if _d1_amplifies(e, p):
                findings.append(Finding("D1", e.id))
            if p.redelegation is False:
                findings.append(Finding("D3", e.id))  # D3: parent forbids re-delegation
            if not _window_contained(e, p):
                findings.append(Finding("D4", e.id))
            if _d6_weakens(e, p):
                findings.append(Finding("D6", e.id))

        # Whole-graph / absolute checks (apply to every edge, root included).
        if graph.depth[e.id] > budget:
            findings.append(Finding("D2", e.id))
        if (e.actions & protected) and graph.trust_tier(e.holder) in ("T2", "T3") and e.issuer != root_issuer:
            findings.append(Finding("D7", e.id))
        if e.evidence_kind == "none":
            findings.append(Finding("D8", e.id))

    # D5 Fan-out recombination: on each parent with >= 2 children, when every
    # child individually passes D1 and D6, and some cap's child-sum exceeds the
    # parent's limit for it.
    for pid in graph.order:
        p = graph.edges[pid]
        kids = graph.children[pid]
        if len(kids) < 2:
            continue
        if any(_d1_amplifies(c, p) or _d6_weakens(c, p) for c in kids):
            continue  # a child already fails D1/D6; D5 does not fire
        fired = False
        for name, plimit in p.caps.items():
            total = 0.0
            for c in kids:
                # Child omitting the cap consumes the parent's full limit.
                total += c.caps.get(name, plimit)
            if total > plimit:
                fired = True
                break
        if fired:
            findings.append(Finding("D5", p.id))

    findings.sort(key=lambda f: (order_index.get(f.edge, 1 << 30), f.cls))
    return findings
