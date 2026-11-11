"""attenu-guard Delegation-Token-chain normalizer (Phase 2 §2.3).

Mapping table derived from the vendored attenu-guard material
(`fixtures/attenu/`, see PROVENANCE.md) — the IETF draft and interop test
vectors. attenu-guard serializes a delegation chain as a list of compact JWS
"Delegation Tokens" (DT). Input to this normalizer is a vector/bundle object::

    {"tokens": ["<header>.<payload>.<sig>", ...], "signer": {...}, "now": N, ...}

Only the token PAYLOADS are read; signatures are NOT verified (presence-only,
consistent with v1 / D8). Each decoded payload carries:
``iss, sub, iat, exp, jti, del_depth, del_max_depth? , par_hash?,
authorization_details:[{type:"agent_delegation", scopes:[...], constraints:[...]}]``.

Mapping (recorded in DECISIONS D-017):
  * One edge per token, ordered root-first by ``del_depth`` (0..n-1, linear).
  * Root authority node = ``iss`` (human/T0). Edge for del_depth 0: issuer=iss,
    holder=sub0. Edge for del_depth k>0: issuer=sub[k-1], holder=sub[k] (T2).
  * ``scopes`` -> ``resources``, translating the dotted/wildcard scope grammar to
    the dgraph pattern grammar: ``.`` -> ``/`` (so ``crm.*`` -> ``crm/*``,
    ``crm.read`` -> ``crm/read``); each result must pass ``validate_pattern``.
    This lets SubGrant's resource subsumption model scope narrowing faithfully.
  * ``actions`` and ``tools`` = [] (scopes are modeled as resources).
  * ``constraints`` of the numeric ``max`` form -> a cap ``{name:key, limit:max}``;
    other constraint kinds (rank/min/one_of/prefix) are ignored in v1.
  * root ``del_max_depth`` -> root ``depth_budget``.
  * ``iat``/``exp`` -> window (unix seconds; exp null -> unbounded).
  * ``evidence = {"kind":"signature","ref":"attenu:<jti>"}`` (DTs are JWS-signed).
  * purposes/data_classes: common-rule constants; redelegation=true.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from ..graph import load_graph
from ..patterns import PatternError, validate_pattern
from . import CONST_DATA_CLASSES, CONST_PURPOSES, NormalizeError


def _b64url_json(segment: str, *, field: str) -> dict:
    pad = "=" * (-len(segment) % 4)
    try:
        raw = base64.urlsafe_b64decode(segment + pad)
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise NormalizeError(f"attenu: {field}: cannot decode token payload: {exc}")


def _scope_to_resource(scope: str) -> str:
    if not isinstance(scope, str) or not scope:
        raise NormalizeError(f"attenu: scope must be a non-empty string, got {scope!r}")
    res = scope.replace(".", "/")
    try:
        validate_pattern(res)
    except PatternError as exc:
        raise NormalizeError(f"attenu: scope {scope!r} -> {res!r}: {exc}")
    return res


def _authority_from_payload(payload: dict, *, idx: int):
    details = payload.get("authorization_details", [])
    if not isinstance(details, list):
        raise NormalizeError(f"attenu: token {idx} 'authorization_details' must be an array")
    resources: list[str] = []
    seen: set[str] = set()
    caps: dict[str, float] = {}
    for d in details:
        if not isinstance(d, dict):
            raise NormalizeError(f"attenu: token {idx} authorization_details entry must be an object")
        for scope in d.get("scopes", []):
            res = _scope_to_resource(scope)
            if res not in seen:
                seen.add(res)
                resources.append(res)
        for con in d.get("constraints", []):
            if isinstance(con, dict) and isinstance(con.get("key"), str) and "max" in con:
                limit = con["max"]
                if isinstance(limit, (int, float)) and not isinstance(limit, bool):
                    caps[con["key"]] = limit
    return resources, [{"name": k, "limit": v} for k, v in caps.items()]


def normalize(doc: Any) -> dict:
    if not isinstance(doc, dict) or not isinstance(doc.get("tokens"), list) or not doc["tokens"]:
        raise NormalizeError("attenu: expected {'tokens': [<compact JWS>, ...]} non-empty")

    decoded = []
    for i, tok in enumerate(doc["tokens"]):
        if not isinstance(tok, str) or tok.count(".") != 2:
            raise NormalizeError(f"attenu: token {i} must be a compact JWS 'h.p.s'")
        payload = _b64url_json(tok.split(".")[1], field=f"token {i}")
        decoded.append(payload)

    # Order root-first by del_depth; require exactly 0..n-1.
    for i, p in enumerate(decoded):
        if not isinstance(p.get("del_depth"), int) or isinstance(p.get("del_depth"), bool):
            raise NormalizeError(f"attenu: token {i} missing integer 'del_depth'")
    decoded.sort(key=lambda p: p["del_depth"])
    depths = [p["del_depth"] for p in decoded]
    if depths != list(range(len(decoded))):
        raise NormalizeError(f"attenu: del_depth sequence must be 0..n-1, got {depths}")

    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    prev_holder = None
    for i, p in enumerate(decoded):
        sub = p.get("sub")
        if not isinstance(sub, str) or not sub:
            raise NormalizeError(f"attenu: token {i} missing non-empty 'sub'")
        iat = p.get("iat")
        exp = p.get("exp", None)
        if iat is None:
            raise NormalizeError(f"attenu: token {i} missing 'iat'")
        from . import unix_to_ts

        issued_at = unix_to_ts(iat, field=f"attenu token {i} iat")
        expires_at = None if exp is None else unix_to_ts(exp, field=f"attenu token {i} exp")
        resources, caps = _authority_from_payload(p, idx=i)

        if i == 0:
            iss = p.get("iss")
            if not isinstance(iss, str) or not iss:
                raise NormalizeError("attenu: root token missing non-empty 'iss'")
            issuer = iss
            nodes[iss] = {"id": iss, "kind": "human", "trust_tier": "T0"}
            depth_budget = p.get("del_max_depth")
            if depth_budget is not None and (not isinstance(depth_budget, int) or isinstance(depth_budget, bool) or depth_budget < 1):
                raise NormalizeError("attenu: root 'del_max_depth' must be a positive integer")
        else:
            issuer = prev_holder
            depth_budget = None
        if sub not in nodes:
            nodes[sub] = {"id": sub, "kind": "agent", "trust_tier": "T2"}

        caveats = {
            "issued_at": issued_at,
            "expires_at": expires_at,
            "redelegation": True,
            "caps": caps,
            "purposes": list(CONST_PURPOSES),
        }
        if i == 0 and depth_budget is not None:
            caveats["depth_budget"] = depth_budget

        jti = p.get("jti", f"dt{i}")
        edges.append({
            "id": f"e{i + 1}",
            "parent_edge": None if i == 0 else f"e{i}",
            "issuer": issuer,
            "holder": sub,
            "authority": {
                "tools": [],
                "actions": [],
                "resources": resources,
                "data_classes": list(CONST_DATA_CLASSES),
            },
            "caveats": caveats,
            "evidence": {"kind": "signature", "ref": f"attenu:{jti}"},
        })
        prev_holder = sub

    out = {"schema": "dgraph/1", "nodes": list(nodes.values()), "edges": edges}
    load_graph(out)
    return out
