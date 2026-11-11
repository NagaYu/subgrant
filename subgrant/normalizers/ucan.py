"""UCAN delegation-chain normalizer (Phase 2 §2.1).

Input: ``{"chain": [<payload>, ...]}`` root first. Each payload:
``{"iss": str, "aud": str, "exp": <unix|null>, "nbf": <unix, optional>,
   "att": [{"with": str, "can": str}], "prf": [<indices>]}``.

Mapping (see reports/phase2.md and DECISIONS D-015):
  * parent of link i = the single index in its ``prf``; root has ``prf: []``.
  * ``issuer = iss``, ``holder = aud``.
  * ``actions`` = sorted set of ``can`` across ``att``.
  * ``resources`` = each ``with`` with a leading ``<scheme>://`` stripped;
    ``"*"`` stays ``"*"``; each result must pass ``validate_pattern``.
  * ``expires_at`` = ``exp`` (null -> null). ``issued_at`` = ``nbf`` if present,
    else inherits the parent link's ``issued_at``; a root with no ``nbf`` gets
    ``2026-01-01T00:00:00Z``.
  * ``redelegation = true``; ``evidence = {"kind":"signature","ref":"ucan:<i>"}``.
  * tools/caps/purposes/data_classes: common-rule constants.
"""

from __future__ import annotations

from typing import Any

from ..graph import load_graph
from ..patterns import PatternError, validate_pattern
from . import (
    CONST_CAPS,
    CONST_DATA_CLASSES,
    CONST_PURPOSES,
    CONST_TOOLS,
    NormalizeError,
    strip_scheme,
    unix_to_ts,
)

ROOT_DEFAULT_ISSUED = "2026-01-01T00:00:00Z"


def normalize(doc: Any) -> dict:
    if not isinstance(doc, dict) or not isinstance(doc.get("chain"), list) or not doc["chain"]:
        raise NormalizeError("ucan: expected {'chain': [<payload>, ...]} non-empty")
    chain = doc["chain"]
    n = len(chain)

    # Validate structure and determine parents.
    parents: list[int | None] = []
    for i, link in enumerate(chain):
        if not isinstance(link, dict):
            raise NormalizeError(f"ucan: link {i} must be an object")
        prf = link.get("prf", [])
        if not isinstance(prf, list):
            raise NormalizeError(f"ucan: link {i} 'prf' must be an array")
        if i == 0:
            if prf:
                raise NormalizeError("ucan: root link (index 0) must have empty 'prf'")
            parents.append(None)
            continue
        if len(prf) != 1:
            raise NormalizeError(
                f"ucan: link {i} must have exactly one proof index, got {prf!r}"
            )
        p = prf[0]
        if not isinstance(p, int) or isinstance(p, bool) or p < 0 or p >= i:
            raise NormalizeError(
                f"ucan: link {i} proof index {p!r} must point at an earlier link"
            )
        parents.append(p)

    issued: list[str] = []
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    for i, link in enumerate(chain):
        iss = link.get("iss")
        aud = link.get("aud")
        if not isinstance(iss, str) or not iss:
            raise NormalizeError(f"ucan: link {i} 'iss' must be a non-empty string")
        if not isinstance(aud, str) or not aud:
            raise NormalizeError(f"ucan: link {i} 'aud' must be a non-empty string")

        att = link.get("att", [])
        if not isinstance(att, list):
            raise NormalizeError(f"ucan: link {i} 'att' must be an array")
        actions: set[str] = set()
        resources: list[str] = []
        seen_res: set[str] = set()
        for cap in att:
            if not isinstance(cap, dict) or "with" not in cap or "can" not in cap:
                raise NormalizeError(f"ucan: link {i} each 'att' entry needs 'with' and 'can'")
            can = cap["can"]
            with_ = cap["with"]
            if not isinstance(can, str) or not isinstance(with_, str):
                raise NormalizeError(f"ucan: link {i} 'with'/'can' must be strings")
            actions.add(can)
            res = strip_scheme(with_)
            try:
                validate_pattern(res)
            except PatternError as exc:
                raise NormalizeError(f"ucan: link {i} resource {with_!r} -> {res!r}: {exc}")
            if res not in seen_res:
                seen_res.add(res)
                resources.append(res)

        # Window.
        exp = link.get("exp", None)
        expires_at = None if exp is None else unix_to_ts(exp, field=f"ucan link {i} exp")
        if "nbf" in link and link["nbf"] is not None:
            issued_at = unix_to_ts(link["nbf"], field=f"ucan link {i} nbf")
        elif parents[i] is None:
            issued_at = ROOT_DEFAULT_ISSUED
        else:
            issued_at = issued[parents[i]]  # inherit parent's issued_at
        issued.append(issued_at)

        # Nodes.
        if iss not in nodes:
            nodes[iss] = {"id": iss, "kind": "agent", "trust_tier": "T2"}
        if aud not in nodes:
            nodes[aud] = {"id": aud, "kind": "agent", "trust_tier": "T2"}
        if parents[i] is None:
            nodes[iss] = {"id": iss, "kind": "human", "trust_tier": "T0"}  # root authority

        parent_edge = None if parents[i] is None else f"e{parents[i] + 1}"
        edges.append({
            "id": f"e{i + 1}",
            "parent_edge": parent_edge,
            "issuer": iss,
            "holder": aud,
            "authority": {
                "tools": list(CONST_TOOLS),
                "actions": sorted(actions),
                "resources": resources,
                "data_classes": list(CONST_DATA_CLASSES),
            },
            "caveats": {
                "issued_at": issued_at,
                "expires_at": expires_at,
                "redelegation": True,
                "caps": list(CONST_CAPS),
                "purposes": list(CONST_PURPOSES),
            },
            "evidence": {"kind": "signature", "ref": f"ucan:{i}"},
        })

    out = {"schema": "dgraph/1", "nodes": list(nodes.values()), "edges": edges}
    load_graph(out)  # guarantee the result is a valid dgraph/1 document
    return out
