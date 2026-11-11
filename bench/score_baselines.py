"""Score baselines on Part A, with the same comparison rule as bench/score.py.

B0 — naive per-edge subset checker, over the full dev 120.
B1 — attenu-guard, via its vendored interop vectors: the `attenu` normalizer +
     core verifier vs each vector's documented verdict (agreement per vector).
     The reverse direction (b) requires installing attenu-guard offline; that is
     attempted/recorded separately and skipped here to stay zero-maintenance.
B2 — UCAN-spec checker, over the UCAN-expressible dev_ext cases.

Divergences between the baselines and SubGrant are listed individually.
"""

from __future__ import annotations

import glob
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from subgrant.baselines import b0_check, b2_check  # noqa: E402
from subgrant.checks import load_policy_pack, run_checks  # noqa: E402
from subgrant.graph import load_graph  # noqa: E402
from subgrant.normalizers import normalize  # noqa: E402

CASES_PATH = os.path.join(_REPO_ROOT, "bench", "dev", "cases.jsonl")
EXT_DIR = os.path.join(_REPO_ROOT, "bench", "dev_ext")
ATTENU_DIR = os.path.join(_REPO_ROOT, "fixtures", "attenu")
SCORE_PATH = os.path.join(_REPO_ROOT, "bench", "dev", "score_baselines.json")
GATE1_CLASSES = ["D1", "D2", "D3", "D4", "D5", "D6", "D7"]


def load_cases():
    with open(CASES_PATH, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _recall_table(cases, finder, pack):
    """finder(graph) -> set of (class, edge). Returns a score dict."""
    planted_total = {c: 0 for c in GATE1_CLASSES}
    planted_detected = {c: 0 for c in GATE1_CLASSES}
    d8_total = d8_detected = 0
    clean_total = clean_fp_cases = clean_fp_findings = 0
    extras = 0
    misses = []  # (case_id, expected) SubGrant-catchable but missed
    for case in cases:
        expected = case["expected"]
        found = finder(load_graph(case["graph"]))
        found_set = {(f.cls, f.edge) for f in found}
        expected_set = {(e["class"], e["edge"]) for e in expected}
        if not expected:
            clean_total += 1
            fp = [f for f in found_set if f[0] in GATE1_CLASSES]
            if fp:
                clean_fp_cases += 1
                clean_fp_findings += len(fp)
            continue
        exp = expected[0]
        cls = exp["class"]
        hit = (exp["class"], exp["edge"]) in found_set
        if cls == "D8":
            d8_total += 1
            d8_detected += int(hit)
        else:
            planted_total[cls] += 1
            planted_detected[cls] += int(hit)
            if not hit:
                misses.append((case["case_id"], exp))
        extras += len([f for f in found_set if f not in expected_set])
    recall = {c: (planted_detected[c] / planted_total[c] if planted_total[c] else None) for c in GATE1_CLASSES}
    return {
        "recall": recall,
        "planted_total": planted_total,
        "planted_detected": planted_detected,
        "d8_detected": d8_detected,
        "d8_total": d8_total,
        "clean_total": clean_total,
        "clean_fp_cases": clean_fp_cases,
        "clean_fp_findings": clean_fp_findings,
        "extras": extras,
        "misses": misses,
    }


def score_b0(cases, pack):
    return _recall_table(cases, lambda g: b0_check(g, pack), pack)


def score_subgrant(cases, pack):
    return _recall_table(cases, lambda g: run_checks(g, pack), pack)


def score_b2():
    """B2 over the UCAN-expressible dev_ext cases, against the same expected."""
    manifest = json.load(open(os.path.join(EXT_DIR, "manifest.json"), encoding="utf-8"))
    rows = {c["case_id"]: c for c in manifest["cases"]}
    scored = []
    per_class_total: dict[str, int] = {}
    per_class_hit: dict[str, int] = {}
    clean_fp = 0
    for cid, case in rows.items():
        info = case["formats"]["ucan"]
        if not info["expressible"]:
            continue
        rep = json.load(open(os.path.join(EXT_DIR, info["path"]), encoding="utf-8"))
        found = {(f.cls, f.edge) for f in b2_check(rep)}
        expected = {(e["class"], e["edge"]) for e in case["expected"]}
        if not case["expected"]:
            if found:
                clean_fp += 1
            scored.append((cid, "clean", bool(found)))
            continue
        exp = case["expected"][0]
        cls = exp["class"]
        per_class_total[cls] = per_class_total.get(cls, 0) + 1
        hit = (exp["class"], exp["edge"]) in found
        per_class_hit[cls] = per_class_hit.get(cls, 0) + int(hit)
        scored.append((cid, cls, hit))
    recall = {c: per_class_hit.get(c, 0) / t for c, t in per_class_total.items()}
    return {"recall": recall, "per_class_total": per_class_total, "clean_fp": clean_fp, "scored": scored}


def score_b1_attenu(pack):
    """B1(a): attenu normalizer + core verifier vs each vendored vector's verdict."""
    out = []
    for f in sorted(glob.glob(os.path.join(ATTENU_DIR, "*.json"))):
        doc = json.load(open(f, encoding="utf-8"))
        attenu_verdict = "accept" if doc.get("expect") == "accept" else "reject"
        attenu_reason = doc.get("expect_reject_reason")
        graph = normalize("attenu", doc)
        findings = [(x.cls, x.edge) for x in run_checks(load_graph(graph), pack)]
        subgrant_verdict = "accept" if not findings else "reject"
        agree = attenu_verdict == subgrant_verdict
        out.append({
            "vector": os.path.basename(f),
            "attenu": attenu_verdict,
            "attenu_reason": attenu_reason,
            "subgrant_findings": findings,
            "agree": agree,
        })
    return out


def main():
    pack = load_policy_pack()
    cases = load_cases()
    sg = score_subgrant(cases, pack)
    b0 = score_b0(cases, pack)
    b2 = score_b2()
    b1 = score_b1_attenu(pack)

    result = {"subgrant": sg, "b0": b0, "b2": b2, "b1_attenu": b1}
    with open(SCORE_PATH, "w", encoding="utf-8") as fh:
        json.dump(result, fh, sort_keys=True, indent=2, default=list)
        fh.write("\n")

    def fmt_recall(r):
        return "  ".join(f"{c}={('%.3f' % r[c]) if r[c] is not None else 'n/a'}" for c in GATE1_CLASSES)

    print("Baseline recall over dev 120 (per-class D1-D7)")
    print("=" * 70)
    print(f"SubGrant   {fmt_recall(sg['recall'])}  | D8 {sg['d8_detected']}/{sg['d8_total']}  FP {sg['clean_fp_cases']}  extras {sg['extras']}")
    print(f"B0 (naive) {fmt_recall(b0['recall'])}  | D8 {b0['d8_detected']}/{b0['d8_total']}  FP {b0['clean_fp_cases']}  extras {b0['extras']}")
    print()
    print("B2 (UCAN-spec) over UCAN-expressible dev_ext cases:")
    for c, t in sorted(b2["per_class_total"].items()):
        print(f"  {c}: recall {b2['recall'][c]:.3f} ({t} case(s))")
    print(f"  clean FP: {b2['clean_fp']}")
    print()
    print("B1 (attenu-guard) per vendored vector:")
    for row in b1:
        tag = "AGREE" if row["agree"] else "DIVERGE"
        print(f"  {row['vector']:30} attenu={row['attenu']:7}({row['attenu_reason']}) subgrant={row['subgrant_findings']} -> {tag}")
    print()
    print("Divergences (baseline misses what SubGrant catches):")
    for cid, exp in b0["misses"]:
        print(f"  B0 miss  {cid}: SubGrant {exp['class']} on {exp['edge']}")
    for cid, cls, hit in b2["scored"]:
        if cls != "clean" and not hit:
            print(f"  B2 miss  {cid}: SubGrant {cls} (B2 has no such concept)")
    for row in b1:
        if not row["agree"]:
            print(f"  B1 diverge {row['vector']}: attenu rejects ({row['attenu_reason']}), SubGrant accepts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
