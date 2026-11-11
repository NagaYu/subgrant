"""SARIF 2.1.0 emitter for SubGrant findings (Phase 2 §5).

One run; ``tool.driver.name = "SubGrant"``; rules D1–D8 with short descriptions
from SPEC §6; one result per finding (``level`` = "error" for D1–D7, "note" for
D8). The result's location URI is the input file name as given.
"""

from __future__ import annotations

from typing import Any

from . import __version__
from .checks import Finding

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"

RULE_DESCRIPTIONS: dict[str, str] = {
    "D1": "Amplification: a child's authority is not a subset of its parent's (tools, actions, resources, or data classes).",
    "D2": "Depth breach: an edge's depth exceeds the effective delegation budget.",
    "D3": "Re-delegation breach: a parent that forbids re-delegation still has a child edge.",
    "D4": "Lifetime breach: a child's validity window is not contained in its parent's.",
    "D5": "Fan-out recombination: a parent's children recombine a cap beyond the parent's limit.",
    "D6": "Caveat drop / weakening: a cap is dropped or raised, or purposes are widened.",
    "D7": "Confused-deputy reachability: a protected action reaches a T2/T3 holder via a non-root issuer.",
    "D8": "Unbound delegation: the edge records no issuer binding (evidence kind is none).",
}

ALL_RULES = ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"]


def _level(cls: str) -> str:
    return "note" if cls == "D8" else "error"


def build_sarif(findings: list[Finding], uri: str) -> dict[str, Any]:
    rules = [
        {
            "id": rid,
            "name": rid,
            "shortDescription": {"text": RULE_DESCRIPTIONS[rid]},
            "defaultConfiguration": {"level": _level(rid)},
        }
        for rid in ALL_RULES
    ]
    results = [
        {
            "ruleId": f.cls,
            "level": _level(f.cls),
            "message": {"text": f"{f.cls} on edge {f.edge}"},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": uri},
                    }
                }
            ],
            "properties": {"edge": f.edge},
        }
        for f in findings
    ]
    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "SubGrant",
                        "version": __version__,
                        "informationUri": "https://subgrant.dev",
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }
