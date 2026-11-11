"""Deterministic dev-bench generator for SubGrant (Phase 1, §5).

Python standard library only. Re-running this writes ``bench/dev/cases.jsonl``
byte-identically (fixed base time, fixed offsets, sorted keys, index-driven
variety — no RNG). 120 cases:

  planted D1x8 D2x6 D3x6 D4x6 D5x8 D6x8 D7x6  (=48, GATE 1 classes)
  planted D8x4  (scored separately)
  clean   x68  (10 restatement, 8 deep, 8 wide fan-out, 8 tightened, 34 mixed)

Each planted case carries exactly one planted violation; ``expected`` lists
exactly the (class, edge) the pinned definition in §4 names. Clean cases list
``[]`` and must produce no finding at all.

Run: ``python -m bench.generate_dev`` or ``python bench/generate_dev.py``.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

SEED = 20261109
BASE = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dev")

TOOLS = ["tool.search", "tool.read", "tool.fetch", "tool.index", "tool.summarize", "tool.vector"]
ACTIONS = ["data.read", "data.list", "report.generate", "cache.read", "index.update", "data.write"]
RES = ["db/project-x/*", "db/project-y/*", "files/reports/*", "kv/cache/*", "logs/app/*", "db/analytics/*"]
DATACLASS_SETS = [["internal"], ["public", "internal"], ["public"], ["internal", "confidential"]]
CAPNAMES = ["spend_usd", "api_calls", "rows_scanned", "tokens", "emails_sent"]
PURPOSE_SETS = [["read"], ["read", "write"], ["read", "communicate"], ["read", "execute"]]
TIERS = ["T0", "T1", "T2", "T3"]
KINDS = ["human", "agent", "service"]
PROTECTED = [
    "funds.transfer", "data.delete", "iam.grant", "iam.modify",
    "code.push_protected", "pii.export", "secret.read", "infra.destroy",
]


def ts(days: int = 0, hours: int = 0) -> str:
    return (BASE + timedelta(days=days, hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def pick(pool, i):
    return pool[i % len(pool)]


def two(pool, i):
    """A deterministic 2-element sorted set from a pool."""
    a, b = pool[i % len(pool)], pool[(i + 2) % len(pool)]
    return sorted({a, b})


def mk_node(nid, kind, tier):
    return {"id": nid, "kind": kind, "trust_tier": tier}


def mk_edge(
    eid, parent, issuer, holder, *, tools, actions, resources, data_classes,
    issued_days, expires_days, redelegation=True, purposes, caps,
    evidence_kind="attestation", depth_budget=None,
):
    """Build one edge dict. ``caps`` is a list of (name, limit) pairs."""
    authority = {
        "tools": sorted(set(tools)),
        "actions": sorted(set(actions)),
        "resources": list(resources),
        "data_classes": sorted(set(data_classes)),
    }
    caveats = {
        "issued_at": ts(issued_days),
        "expires_at": None if expires_days is None else ts(expires_days),
        "redelegation": redelegation,
        "caps": [{"name": n, "limit": l} for n, l in sorted(caps)],
        "purposes": sorted(set(purposes)),
    }
    if depth_budget is not None:
        caveats["depth_budget"] = depth_budget
    if evidence_kind == "none":
        evidence = {"kind": "none", "ref": None}
    else:
        evidence = {"kind": evidence_kind, "ref": f"{evidence_kind[:3]}:{eid}"}
    return {
        "id": eid,
        "parent_edge": parent,
        "issuer": issuer,
        "holder": holder,
        "authority": authority,
        "caveats": caveats,
        "evidence": evidence,
    }


def doc(nodes, edges):
    return {"schema": "dgraph/1", "nodes": nodes, "edges": edges}


def base_params(i):
    """A deterministic bundle of valid base authority for case index ``i``."""
    return {
        "tools": two(TOOLS, i),
        "actions": two(ACTIONS, i),
        "resources": [pick(RES, i)],
        "data_classes": pick(DATACLASS_SETS, i),
        "capname": pick(CAPNAMES, i),
        "purposes": pick(PURPOSE_SETS, i % 2),  # keep base simple (read / read+write)
    }


def restate_chain(i, length, *, root_tier="T0", child_tiers=None, depth_budget=None,
                  evidence_kind="attestation", redeleg=None, protected_action=None):
    """A fully valid equal-restatement chain of ``length`` edges.

    Returns (nodes, edges). Node n0 is the root authority. All edges restate the
    same authority/caveats, so the chain is clean by construction. Callers mutate
    a copy to plant exactly one violation.
    """
    p = base_params(i)
    actions = list(p["actions"])
    if protected_action is not None and protected_action not in actions:
        actions = sorted(set(actions) | {protected_action})
    nodes = [mk_node("n0", pick(KINDS, i), root_tier)]
    tiers = child_tiers or ["T1"] * length
    edges = []
    for d in range(1, length + 1):
        holder_id = f"n{d}"
        tier = tiers[(d - 1) % len(tiers)] if child_tiers else "T1"
        nodes.append(mk_node(holder_id, "agent", tier))
        issuer = f"n{d - 1}"
        parent = None if d == 1 else f"e{d - 1}"
        redel = True
        if redeleg is not None:
            redel = redeleg[d - 1] if isinstance(redeleg, list) else redeleg
        edges.append(mk_edge(
            f"e{d}", parent, issuer, holder_id,
            tools=p["tools"], actions=actions, resources=list(p["resources"]),
            data_classes=p["data_classes"], issued_days=0, expires_days=180,
            redelegation=redel, purposes=p["purposes"], caps=[(p["capname"], 100)],
            evidence_kind=evidence_kind,
            depth_budget=depth_budget if d == 1 else None,
        ))
    return nodes, edges


# --------------------------------------------------------------------------- #
# Planted builders. Each returns (doc, expected).
# --------------------------------------------------------------------------- #

def plant_d1(i):
    """Child amplifies on one dimension (cycled)."""
    nodes, edges = restate_chain(i, 2)
    dim = i % 4
    p = base_params(i)
    child = edges[1]
    if dim == 0:  # extra tool
        extra = pick([t for t in TOOLS if t not in child["authority"]["tools"]], i)
        child["authority"]["tools"] = sorted(set(child["authority"]["tools"]) | {extra})
    elif dim == 1:  # extra (non-protected) action
        extra = pick([a for a in ACTIONS if a not in child["authority"]["actions"]], i)
        child["authority"]["actions"] = sorted(set(child["authority"]["actions"]) | {extra})
    elif dim == 2:  # resource not subsumed by parent
        extra = pick([r for r in RES if r not in child["authority"]["resources"]], i)
        child["authority"]["resources"] = list(child["authority"]["resources"]) + [extra]
    else:  # extra data class
        extra = pick([d for d in ["public", "internal", "confidential", "restricted"]
                      if d not in child["authority"]["data_classes"]], i)
        child["authority"]["data_classes"] = sorted(set(child["authority"]["data_classes"]) | {extra})
    return doc(nodes, edges), [{"class": "D1", "edge": "e2"}]


def plant_d2(i):
    """Exactly the last edge exceeds the effective depth budget."""
    plans = [(2, 3), (3, 4), (4, 5), (5, 6), (None, 7), (1, 2)]
    budget, length = plans[i % len(plans)]
    nodes, edges = restate_chain(i, length, depth_budget=budget)
    return doc(nodes, edges), [{"class": "D2", "edge": f"e{length}"}]


def plant_d3(i):
    """A parent forbids re-delegation yet has a child."""
    depth = [2, 3][i % 2]  # plant on e2 (root forbids) or e3 (e2 forbids)
    if depth == 2:
        redeleg = [False, True]  # root e1 forbids, e2 is the illegal child
        nodes, edges = restate_chain(i, 2, redeleg=redeleg)
        return doc(nodes, edges), [{"class": "D3", "edge": "e2"}]
    redeleg = [True, False, True]  # e2 forbids, e3 is the illegal child
    nodes, edges = restate_chain(i, 3, redeleg=redeleg)
    return doc(nodes, edges), [{"class": "D3", "edge": "e3"}]


def plant_d4(i):
    """Child validity window not contained in parent's."""
    nodes, edges = restate_chain(i, 2)
    child = edges[1]
    variant = i % 3
    if variant == 0:  # child starts before parent
        child["caveats"]["issued_at"] = ts(-1)
    elif variant == 1:  # child expires after parent
        child["caveats"]["expires_at"] = ts(400)
    else:  # parent bounded, child unbounded
        child["caveats"]["expires_at"] = None
    return doc(nodes, edges), [{"class": "D4", "edge": "e2"}]


def plant_d5(i):
    """Fan-out: children each pass D1/D6, but a cap's child-sum exceeds parent."""
    p = base_params(i)
    capname = p["capname"]
    k = [2, 3, 4, 5][i % 4]
    # parent limit 100; each child gets a share that is individually <= 100 but
    # whose sum exceeds 100.
    shares = {2: [60, 60], 3: [40, 40, 40], 4: [30, 30, 30, 30], 5: [25, 25, 25, 25, 25]}[k]
    use_intermediate = (i % 2 == 1)
    nodes = [mk_node("n0", pick(KINDS, i), "T0")]
    edges = []
    if use_intermediate:
        # root e1 -> hub e2 -> children
        nodes.append(mk_node("n1", "agent", "T1"))
        edges.append(mk_edge(
            "e1", None, "n0", "n1", tools=p["tools"], actions=p["actions"],
            resources=list(p["resources"]), data_classes=p["data_classes"],
            issued_days=0, expires_days=180, purposes=p["purposes"], caps=[(capname, 100)],
        ))
        nodes.append(mk_node("n2", "agent", "T1"))
        edges.append(mk_edge(
            "e2", "e1", "n1", "n2", tools=p["tools"], actions=p["actions"],
            resources=list(p["resources"]), data_classes=p["data_classes"],
            issued_days=0, expires_days=180, purposes=p["purposes"], caps=[(capname, 100)],
        ))
        hub_edge, hub_node = "e2", "n2"
        next_e, next_n = 3, 3
    else:
        # root e1 is the hub
        nodes.append(mk_node("n1", "agent", "T1"))
        edges.append(mk_edge(
            "e1", None, "n0", "n1", tools=p["tools"], actions=p["actions"],
            resources=list(p["resources"]), data_classes=p["data_classes"],
            issued_days=0, expires_days=180, purposes=p["purposes"], caps=[(capname, 100)],
        ))
        hub_edge, hub_node = "e1", "n1"
        next_e, next_n = 2, 2
    for j, share in enumerate(shares):
        cid = f"n{next_n + j}"
        nodes.append(mk_node(cid, "agent", "T1"))
        edges.append(mk_edge(
            f"e{next_e + j}", hub_edge, hub_node, cid, tools=p["tools"], actions=p["actions"],
            resources=list(p["resources"]), data_classes=p["data_classes"],
            issued_days=0, expires_days=180, purposes=p["purposes"], caps=[(capname, share)],
        ))
    return doc(nodes, edges), [{"class": "D5", "edge": hub_edge}]


def plant_d6(i):
    """Caveat weakening: cap dropped / cap raised / purpose widened (cycled)."""
    variant = i % 3
    plant_on_e3 = (i % 2 == 1)
    length = 3 if plant_on_e3 else 2
    nodes, edges = restate_chain(i, length)
    target = edges[length - 1]
    eid = f"e{length}"
    if variant == 0:  # drop the cap
        target["caveats"]["caps"] = []
    elif variant == 1:  # raise the cap
        name = target["caveats"]["caps"][0]["name"]
        target["caveats"]["caps"] = [{"name": name, "limit": 150}]
    else:  # widen purposes
        widened = sorted(set(target["caveats"]["purposes"]) | {"administer"})
        target["caveats"]["purposes"] = widened
    return doc(nodes, edges), [{"class": "D6", "edge": eid}]


def plant_d7(i):
    """Protected action reaches a T2/T3 holder via a non-root issuer."""
    action = pick(PROTECTED, i)
    deep = (i % 2 == 1)
    if not deep:
        # n0 -> n1(T1) -> n2(T2): e2 grants protected to T2, issuer n1 != root
        tiers = ["T1", "T2"]
        nodes, edges = restate_chain(i, 2, child_tiers=tiers, protected_action=action)
        return doc(nodes, edges), [{"class": "D7", "edge": "e2"}]
    tiers = ["T1", "T1", "T3"]
    nodes, edges = restate_chain(i, 3, child_tiers=tiers, protected_action=action)
    return doc(nodes, edges), [{"class": "D7", "edge": "e3"}]


def plant_d8(i):
    """One edge records no issuer binding (evidence.kind == none)."""
    plant_on_e2 = (i % 2 == 0)
    if plant_on_e2:
        nodes, edges = restate_chain(i, 2)
        edges[1]["evidence"] = {"kind": "none", "ref": None}
        return doc(nodes, edges), [{"class": "D8", "edge": "e2"}]
    nodes, edges = restate_chain(i, 3)
    edges[2]["evidence"] = {"kind": "none", "ref": None}
    return doc(nodes, edges), [{"class": "D8", "edge": "e3"}]


# --------------------------------------------------------------------------- #
# Clean builders.
# --------------------------------------------------------------------------- #

def clean_restatement(i):
    length = [2, 3][i % 2]
    nodes, edges = restate_chain(i, length)
    return doc(nodes, edges), []


def clean_deep(i):
    length = [4, 5, 6][i % 3]
    nodes, edges = restate_chain(i, length)
    return doc(nodes, edges), []


def clean_wide(i):
    """Wide fan-out whose cap sums stay within the parent's limit."""
    p = base_params(i)
    capname = p["capname"]
    k = [3, 4, 5][i % 3]
    share = {3: 30, 4: 20, 5: 15}[k]  # sums 90 / 80 / 75, all <= 100
    nodes = [mk_node("n0", pick(KINDS, i), "T0"), mk_node("n1", "agent", "T1")]
    edges = [mk_edge(
        "e1", None, "n0", "n1", tools=p["tools"], actions=p["actions"],
        resources=list(p["resources"]), data_classes=p["data_classes"],
        issued_days=0, expires_days=180, purposes=p["purposes"], caps=[(capname, 100)],
    )]
    for j in range(k):
        cid = f"n{2 + j}"
        nodes.append(mk_node(cid, "agent", "T1"))
        edges.append(mk_edge(
            f"e{2 + j}", "e1", "n1", cid, tools=p["tools"], actions=p["actions"],
            resources=list(p["resources"]), data_classes=p["data_classes"],
            issued_days=0, expires_days=180, purposes=p["purposes"], caps=[(capname, share)],
        ))
    return doc(nodes, edges), []


def clean_tightened(i):
    """Each child tightens: lower cap, narrower purposes, shorter window, fewer tools."""
    p = base_params(i)
    length = [2, 3][i % 2]
    capname = p["capname"]
    nodes = [mk_node("n0", pick(KINDS, i), "T0")]
    edges = []
    tools = sorted(set(p["tools"]))
    purposes = ["read", "write"]
    cap_limit = 100
    expires = 180
    res = list(p["resources"])
    for d in range(1, length + 1):
        nodes.append(mk_node(f"n{d}", "agent", "T1"))
        parent = None if d == 1 else f"e{d - 1}"
        if d > 1:
            # tighten relative to previous
            if len(tools) > 1:
                tools = sorted(tools[:-1])
            purposes = ["read"]
            cap_limit = cap_limit - 10
            expires = expires - 10
        edges.append(mk_edge(
            f"e{d}", parent, f"n{d - 1}", f"n{d}", tools=tools, actions=p["actions"],
            resources=res, data_classes=p["data_classes"], issued_days=0, expires_days=expires,
            purposes=purposes, caps=[(capname, cap_limit)],
        ))
    return doc(nodes, edges), []


def clean_mixed(i):
    """Mixed valid graphs, depth 2-4, varied shapes (chain or small fan-out)."""
    shape = i % 3
    if shape == 0:
        nodes, edges = restate_chain(i, [2, 3, 4][i % 3])
        return doc(nodes, edges), []
    if shape == 1:
        return clean_tightened(i)
    # small 2-child fan-out within bound, plus a grandchild on one branch
    p = base_params(i)
    capname = p["capname"]
    nodes = [mk_node("n0", pick(KINDS, i), "T0"), mk_node("n1", "agent", "T1")]
    edges = [mk_edge(
        "e1", None, "n0", "n1", tools=p["tools"], actions=p["actions"],
        resources=list(p["resources"]), data_classes=p["data_classes"],
        issued_days=0, expires_days=180, purposes=p["purposes"], caps=[(capname, 100)],
    )]
    nodes += [mk_node("n2", "agent", "T1"), mk_node("n3", "agent", "T2")]
    edges.append(mk_edge(
        "e2", "e1", "n1", "n2", tools=p["tools"], actions=p["actions"],
        resources=list(p["resources"]), data_classes=p["data_classes"],
        issued_days=0, expires_days=170, purposes=p["purposes"], caps=[(capname, 40)],
    ))
    edges.append(mk_edge(
        "e3", "e1", "n1", "n3", tools=p["tools"], actions=p["actions"],
        resources=list(p["resources"]), data_classes=p["data_classes"],
        issued_days=0, expires_days=170, purposes=p["purposes"], caps=[(capname, 40)],
    ))
    # grandchild on branch e2, further tightened
    nodes.append(mk_node("n4", "agent", "T2"))
    edges.append(mk_edge(
        "e4", "e2", "n2", "n4", tools=p["tools"], actions=p["actions"],
        resources=list(p["resources"]), data_classes=p["data_classes"],
        issued_days=0, expires_days=160, purposes=p["purposes"], caps=[(capname, 20)],
    ))
    return doc(nodes, edges), []


def build_all():
    cases = []
    idx = 0

    def add(builder, n):
        nonlocal idx
        for _ in range(n):
            g, expected = builder(idx)
            cases.append((g, expected))
            idx += 1

    # Planted (GATE 1 classes)
    add(plant_d1, 8)
    add(plant_d2, 6)
    add(plant_d3, 6)
    add(plant_d4, 6)
    add(plant_d5, 8)
    add(plant_d6, 8)
    add(plant_d7, 6)
    # Planted D8 (scored separately)
    add(plant_d8, 4)
    # Clean
    add(clean_restatement, 10)
    add(clean_deep, 8)
    add(clean_wide, 8)
    add(clean_tightened, 8)
    add(clean_mixed, 34)

    assert len(cases) == 120, f"expected 120 cases, built {len(cases)}"
    return cases


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    cases = build_all()
    lines = []
    for n, (g, expected) in enumerate(cases, start=1):
        obj = {"case_id": f"case-{n:04d}", "graph": g, "expected": expected}
        lines.append(json.dumps(obj, sort_keys=True, separators=(",", ":")))
    payload = ("\n".join(lines) + "\n").encode("utf-8")

    cases_path = os.path.join(OUT_DIR, "cases.jsonl")
    with open(cases_path, "wb") as fh:
        fh.write(payload)

    manifest = {
        "count": len(cases),
        "seed": SEED,
        "cases_sha256": hashlib.sha256(payload).hexdigest(),
    }
    manifest_path = os.path.join(OUT_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, sort_keys=True, indent=2)
        fh.write("\n")

    print(f"wrote {len(cases)} cases to {cases_path}")
    print(f"cases_sha256 = {manifest['cases_sha256']}")


if __name__ == "__main__":
    main()
