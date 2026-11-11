"""Bench regeneration is byte-identical; composition and GATE 1 hold."""

import hashlib
import json
import os

from bench import generate_dev, score

DEV_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bench", "dev")


def test_regeneration_byte_identical():
    cases = generate_dev.build_all()
    lines = []
    for n, (g, expected) in enumerate(cases, start=1):
        obj = {"case_id": f"case-{n:04d}", "graph": g, "expected": expected}
        lines.append(json.dumps(obj, sort_keys=True, separators=(",", ":")))
    payload = ("\n".join(lines) + "\n").encode("utf-8")

    with open(os.path.join(DEV_DIR, "cases.jsonl"), "rb") as fh:
        on_disk = fh.read()
    assert payload == on_disk, "generator output drifted from committed cases.jsonl"

    with open(os.path.join(DEV_DIR, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    assert manifest["count"] == 120
    assert manifest["seed"] == generate_dev.SEED
    assert manifest["cases_sha256"] == hashlib.sha256(on_disk).hexdigest()


def test_composition_counts():
    counts = {}
    for case in score.load_cases():
        expected = case["expected"]
        key = expected[0]["class"] if expected else "clean"
        counts[key] = counts.get(key, 0) + 1
    assert counts == {
        "D1": 8, "D2": 6, "D3": 6, "D4": 6, "D5": 8, "D6": 8, "D7": 6, "D8": 4, "clean": 68
    }


def test_each_planted_has_exactly_one_expected():
    for case in score.load_cases():
        if case["expected"]:
            assert len(case["expected"]) == 1, case["case_id"]


def test_gate1_passes():
    result = score.score()
    for cls in score.GATE1_CLASSES:
        assert result["recall"][cls] == 1.0, (cls, result["recall"][cls])
    assert result["clean_fp_cases"] == 0
    assert result["extra_findings"] == 0
    assert result["d8_detected"] == 4
    assert result["gate1"] is True
