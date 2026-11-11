"""RFC 8693 token-exchange act-chain normalizer (Phase 2 §2.2).

Input: one decoded JWT payload (signatures are not verified — presence only):
``{"iss": str, "sub": str, "exp": <unix>, "iat": <unix>, "scope": "<space-sep>",
   "act": {"sub": str, "scope": "<...>", "act": {...}}}`` (``act`` optional).

Mapping (see reports/phase2.md and DECISIONS D-016):
  * Edges, root first: edge 0 is ``iss -> sub``. Each nested ``act`` adds one
    edge from the previous holder to that ``act``'s ``sub`` (v1 reading: the act
    chain is the delegation chain, outermost = most recent).
  * ``actions`` at each level = that level's ``scope`` split on whitespace;
    a level with no ``scope`` inherits the previous level's actions.
  * All edges share the token window: ``issued_at=iat``, ``expires_at=exp``.
  * ``evidence={"kind":"attestation","ref":"rfc8693:act-chain"}``; ``redelegation=true``.
  * resources (``[]``), caps, purposes, data_classes, tools: common-rule constants.
"""

from __future__ import annotations

from typing import Any

from ..graph import load_graph
from . import (
    CONST_CAPS,
    CONST_DATA_CLASSES,
    CONST_PURPOSES,
    CONST_TOOLS,
    NormalizeError,
    unix_to_ts,
)


def _levels(payload: dict) -> list[tuple[str, Any]]:
    """Flatten the act chain into [(holder_sub, scope_or_None), ...]."""
    out: list[tuple[str, Any]] = []
    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        raise NormalizeError("rfc8693: top-level 'sub' must be a non-empty string")
    out.append((sub, payload.get("scope")))
    cur = payload.get("act")
    depth = 0
    while cur is not None:
        depth += 1
        if not isinstance(cur, dict):
            raise NormalizeError(f"rfc8693: 'act' at depth {depth} must be an object")
        asub = cur.get("sub")
        if not isinstance(asub, str) or not asub:
            raise NormalizeError(f"rfc8693: 'act' at depth {depth} needs a non-empty 'sub'")
        out.append((asub, cur.get("scope")))
        cur = cur.get("act")
    return out


def _actions(scope: Any, *, level: int, prev: set[str] | None) -> set[str]:
    if scope is None:
        if prev is None:
            return set()  # top level with no scope -> empty authority
        return set(prev)
    if not isinstance(scope, str):
        raise NormalizeError(f"rfc8693: 'scope' at level {level} must be a string")
    return set(scope.split())


def normalize(doc: Any) -> dict:
    if not isinstance(doc, dict):
        raise NormalizeError("rfc8693: expected a JWT payload object")
    iss = doc.get("iss")
    if not isinstance(iss, str) or not iss:
        raise NormalizeError("rfc8693: 'iss' must be a non-empty string")
    if "iat" not in doc or "exp" not in doc:
        raise NormalizeError("rfc8693: 'iat' and 'exp' are required")
    issued_at = unix_to_ts(doc["iat"], field="rfc8693 iat")
    exp = doc["exp"]
    expires_at = None if exp is None else unix_to_ts(exp, field="rfc8693 exp")

    levels = _levels(doc)

    nodes: dict[str, dict] = {iss: {"id": iss, "kind": "human", "trust_tier": "T0"}}
    edges: list[dict] = []
    prev_actions: set[str] | None = None
    prev_holder = iss
    for i, (holder, scope) in enumerate(levels):
        actions = _actions(scope, level=i, prev=prev_actions)
        prev_actions = actions
        if holder not in nodes:
            nodes[holder] = {"id": holder, "kind": "agent", "trust_tier": "T2"}
        issuer = prev_holder
        if issuer not in nodes:
            nodes[issuer] = {"id": issuer, "kind": "agent", "trust_tier": "T2"}
        edges.append({
            "id": f"e{i + 1}",
            "parent_edge": None if i == 0 else f"e{i}",
            "issuer": issuer,
            "holder": holder,
            "authority": {
                "tools": list(CONST_TOOLS),
                "actions": sorted(actions),
                "resources": [],
                "data_classes": list(CONST_DATA_CLASSES),
            },
            "caveats": {
                "issued_at": issued_at,
                "expires_at": expires_at,
                "redelegation": True,
                "caps": list(CONST_CAPS),
                "purposes": list(CONST_PURPOSES),
            },
            "evidence": {"kind": "attestation", "ref": "rfc8693:act-chain"},
        })
        prev_holder = holder

    out = {"schema": "dgraph/1", "nodes": list(nodes.values()), "edges": edges}
    load_graph(out)
    return out
