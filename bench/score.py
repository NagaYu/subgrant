"""Score the SubGrant verifier core against the dev bench (§6).

Loads ``bench/dev/cases.jsonl``, runs the verifier on each graph, compares
findings to ``expected``, writes ``bench/dev/score.json`` and prints a table.

Metrics:
  * per-class recall D1-D7 (planted, detected iff expected class+edge present)
  * D8 detected count (of 4), scored separately from GATE 1
  * clean false positives: clean cases with any D1-D7 finding (cases + rate),
    and the total count of FP findings
  * extra findings on planted cases (each investigated, see reports/phase1.md)

GATE 1 (per §6): recall D1-D7 all == 1.000 AND clean FP cases == 0.
(pytest-green is the third GATE 1 condition, checked by the test run.)
"""

from __future__ import annotations

import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from subgrant.checks import load_policy_pack, run_checks  # noqa: E402
from subgrant.graph import load_graph  # noqa: E402

CASES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dev", "cases.jsonl")
SCORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dev", "score.json")

GATE1_CLASSES = ["D1", "D2", "D3", "D4", "D5", "D6", "D7"]


def load_cases(path=CASES_PATH):
    cases = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def score(cases=None):
    if cases is None:
        cases = load_cases()
    pack = load_policy_pack()

    planted_total = {c: 0 for c in GATE1_CLASSES}
    planted_detected = {c: 0 for c in GATE1_CLASSES}
    d8_total = 0
    d8_detected = 0

    clean_fp_cases = 0
    clean_total = 0
    clean_fp_findings = 0

    extra_findings = 0
    extra_detail = []  # (case_id, [finding dicts])
    clean_fp_detail = []  # (case_id, [finding dicts])
    missed_detail = []  # (case_id, expected dict)

    for case in cases:
        case_id = case["case_id"]
        expected = case["expected"]
        graph = load_graph(case["graph"])
        findings = [f.as_dict() for f in run_checks(graph, pack)]
        found_set = {(f["class"], f["edge"]) for f in findings}
        expected_set = {(e["class"], e["edge"]) for e in expected}

        if not expected:  # clean case
            clean_total += 1
            fp_here = [f for f in findings if f["class"] in GATE1_CLASSES]
            if fp_here:
                clean_fp_cases += 1
                clean_fp_findings += len(fp_here)
                clean_fp_detail.append((case_id, fp_here))
            continue

        # planted case (exactly one planted finding)
        exp = expected[0]
        cls = exp["class"]
        if cls == "D8":
            d8_total += 1
            if (exp["class"], exp["edge"]) in found_set:
                d8_detected += 1
        else:
            planted_total[cls] += 1
            if (exp["class"], exp["edge"]) in found_set:
                planted_detected[cls] += 1
            else:
                missed_detail.append((case_id, exp))

        extras = [f for f in findings if (f["class"], f["edge"]) not in expected_set]
        if extras:
            extra_findings += len(extras)
            extra_detail.append((case_id, extras))

    recall = {}
    for c in GATE1_CLASSES:
        recall[c] = (planted_detected[c] / planted_total[c]) if planted_total[c] else None

    clean_fp_rate = (clean_fp_cases / clean_total) if clean_total else 0.0

    gate1_recall_ok = all(recall[c] == 1.0 for c in GATE1_CLASSES)
    gate1 = gate1_recall_ok and clean_fp_cases == 0

    result = {
        "planted_total": planted_total,
        "planted_detected": planted_detected,
        "recall": recall,
        "d8_total": d8_total,
        "d8_detected": d8_detected,
        "clean_total": clean_total,
        "clean_fp_cases": clean_fp_cases,
        "clean_fp_rate": clean_fp_rate,
        "clean_fp_findings": clean_fp_findings,
        "extra_findings": extra_findings,
        "gate1_recall_ok": gate1_recall_ok,
        "gate1": gate1,
        "detail": {
            "extras": [{"case_id": cid, "findings": f} for cid, f in extra_detail],
            "clean_fp": [{"case_id": cid, "findings": f} for cid, f in clean_fp_detail],
            "missed": [{"case_id": cid, "expected": e} for cid, e in missed_detail],
        },
    }
    return result


def print_table(result):
    print("SubGrant dev-bench score")
    print("=" * 48)
    print(f"{'class':<8}{'planted':>9}{'detected':>10}{'recall':>9}")
    for c in GATE1_CLASSES:
        r = result["recall"][c]
        rstr = f"{r:.3f}" if r is not None else "   n/a"
        print(f"{c:<8}{result['planted_total'][c]:>9}{result['planted_detected'][c]:>10}{rstr:>9}")
    print("-" * 48)
    print(f"D8 detected: {result['d8_detected']} of {result['d8_total']} (scored separately)")
    print(
        f"clean cases: {result['clean_total']}  "
        f"FP cases: {result['clean_fp_cases']}  "
        f"FP rate: {result['clean_fp_rate']:.3f}  "
        f"FP findings: {result['clean_fp_findings']}"
    )
    print(f"extra findings on planted cases: {result['extra_findings']}")
    if result["detail"]["extras"]:
        print("  extras detail:")
        for row in result["detail"]["extras"]:
            print(f"    {row['case_id']}: {row['findings']}")
    if result["detail"]["clean_fp"]:
        print("  clean FP detail:")
        for row in result["detail"]["clean_fp"]:
            print(f"    {row['case_id']}: {row['findings']}")
    if result["detail"]["missed"]:
        print("  missed detail:")
        for row in result["detail"]["missed"]:
            print(f"    {row['case_id']}: expected {row['expected']}")
    print("-" * 48)
    print(f"GATE 1 (recall D1-D7 == 1.000 and clean FP cases == 0): "
          f"{'PASS' if result['gate1'] else 'FAIL'}")


def main():
    result = score()
    with open(SCORE_PATH, "w", encoding="utf-8") as fh:
        json.dump(result, fh, sort_keys=True, indent=2)
        fh.write("\n")
    print_table(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
