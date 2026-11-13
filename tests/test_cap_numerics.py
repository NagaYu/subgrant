"""Regression tests for the cap-numerics fix (DECISIONS "cap numerics").

Two evasion families found by the adversarial fuzz audit are closed here:

  * ``D6|cap/nan`` — a child (or parent) cap limit of ``NaN`` silently defeated
    the strict ``>`` comparison, so D6 stayed quiet and the enforceable bound
    vanished.
  * ``D6|cap/bigint-plus-one`` — ``float64`` coercion at load made
    ``2**53 + 1`` equal to ``2**53``, so an integer cap raise of exactly 1 slid
    past D6.

Pinned semantics (see DECISIONS):
  * NaN is a *weakening*, reported as a finding (D6/D5), never an input error.
  * Cap limits compare exactly as written; integers keep full precision.
  * Everything else keeps today's verdict (+Infinity fires, -Infinity clean,
    finite floats unchanged, equal restatement clean).

The three repro chains are copied under ``tests/fixtures/caps/`` so these
tests do not depend on the (read-only) ``fuzz/`` branch tooling.
"""

from __future__ import annotations

import base64
import json
import math
import os
import subprocess
import sys
from fractions import Fraction

from subgrant.checks import _cap_sum, load_policy_pack, run_checks
from subgrant.graph import load_graph
from subgrant.normalizers import normalize as normalize_doc

from .helpers import base_chain

PACK = load_policy_pack()
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "caps")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def findings_of(doc):
    return {(f.cls, f.edge) for f in run_checks(load_graph(doc), PACK)}


def _set_child_cap(doc, limit, name="spend_usd"):
    """Set the child edge (e2) cap to ``limit`` on a fresh base chain."""
    doc["edges"][1]["caveats"]["caps"] = [{"name": name, "limit": limit}]
    return doc


# --------------------------------------------------------------------------- #
# 1. The three checked-in repro chains now produce findings (exit 1 via CLI).
# --------------------------------------------------------------------------- #

def _verify_cli(path):
    proc = subprocess.run(
        [sys.executable, "-m", "subgrant", "verify", path],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout


def test_repro_d6_nan_cli_flags():
    rc, out = _verify_cli(os.path.join(FIXTURES, "evasion_D6_nan.json"))
    assert rc == 1, out
    assert "D6" in out


def test_repro_d6_bigint_cli_flags():
    rc, out = _verify_cli(os.path.join(FIXTURES, "evasion_D6_bigint.json"))
    assert rc == 1, out
    assert "D6" in out


def test_repro_d5_nan_sibling_cli_flags():
    rc, out = _verify_cli(os.path.join(FIXTURES, "evasion_D5_nan_sibling.json"))
    assert rc == 1, out
    # The NaN sibling individually fails D6 (NaN is not provably <= parent), so
    # the chain is flagged; the per-edge D6 finding is reported.
    assert "D6" in out


def test_all_three_repros_via_run_checks():
    for fn in ("evasion_D6_nan.json", "evasion_D6_bigint.json", "evasion_D5_nan_sibling.json"):
        with open(os.path.join(FIXTURES, fn), "r", encoding="utf-8") as fh:
            doc = json.load(fh)  # json.load accepts bareword NaN (allow_nan)
        assert findings_of(doc), f"{fn} produced no findings"


# --------------------------------------------------------------------------- #
# 2. Integers keep full precision (2**53 boundary).
# --------------------------------------------------------------------------- #

def test_bigint_raise_by_one_fires_d6():
    d = _set_child_cap(base_chain(), 2 ** 53 + 1)
    d["edges"][0]["caveats"]["caps"] = [{"name": "spend_usd", "limit": 2 ** 53}]
    assert ("D6", "e2") in findings_of(d)


def test_bigint_equal_restate_is_clean():
    d = _set_child_cap(base_chain(), 2 ** 53)
    d["edges"][0]["caveats"]["caps"] = [{"name": "spend_usd", "limit": 2 ** 53}]
    assert ("D6", "e2") not in findings_of(d)


# --------------------------------------------------------------------------- #
# 3. NaN is a weakening (D6), both as child and as parent limit.
# --------------------------------------------------------------------------- #

def test_nan_child_cap_fires_d6():
    d = _set_child_cap(base_chain(), float("nan"))
    assert ("D6", "e2") in findings_of(d)


def test_nan_parent_cap_with_finite_child_fires_d6():
    d = base_chain()
    d["edges"][0]["caveats"]["caps"] = [{"name": "spend_usd", "limit": float("nan")}]
    d["edges"][1]["caveats"]["caps"] = [{"name": "spend_usd", "limit": 50}]
    assert ("D6", "e2") in findings_of(d)


def test_nan_cap_is_not_an_input_error():
    # A NaN cap must load cleanly (it is a finding, not a GraphError / exit 2).
    d = _set_child_cap(base_chain(), float("nan"))
    load_graph(d)  # does not raise


# --------------------------------------------------------------------------- #
# 4. Preserved verdicts for the non-finite and ordinary cases.
# --------------------------------------------------------------------------- #

def test_positive_infinity_child_fires_d6():
    d = _set_child_cap(base_chain(), float("inf"))
    assert ("D6", "e2") in findings_of(d)


def test_negative_infinity_child_is_clean():
    d = _set_child_cap(base_chain(), float("-inf"))
    assert ("D6", "e2") not in findings_of(d)


def test_ordinary_raise_fires_d6():
    d = _set_child_cap(base_chain(), 200)  # parent is 100
    assert ("D6", "e2") in findings_of(d)


def test_equal_restate_is_clean():
    d = _set_child_cap(base_chain(), 100)  # equal to parent
    assert ("D6", "e2") not in findings_of(d)


# --------------------------------------------------------------------------- #
# 5. NaN caps are flagged through the descriptor and attenu normalizers.
# --------------------------------------------------------------------------- #

def _descriptor_nan():
    return {
        "framework": "x", "version": "1", "scenario": "s",
        "child_credentials": "scoped", "handoff_evidence": "signed token",
        "source_refs": [],
        "generations": [
            {"node": "root", "actions": ["data.read"], "resources": [], "tools": [],
             "caps": [{"name": "spend_usd", "limit": 100}], "purposes": ["read"]},
            {"node": "a2", "actions": ["data.read"], "resources": [], "tools": [],
             "caps": [{"name": "spend_usd", "limit": float("nan")}], "purposes": ["read"]},
        ],
    }


def _jws(payload: dict) -> str:
    def seg(obj):
        raw = json.dumps(obj, allow_nan=True).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    return f"{seg({'alg': 'none'})}.{seg(payload)}.sig"


def _attenu_nan():
    return {"tokens": [
        _jws({"iss": "root", "sub": "a1", "iat": 1700000000, "exp": 1800000000, "jti": "t0",
              "del_depth": 0, "authorization_details": [
                  {"type": "agent_delegation", "scopes": ["crm.read"],
                   "constraints": [{"key": "spend_usd", "max": 100}]}]}),
        _jws({"iss": "root", "sub": "a2", "iat": 1700000000, "exp": 1800000000, "jti": "t1",
              "del_depth": 1, "authorization_details": [
                  {"type": "agent_delegation", "scopes": ["crm.read"],
                   "constraints": [{"key": "spend_usd", "max": float("nan")}]}]}),
    ]}


def test_descriptor_nan_cap_flagged():
    norm = normalize_doc("descriptor", _descriptor_nan())
    assert any(c == "D6" for c, _ in findings_of(norm))


def test_attenu_nan_cap_flagged():
    norm = normalize_doc("attenu", _attenu_nan())
    assert any(c == "D6" for c, _ in findings_of(norm))


# --------------------------------------------------------------------------- #
# 6. D5 sibling sum: exact integer arithmetic, non-finite poisoning.
# --------------------------------------------------------------------------- #

def test_cap_sum_is_exact_for_integers():
    # float64 would round 2**53 + (2**53 + 1) differently; Fraction is exact.
    assert _cap_sum([2 ** 53, 2 ** 53 + 1]) == Fraction(2 ** 54 + 1)


def test_cap_sum_finite_float_is_exact_binary_value():
    assert _cap_sum([0.5, 0.25]) == Fraction(3, 4)


def test_cap_sum_nan_addend_poisons_to_nan():
    assert math.isnan(_cap_sum([90, float("nan")]))


def test_cap_sum_positive_infinity_addend():
    assert _cap_sum([90, float("inf")]) == float("inf")


def test_cap_sum_mixed_infinities_poison_to_nan():
    assert math.isnan(_cap_sum([float("inf"), float("-inf")]))


def test_d5_exact_integer_overflow_fires():
    # Two siblings each 2**52 + 1 sum to 2**53 + 2 > parent 2**53. A float64
    # sum would be 2**53 + 2 here, but the point is the integer sum is exact.
    d = {
        "schema": "dgraph/1",
        "nodes": [
            {"id": "n0", "kind": "human", "trust_tier": "T0"},
            {"id": "n1", "kind": "agent", "trust_tier": "T1"},
            {"id": "n2", "kind": "agent", "trust_tier": "T1"},
        ],
        "edges": [
            {"id": "e1", "parent_edge": None, "issuer": "n0", "holder": "n1",
             "authority": {"tools": [], "actions": ["data.read"],
                           "resources": ["db/x/*"], "data_classes": ["internal"]},
             "caveats": {"issued_at": "2026-01-01T00:00:00Z", "expires_at": None,
                         "redelegation": True,
                         "caps": [{"name": "spend_usd", "limit": 2 ** 53}],
                         "purposes": ["read"]},
             "evidence": {"kind": "attestation", "ref": "att:e1"}},
            {"id": "e2", "parent_edge": "e1", "issuer": "n1", "holder": "n2",
             "authority": {"tools": [], "actions": ["data.read"],
                           "resources": ["db/x/*"], "data_classes": ["internal"]},
             "caveats": {"issued_at": "2026-01-01T00:00:00Z", "expires_at": None,
                         "redelegation": True,
                         "caps": [{"name": "spend_usd", "limit": 2 ** 52 + 1}],
                         "purposes": ["read"]},
             "evidence": {"kind": "attestation", "ref": "att:e2"}},
            {"id": "e3", "parent_edge": "e1", "issuer": "n1", "holder": "n2",
             "authority": {"tools": [], "actions": ["data.read"],
                           "resources": ["db/x/*"], "data_classes": ["internal"]},
             "caveats": {"issued_at": "2026-01-01T00:00:00Z", "expires_at": None,
                         "redelegation": True,
                         "caps": [{"name": "spend_usd", "limit": 2 ** 52 + 1}],
                         "purposes": ["read"]},
             "evidence": {"kind": "attestation", "ref": "att:e3"}},
        ],
    }
    # Each child individually narrows (2**52 + 1 <= 2**53), so D6 does not fire
    # and the D5 fan-out gate is reached; the exact sibling sum overflows.
    assert ("D5", "e1") in findings_of(d)
