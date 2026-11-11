"""Framework handoff-descriptor normalizer (Phase 2 §2.4).

Input::

    {"framework": str, "version": str, "scenario": str,
     "generations": [{"node": str, "tools": [], "actions": [], "resources": [],
                      "caps": [{"name","limit"}], "purposes": []}, ...],
     "child_credentials": "inherit" | "scoped" | "none",
     "handoff_evidence": "signed token" | "logged attestation" | "none",
     "source_refs": [urls]}

Mapping (see reports/phase2.md and DECISIONS D-018):
  * One edge per generation step; generation 0's node is the root authority, and
    the root edge is ``gen0 -> gen0`` (the root authority holding its authority).
    Edge i (i>0) is ``gen[i-1] -> gen[i]``.
  * Edge authority: ``inherit`` -> the parent edge's authority verbatim (so the
    full root authority propagates down); ``scoped`` -> generation i's listed
    authority; ``none`` -> empty authority.
  * Windows: every edge ``issued_at="2026-01-01T00:00:00Z"``, ``expires_at=null``;
    ``depth_budget`` absent; ``redelegation=true``.
  * ``evidence.kind``: "signed token"->signature, "logged attestation"->attestation,
    "none"->none (ref ``descriptor:<framework>`` when not none).
  * ``data_classes``: common-rule constant ``["internal"]``.

The §2.4 contract shows 2 or 3 generations (the Part B scenario); this
normalizer accepts any N>=1 linear generations (DECISIONS D-018), which is what
lets dev_ext represent chains of other lengths.
"""

from __future__ import annotations

from typing import Any

from ..graph import load_graph
from ..patterns import PatternError, validate_pattern
from . import CONST_DATA_CLASSES, NormalizeError

FIXED_ISSUED = "2026-01-01T00:00:00Z"
_CRED = {"inherit", "scoped", "none"}
_EVIDENCE = {"signed token": "signature", "logged attestation": "attestation", "none": "none"}


def _authority_of(gen: dict, *, idx: int) -> dict:
    tools = gen.get("tools", [])
    actions = gen.get("actions", [])
    resources = gen.get("resources", [])
    caps = gen.get("caps", [])
    purposes = gen.get("purposes", [])
    for name, val in (("tools", tools), ("actions", actions), ("resources", resources), ("purposes", purposes)):
        if not isinstance(val, list) or any(not isinstance(x, str) for x in val):
            raise NormalizeError(f"descriptor: generation {idx} '{name}' must be a string array")
    for r in resources:
        try:
            validate_pattern(r)
        except PatternError as exc:
            raise NormalizeError(f"descriptor: generation {idx} resource {r!r}: {exc}")
    if not isinstance(caps, list):
        raise NormalizeError(f"descriptor: generation {idx} 'caps' must be an array")
    for c in caps:
        if not isinstance(c, dict) or not isinstance(c.get("name"), str) or not isinstance(
            c.get("limit"), (int, float)
        ) or isinstance(c.get("limit"), bool):
            raise NormalizeError(f"descriptor: generation {idx} cap must be {{name, limit}}")
    return {
        "tools": sorted(set(tools)),
        "actions": sorted(set(actions)),
        "resources": list(resources),
        "data_classes": list(CONST_DATA_CLASSES),
    }, [{"name": c["name"], "limit": c["limit"]} for c in caps], sorted(set(purposes))


def _empty_authority():
    return (
        {"tools": [], "actions": [], "resources": [], "data_classes": list(CONST_DATA_CLASSES)},
        [],
        [],
    )


def normalize(doc: Any) -> dict:
    if not isinstance(doc, dict):
        raise NormalizeError("descriptor: expected an object")
    gens = doc.get("generations")
    if not isinstance(gens, list) or not gens:
        raise NormalizeError("descriptor: 'generations' must be a non-empty array")
    cred = doc.get("child_credentials")
    if cred not in _CRED:
        raise NormalizeError(f"descriptor: 'child_credentials' must be one of {sorted(_CRED)}")
    hoe = doc.get("handoff_evidence")
    if hoe not in _EVIDENCE:
        raise NormalizeError(f"descriptor: 'handoff_evidence' must be one of {sorted(_EVIDENCE)}")
    framework = doc.get("framework", "unknown")
    if not isinstance(framework, str) or not framework:
        raise NormalizeError("descriptor: 'framework' must be a non-empty string")

    nodes_in: list[str] = []
    for i, g in enumerate(gens):
        if not isinstance(g, dict) or not isinstance(g.get("node"), str) or not g["node"]:
            raise NormalizeError(f"descriptor: generation {i} needs a non-empty 'node'")
        nodes_in.append(g["node"])

    evid_kind = _EVIDENCE[hoe]
    evidence = (
        {"kind": "none", "ref": None}
        if evid_kind == "none"
        else {"kind": evid_kind, "ref": f"descriptor:{framework}"}
    )

    def authority_tuple(idx):
        if cred == "none":
            return _empty_authority()
        return _authority_of(gens[idx], idx=idx)

    edges: list[dict] = []
    prev_tuple = None
    for i in range(len(gens)):
        if cred == "inherit":
            auth, caps, purposes = authority_tuple(0) if i == 0 else prev_tuple
        else:  # scoped or none
            auth, caps, purposes = authority_tuple(i)
        prev_tuple = (auth, caps, purposes)

        issuer = nodes_in[0] if i == 0 else nodes_in[i - 1]
        holder = nodes_in[i]
        edges.append({
            "id": f"e{i + 1}",
            "parent_edge": None if i == 0 else f"e{i}",
            "issuer": issuer,
            "holder": holder,
            "authority": auth,
            "caveats": {
                "issued_at": FIXED_ISSUED,
                "expires_at": None,
                "redelegation": True,
                "caps": caps,
                "purposes": purposes,
            },
            "evidence": dict(evidence),
        })

    # Nodes: generation 0's node is the root authority (human/T0); others agent/T2.
    nodes: dict[str, dict] = {}
    for i, nid in enumerate(nodes_in):
        if nid in nodes:
            continue
        if i == 0:
            nodes[nid] = {"id": nid, "kind": "human", "trust_tier": "T0"}
        else:
            nodes[nid] = {"id": nid, "kind": "agent", "trust_tier": "T2"}

    out = {"schema": "dgraph/1", "nodes": list(nodes.values()), "edges": edges}
    load_graph(out)
    return out
