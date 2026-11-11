"""Round-trip scorer for dev_ext (Phase 2 §3).

For every expressible representation in the dev_ext manifest: normalize it with
the core normalizer, run the core verifier, and assert the finding set equals
the source dev case's ``expected`` exactly. Reports per-format pass counts and
lists any mismatch (there should be none — a mismatch means the representation
or normalizer is wrong, never ``expected``).
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
from subgrant.normalizers import normalize  # noqa: E402

EXT_DIR = os.path.join(_REPO_ROOT, "bench", "dev_ext")
MANIFEST = os.path.join(EXT_DIR, "manifest.json")
SCORE_PATH = os.path.join(EXT_DIR, "score_ext.json")


def score():
    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    pack = load_policy_pack()
    formats = manifest["formats"]

    per_format = {f: {"expressible": 0, "passed": 0, "failed": 0} for f in formats}
    inexpressible = {f: 0 for f in formats}
    mismatches = []

    for case in manifest["cases"]:
        expected = {(e["class"], e["edge"]) for e in case["expected"]}
        for fmt in formats:
            info = case["formats"][fmt]
            if not info["expressible"]:
                inexpressible[fmt] += 1
                continue
            per_format[fmt]["expressible"] += 1
            rep = json.load(open(os.path.join(EXT_DIR, info["path"]), encoding="utf-8"))
            norm = normalize(fmt, rep)
            findings = {(f.cls, f.edge) for f in run_checks(load_graph(norm), pack)}
            if findings == expected:
                per_format[fmt]["passed"] += 1
            else:
                per_format[fmt]["failed"] += 1
                mismatches.append({
                    "case_id": case["case_id"],
                    "format": fmt,
                    "expected": sorted(expected),
                    "got": sorted(findings),
                })

    result = {
        "per_format": per_format,
        "inexpressible": inexpressible,
        "mismatches": mismatches,
        "all_pass": all(per_format[f]["failed"] == 0 for f in formats),
    }
    return result


def main():
    result = score()
    with open(SCORE_PATH, "w", encoding="utf-8") as fh:
        json.dump(result, fh, sort_keys=True, indent=2)
        fh.write("\n")
    print("dev_ext round-trip score")
    print("=" * 52)
    print(f"{'format':12}{'expressible':>12}{'passed':>8}{'failed':>8}{'inexpr':>8}")
    for fmt in result["per_format"]:
        pf = result["per_format"][fmt]
        print(f"{fmt:12}{pf['expressible']:>12}{pf['passed']:>8}{pf['failed']:>8}{result['inexpressible'][fmt]:>8}")
    print("-" * 52)
    if result["mismatches"]:
        print("MISMATCHES (investigate; never edit expected):")
        for m in result["mismatches"]:
            print(f"  {m['case_id']} [{m['format']}] expected {m['expected']} got {m['got']}")
    else:
        print("All expressible representations round-trip to their expected findings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
