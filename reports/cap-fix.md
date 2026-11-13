# SubGrant — cap-numerics fix

**Session:** fix session for the two D6 cap evasions found by the adversarial
fuzz audit (`reports/fuzz-audit.md` §4). Branch `fix-cap-numerics`, cut from the
`fuzz-audit` tip (`4a8f299`) so the repros and harness are at hand. Local commit
only — nothing pushed, `../SubGrant-public` untouched, the sealed holdout never
opened.

---

## 1. Defect and fix

**Root cause (one spot):** `caveats.caps[].limit` was coerced to `float64` at
load (`subgrant/graph.py:194`, `caps[name] = float(limit)`) and compared with a
strict `>` in D6 (`subgrant/checks.py::_d6_weakens`) and in the D5 sibling-sum.
Two reproduced evasion families:

* `D6|cap/nan` — a `NaN` child cap limit: every `NaN` comparison is `False`, so
  `child > parent` is `False`, D6 stays silent and the enforceable bound is
  gone. The same `NaN` child collapses D5 (`90 + NaN`) and passes through the
  descriptor and attenu normalizers.
* `D6|cap/bigint-plus-one` — parent `9007199254740992` (2⁵³), child
  `9007199254740993`: `float64` coercion makes them equal, so D6 stays silent.

**Fix (pinned semantics D-021):**

| file | change | why |
|---|---|---|
| `subgrant/graph.py` | `caps[name] = limit` (was `float(limit)`); type `dict[str, int \| float]` | preserve the JSON number exactly — an `int` stays arbitrary-precision, a `float` stays a `float`; `NaN`/`±Inf` accepted at load, never an input error |
| `subgrant/checks.py` `_d6_weakens` | `if not (e.caps[name] <= plimit):` (was `if e.caps[name] > plimit:`) | provably-≤ test: `False`-safe for `NaN` (a `NaN` child *or* `NaN` parent fires D6); integers compare exactly so 2⁵³+1 > 2⁵³ |
| `subgrant/checks.py` D5 sum | `_cap_sum(...)` + `if not (total <= plimit):` (was `total = 0.0; … total += …; if total > plimit:`) | exact arithmetic (`Fraction`): integer sibling sums are exact; a `NaN` addend (or +∞/−∞ mix) poisons the total so a non-finite sum is never provably within the limit → D5 fires |

`_cap_sum` sums finite ints/floats via `Fraction` (which captures a float's
exact binary value), returns `float('nan')` if any addend is `NaN` or if +∞ and
−∞ are mixed, and returns the lone infinity otherwise.

**Non-finite verdict table (after fix):** +Infinity child → D6 fires;
−Infinity child → clean (narrows); finite floats → unchanged; equal restatement
(incl. exactly 2⁵³) → clean. `NaN` (child or parent) → D6 fires.

Note on the D5 repro: whenever a `NaN` would enter a D5 sum, that same `NaN`
child already fails the per-edge D6 provably-≤ test, so the D5 fan-out gate
(fire only when every child individually passes D1/D6) defers to the direct D6
finding. The chain is still flagged; the `NaN`-poisoning of `_cap_sum` is a
belt-and-suspenders property, verified directly in `test_cap_numerics.py`
(`test_d5_exact_integer_overflow_fires`, `test_cap_sum_*`).

## 2. `float(` grep over `subgrant/`

Before: one hit, the defect — `subgrant/graph.py:194: caps[name] = float(limit)`.

After:

```
subgrant/checks.py:131:        return float("nan")
subgrant/checks.py:133:        return float("inf")
subgrant/checks.py:135:        return float("-inf")
```

These three are non-finite **sentinel constructors** inside `_cap_sum`, not
coercions of an authority-bearing input number. No other `float(` coercion of
an authority number exists anywhere in `subgrant/` — the defect was caps only,
as expected.

## 3. DECISIONS entry (D-021, appended)

> **D-021 · Cap numerics — exact comparison, NaN/Infinity as findings.** Cap
> limits are compared exactly as written, with no `float64` rounding; at load
> the JSON number is preserved (int stays arbitrary-precision int, float stays
> float). D6/D5 use a provably-≤ test (`not (child <= parent)`), which is
> `False`-safe for `NaN`, so a `NaN` child limit fires D6 and a `NaN` parent
> limit makes any child cap not-provably-≤ (D6 fires); `NaN` is a weakening
> reported as a finding, never an input error. The D5 sibling sum is exact
> (`Fraction`) so integer sums cannot round within the limit, and a `NaN`/∞
> addend poisons the sum into firing. +Infinity child fires D6, −Infinity child
> is clean. Monotone-fix rationale: the fix only ever *adds* findings (superset)
> and changes verdicts only inside the two evasion families, so the published
> GATE 2 statement stays true by construction without reopening the sealed
> holdout; converting caps to input errors would remove findings and break that
> guarantee, so it was rejected.

(Full text in `DECISIONS.md`.)

## 4. Verification

### 4.1 pytest

| | result |
|---|---|
| before | **128 passed** |
| after | **149 passed** (128 existing, all green + **21 new** in `tests/test_cap_numerics.py`) |

### 4.2 dev bench (`python -m bench.score`) — identical, GATE 1 PASS

| class | recall (before = after) |
|---|---|
| D1–D7 | **1.000** each |
| D8 | **4 of 4** |
| clean cases | 68, FP cases **0**, FP findings **0** |
| extra findings | 0 |

`bench/dev/cases.jsonl` sha256 = `6858bed2b96ecd855cc862f7cf69e684e32ae982b5781dd7b7574da5ccf3c706` (unchanged). Bench files untouched.

### 4.3 dev_ext (`python -m bench.score_ext`) — identical

| format | expressible | passed | failed |
|---|---|---|---|
| ucan | 13 | 13 | 0 |
| rfc8693 | 8 | 8 | 0 |
| descriptor | 11 | 11 | 0 |

All expressible representations round-trip; mismatches 0.

### 4.4 fuzz harness (`python -m fuzz.run_fuzz`, `fuzz/` unmodified)

| bucket | before | after |
|---|---:|---:|
| caught | 3100 | **3300** |
| evasion | **200** | **0** |
| generator-error | 1600 | 1600 |
| spec-ambiguity | 300 | 300 |
| total_scored | 5200 | 5200 |
| dev_oracle_crosscheck | 120/120 agree | **120/120 agree** |
| distinct_evasions | `D6\|cap/bigint-plus-one`, `D6\|cap/nan` | **[] (none)** |

Per-class buckets (before → after):

| class | before | after |
|---|---|---|
| D1 | caught 1000, gen-err 100, ambig 200 | **identical** |
| D2 | caught 200, gen-err 100 | **identical** |
| D3 | caught 200 | **identical** |
| D4 | caught 600, gen-err 500 | **identical** |
| D5 | caught 300, gen-err 200 | **identical** |
| D6 | caught 500, **evasion 200**, gen-err 600 | caught **700**, **evasion 0**, gen-err 600 |
| D7 | caught 300, gen-err 100, ambig 100 | **identical** |

**Bucket movement:** the only change is D6 `evasion 200 → 0`, `caught 500 → 700`.
That +200 is exactly the two fixed families × 100 semantics-preserving salts
(`cap/nan` and `cap/bigint-plus-one`), which now surface as D6 findings. No
previously-caught `(generator, mutation_kind)` became uncaught; every other
per-class bucket, the generator-error and spec-ambiguity totals, and the oracle
crosscheck are byte-identical. No movement outside the two fixed families.

**Encoding differential (Attack 3), scenario `cap-raise-NaN (D6)`** — now
flagged in **both** formats:

```
flagged_in: ["attenu", "descriptor"]   passed_in: []
verdicts:   descriptor -> ["D6:e2"]     attenu -> ["D6:e2"]
```

(Because both formats now flag it, it is no longer a *differential* and so no
longer appears in `encoding_differentials`; `cap-raise (D6)` still appears there
as the disclosed ucan inexpressibility, D-019 — unchanged.)

### 4.5 repros via the real CLI (`python -m subgrant verify <file>`)

| repro | before | after |
|---|---|---|
| `fuzz/repros/evasion_D6_nan.json` | `OK: no findings`, exit 0 | `D6  e2`, **exit 1** |
| `fuzz/repros/evasion_D6_bigint.json` | `OK: no findings`, exit 0 | `D6  e2`, **exit 1** |
| `fuzz/repros/evasion_D5_nan_sibling.json` | `OK: no findings`, exit 0 | `D6  e3`, **exit 1** |

(The three fixtures copied to `tests/fixtures/caps/` give the same results, so
the regression tests do not depend on the `fuzz/` branch.)

### 4.6 diff scope (`git diff … --stat`)

The fix delta (`git diff 4a8f299 …`, i.e. against the `fuzz-audit` tip) is
limited to:

```
 DECISIONS.md                                    |  42 +
 reports/cap-fix.md                              | (this file)
 subgrant/checks.py                              |  55 ++-
 subgrant/graph.py                               |  12 +-
 tests/fixtures/caps/evasion_D5_nan_sibling.json | 141 +
 tests/fixtures/caps/evasion_D6_bigint.json      |  98 +
 tests/fixtures/caps/evasion_D6_nan.json         |  98 +
 tests/test_cap_numerics.py                      | 266 +
```

`git diff 4a8f299 -- fuzz bench packs SPEC.md` is **empty** — the fix touches
none of them. (`git diff f3e4e93`, the published-equivalent baseline,
additionally shows the `fuzz/` tooling and `reports/fuzz-audit.md` added by the
audit commit `4a8f299`; this fix does not alter those.)

## 5. Self-judgement per evasion family

* **`D6|cap/nan` — FIXED.** A `NaN` child cap fires D6 (provably-≤ is
  `False`-safe); a `NaN` parent cap fires D6 on any child; a `NaN` sibling sum
  poisons D5. CLI evidence: `evasion_D6_nan.json` now `D6 e2`, exit 1;
  `evasion_D5_nan_sibling.json` now `D6 e3`, exit 1; descriptor and attenu
  `cap-raise-NaN` both `D6:e2`. Fuzz `cap/nan` evasions 100 → 0.
* **`D6|cap/bigint-plus-one` — FIXED.** The limit is preserved as an exact
  `int`, so `2⁵³+1 > 2⁵³` fires D6, while `2⁵³ → 2⁵³` stays clean. CLI
  evidence: `evasion_D6_bigint.json` now `D6 e2`, exit 1. Fuzz
  `cap/bigint-plus-one` evasions 100 → 0.

Both families closed; fuzz total evasions **0**, and the fix is monotone (dev
bench, dev_ext, pytest, and every non-D6 fuzz bucket unchanged).
