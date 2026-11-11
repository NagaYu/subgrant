"""Generate multi-format representations of known dev cases (Phase 2 §3).

dev_ext proves the normalizers preserve verdicts on graphs whose truth is
already known. For each selected dev case and each format, this inverts the
§2 mapping by hand to build a representation, then normalizes + verifies it and
checks the finding set equals the source case's ``expected`` exactly.

A format can only carry some dimensions, so a representation is **expressible**
only when the format can reproduce the case's expected findings:
  * rfc8693 and descriptor need a pure linear chain (fan-outs are inexpressible).
  * a case whose violation lives on a dimension the format drops (e.g. caps for
    ucan, windows for rfc8693/descriptor, evidence for all three) is inexpressible.
Inexpressible (case, format) pairs are recorded in the manifest with the reason
(the §3 escape for rfc8693 fan-outs, generalized — see DECISIONS D-019). We never
edit ``expected``.

Deterministic: reads the frozen ``bench/dev/cases.jsonl`` and writes
representation files + a manifest byte-identically on every run.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from subgrant.checks import load_policy_pack, run_checks  # noqa: E402
from subgrant.graph import load_graph  # noqa: E402
from subgrant.normalizers import NormalizeError, normalize  # noqa: E402

CASES_PATH = os.path.join(_REPO_ROOT, "bench", "dev", "cases.jsonl")
OUT_DIR = os.path.join(_REPO_ROOT, "bench", "dev_ext")
FORMATS = ["ucan", "rfc8693", "descriptor"]

# Clean sub-kind case-id ranges (documented in reports/phase1.md §3 and the
# generator build order): restatement 0053-0062, deep 0063-0070,
# wide 0071-0078, tightened 0079-0086, mixed 0087-0120.
CLEAN_SUBKINDS = {
    "restatement": (53, 62),
    "deep": (63, 70),
    "wide": (71, 78),
    "tightened": (79, 86),
    "mixed": (87, 120),
}


def _cid(n: int) -> str:
    return f"case-{n:04d}"


def select_case_ids() -> list[str]:
    """The pinned 24-case selection (§3)."""
    rows = load_cases()
    by_class: dict[str, list[str]] = {}
    for r in rows:
        key = r["expected"][0]["class"] if r["expected"] else "clean"
        by_class.setdefault(key, []).append(r["case_id"])
    chosen: list[str] = []
    for cls in ["D1", "D2", "D3", "D4", "D5", "D6", "D7"]:
        chosen += by_class[cls][:2]  # first two planted of each class
    chosen += by_class["D8"][:1]  # first planted D8
    chosen += [_cid(CLEAN_SUBKINDS["restatement"][0]), _cid(CLEAN_SUBKINDS["restatement"][0] + 1)]
    chosen += [_cid(CLEAN_SUBKINDS["deep"][0]), _cid(CLEAN_SUBKINDS["deep"][0] + 1)]
    chosen += [_cid(CLEAN_SUBKINDS["wide"][0]), _cid(CLEAN_SUBKINDS["wide"][0] + 1)]
    chosen += [_cid(CLEAN_SUBKINDS["tightened"][0]), _cid(CLEAN_SUBKINDS["tightened"][0] + 1)]
    chosen += [_cid(CLEAN_SUBKINDS["mixed"][0])]
    assert len(chosen) == 24, f"expected 24, got {len(chosen)}"
    return chosen


def load_cases(path=CASES_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def ts_to_unix(ts: str) -> int:
    dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def is_chain(graph: dict) -> bool:
    """True iff the graph is a pure linear chain (no edge has 2+ children)."""
    seen: set[str] = set()
    for e in graph["edges"]:
        p = e["parent_edge"]
        if p is None:
            continue
        if p in seen:
            return False
        seen.add(p)
    return True


def _edge_order(graph: dict) -> list[dict]:
    return list(graph["edges"])  # document order (root first, parents before children)


# --------------------------------------------------------------------------- #
# Hand inverters: dgraph/1 -> source-format representation
# --------------------------------------------------------------------------- #

def to_ucan(graph: dict) -> dict:
    edges = _edge_order(graph)
    index = {e["id"]: i for i, e in enumerate(edges)}
    chain = []
    for e in edges:
        a = e["authority"]
        actions = a["actions"]
        resources = a["resources"]
        att = [{"with": r, "can": c} for r in resources for c in actions]
        link = {
            "iss": e["issuer"],
            "aud": e["holder"],
            "att": att,
            "nbf": ts_to_unix(e["caveats"]["issued_at"]),
            "exp": None if e["caveats"]["expires_at"] is None else ts_to_unix(e["caveats"]["expires_at"]),
            "prf": [] if e["parent_edge"] is None else [index[e["parent_edge"]]],
        }
        chain.append(link)
    return {"chain": chain}


def to_rfc8693(graph: dict) -> dict:
    edges = _edge_order(graph)  # linear
    root = edges[0]
    iat = ts_to_unix(root["caveats"]["issued_at"])
    exp = None if root["caveats"]["expires_at"] is None else ts_to_unix(root["caveats"]["expires_at"])

    def scope(e):
        return " ".join(e["authority"]["actions"])

    # Build nested act from the tail (e2..eN).
    nested = None
    for e in reversed(edges[1:]):
        nested = {"sub": e["holder"], "scope": scope(e), "act": nested}
    payload = {
        "iss": root["issuer"],
        "sub": root["holder"],
        "scope": scope(root),
        "iat": iat,
        "exp": exp,
    }
    if nested is not None:
        payload["act"] = nested
    return payload


def to_descriptor(graph: dict) -> dict:
    edges = _edge_order(graph)  # linear
    # Evidence is chain-wide in the descriptor format; use attestation unless the
    # source root carries none (then the case is inexpressible and build+check
    # will flag it).
    root_evi = edges[0]["evidence"]["kind"]
    handoff = "logged attestation" if root_evi != "none" else "none"
    generations = []
    for i, e in enumerate(edges):
        a = e["authority"]
        generations.append({
            "node": f"g{i}",
            "tools": a["tools"],
            "actions": a["actions"],
            "resources": a["resources"],
            "caps": [{"name": c["name"], "limit": c["limit"]} for c in e["caveats"]["caps"]],
            "purposes": e["caveats"]["purposes"],
        })
    return {
        "framework": "devext",
        "version": "0",
        "scenario": "dev_ext round-trip",
        "generations": generations,
        "child_credentials": "scoped",
        "handoff_evidence": handoff,
        "source_refs": [],
    }


INVERTERS = {"ucan": to_ucan, "rfc8693": to_rfc8693, "descriptor": to_descriptor}


def expressible(case: dict, fmt: str, pack: dict):
    """Return (ok, representation_or_None, reason)."""
    graph = case["graph"]
    expected = {(e["class"], e["edge"]) for e in case["expected"]}
    if fmt in ("rfc8693", "descriptor") and not is_chain(graph):
        return False, None, f"{fmt}: fan-out graph is inexpressible as a linear {fmt} chain"
    rep = INVERTERS[fmt](graph)
    try:
        norm = normalize(fmt, rep)
    except NormalizeError as exc:
        return False, None, f"{fmt}: representation failed to normalize: {exc}"
    findings = {(f.cls, f.edge) for f in run_checks(load_graph(norm), pack)}
    if findings == expected:
        return True, rep, "expressible"
    return (
        False,
        None,
        f"{fmt}: normalized findings {sorted(findings)} != expected {sorted(expected)} "
        f"(dimension not carried by {fmt})",
    )


def build():
    pack = load_policy_pack()
    rows = {r["case_id"]: r for r in load_cases()}
    chosen = select_case_ids()

    manifest_cases = []
    files_to_write: dict[str, dict] = {}
    counts = {fmt: {"expressible": 0, "inexpressible": 0} for fmt in FORMATS}

    for cid in chosen:
        case = rows[cid]
        cls = case["expected"][0]["class"] if case["expected"] else "clean"
        entry = {"case_id": cid, "class": cls, "expected": case["expected"], "formats": {}}
        for fmt in FORMATS:
            ok, rep, reason = expressible(case, fmt, pack)
            if ok:
                counts[fmt]["expressible"] += 1
                path = f"{fmt}/{cid}.json"
                files_to_write[path] = rep
                entry["formats"][fmt] = {"expressible": True, "path": path}
            else:
                counts[fmt]["inexpressible"] += 1
                entry["formats"][fmt] = {"expressible": False, "reason": reason}
        manifest_cases.append(entry)

    manifest = {
        "count": len(chosen),
        "selected_case_ids": chosen,
        "formats": FORMATS,
        "counts": counts,
        "cases": manifest_cases,
    }
    return manifest, files_to_write


def main():
    manifest, files = build()
    for fmt in FORMATS:
        os.makedirs(os.path.join(OUT_DIR, fmt), exist_ok=True)
    for rel, doc in files.items():
        with open(os.path.join(OUT_DIR, rel), "w", encoding="utf-8") as fh:
            json.dump(doc, fh, sort_keys=True, indent=2)
            fh.write("\n")
    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, sort_keys=True, indent=2)
        fh.write("\n")
    for fmt in FORMATS:
        c = manifest["counts"][fmt]
        print(f"{fmt:10} expressible={c['expressible']:2}  inexpressible={c['inexpressible']:2}")
    print(f"wrote {len(files)} representation files + manifest to {OUT_DIR}")


if __name__ == "__main__":
    main()
