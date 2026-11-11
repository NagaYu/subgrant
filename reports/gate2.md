# SubGrant — GATE 2 report (sealed holdout)

**Verdict: PASS.** Scored exactly once, on the sealed 120-case holdout, against
the verifier at the pre-registered commit. This session changed nothing in
`subgrant/`, the holdout, or `PREDICTIONS.md`; the only addition is the holdout
scorer (`bench/score_holdout.py`), which reuses the dev scorer's comparison
logic verbatim.

---

## 1. Seal verification (§0)

All three checks **PASS**.

### Check 1 — predictions precede the holdout

`bench/holdout/PREDICTIONS.md` was added by commit `c0af74c` ("pre-register
holdout predictions"), which is the parent of `f57b8e6` ("author sealed holdout
(120 cases)") — the single commit that added `bench/holdout/cases.jsonl`,
`generate_holdout.py`, `manifest.json`, and `AUTHORING.md`. The prediction
commit therefore precedes every commit adding holdout cases or generator code.

```
f57b8e6  author sealed holdout (120 cases)      <- cases + generator + manifest + authoring
c0af74c  pre-register holdout predictions        <- PREDICTIONS.md (precedes the above)
bcbd286  Phase 2: normalizers, baselines, ...    <- verifier under test
f8665de  Phase 1: core verifier, dev bench, ...
```

### Check 2 — verifier byte-identical to the one predicted

`PREDICTIONS.md` names verifier commit
`bcbd286a8002fa4cdf61b00d923e03d4d6ddb5c4` (= `bcbd286`, the Phase 2 commit).

- `git diff bcbd286 HEAD -- subgrant/` → **empty** (the entire verifier tree is
  unchanged between the predicted commit and HEAD `f57b8e6`).
- Explicit stat over the three core files
  `subgrant/checks.py subgrant/patterns.py subgrant/graph.py` → **empty** (no
  change to their bytes or behavior).

The Phase 2 modules (`normalizers/`, `baselines.py`, `sarif.py`) existed already
at `bcbd286` and were not touched after it; the holdout commits added only
material under `bench/holdout/`.

### Check 3 — case-file hashes anchored

- `bench/holdout/cases.jsonl` sha256
  = `b751472852b487f04b32ef8053a4714c8ef33102fc3507657b4aa803d667c752`
  = `cases_sha256` in `bench/holdout/manifest.json` ✓
- `bench/dev/cases.jsonl` sha256
  = `6858bed2b96ecd855cc862f7cf69e684e32ae982b5781dd7b7574da5ccf3c706`
  = the anchored dev hash ✓

Holdout composition as loaded: D1×8 D2×6 D3×6 D4×6 D5×8 D6×8 D7×6 (= 48 planted)
+ D8×4 + 68 clean = 120, matching `PREDICTIONS.md` and `manifest.json` (count
120, seed 20261111).

---

## 2. Scoring table (one run)

Comparison rule (identical to the dev scorer): a planted case is detected iff a
finding matches it on **both class and edge**; clean cases must raise no D1–D7
finding; extra findings on planted cases are counted separately.

```
class     planted  detected   recall
D1              8         8    1.000
D2              6         6    1.000
D3              6         6    1.000
D4              6         6    1.000
D5              8         8    1.000
D6              8         8    1.000
D7              6         6    1.000
------------------------------------------------
D8 detected: 4 of 4 (scored separately)
clean cases: 68   FP cases: 0   FP rate: 0.000   FP findings: 0
extra findings on planted cases: 0
```

Written to `bench/holdout/score.json`.

### Prediction vs actual

| class | predicted recall | actual recall | result |
| --- | --- | --- | --- |
| D1 | 1.000 | 1.000 | met |
| D2 | 1.000 | 1.000 | met |
| D3 | 1.000 | 1.000 | met |
| D4 | 0.98  | 1.000 | beat |
| D5 | 0.95  | 1.000 | beat |
| D6 | 1.000 | 1.000 | met |
| D7 | 0.97  | 1.000 | beat |
| clean FP rate | 0.015 | 0.000 | beat (fewer FPs) |
| D8 detection | 4 of 4 | 4 of 4 | met |
| GATE 2 verdict | PASS | PASS | met |

Every class met or beat its pre-registered prediction. The three sub-1.0
predictions (D4, D5, D7 — the boundary/composite classes) all came in at 1.000,
and the predicted 1.5% clean FP rate came in at 0.0%.

---

## 3. GATE 2 verdict

**GATE 2 = PASS.**

Criterion by criterion:

- Per-class recall D1–D7 each ≥ 0.85: **D1=D2=D3=D4=D5=D6=D7=1.000** — all ≥ 0.85 ✓
- Clean false-positive rate ≤ 5%: **0/68 = 0.000 (0.0%)** ≤ 5% ✓

Both conditions hold, so the verdict is PASS with no partial credit and no
re-run. D8 (reported separately, not a gate criterion): 4 of 4 detected.

---

## 4. Disagreement investigation (§3)

For every one of the 120 cases, the verifier's findings equal the holdout's
`expected`:

- **Misses:** 0 (every planted D1–D7 and every D8 was detected on the exact
  expected edge).
- **Clean false positives:** 0 (no clean case raised any finding).
- **Extra findings on planted cases:** 0.

`bench/holdout/score.json` detail lists `missed`, `clean_fp`, and `extras` are
all empty. There are therefore **no disagreements to investigate** — no case
where findings ≠ expected, hence nothing adjudicated as "verifier wrong" or
"expectation wrong", and nothing to cite against SPEC or cross-check against
`AUTHORING.md`. The verifier and the independently authored holdout agree
completely, which is the strongest available evidence that the implementation
realizes the SPEC semantics the holdout author encoded from `SPEC.md` /
`DECISIONS.md`.

Disagreement counts: **0 misses, 0 FPs, 0 extras.**

---

## 5. Next step

GATE 2 is PASS, so the portfolio stop rule's fix-round / re-gate path does not
apply. **Phase 3 (publication prep) awaits the owner's separate confirmation**
— it is not started by this session. Nothing here is published; all work is
local.
