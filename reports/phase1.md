# SubGrant — Phase 1 report

Date: 2026-11-11 · Local build · Python 3.11+ (developed on 3.13), stdlib
runtime, `pytest` for tests.

## 1. What was built

```
subgrant/
  __init__.py     version (0.1.0)
  patterns.py     closed resource-pattern grammar + subsumption (§2 of SPEC)
  graph.py        dgraph/1 load + full structural validation (input errors)
  checks.py       D1–D8 checks + policy-pack loader + effective-budget logic
  report.py       hash-chained evidence pack (JSON) + Markdown + verifier
  cli.py          python -m subgrant verify|report  (exit 0/1/2)
  __main__.py     module entry point
schema/dgraph-1.json         JSON Schema (documentary; Python does real validation)
packs/delegation-policy-v1.json   pinned policy pack (max_depth 6, 8 protected actions)
bench/
  generate_dev.py  deterministic generator (seed 20261109), no RNG
  score.py         scorer -> bench/dev/score.json + printed table
  dev/cases.jsonl  120 generated cases
  dev/manifest.json  {count, seed, cases_sha256}
  dev/score.json   scorer output
tests/            pytest suite (patterns, graph, checks, report, cli, bench)
README.md SPEC.md DECISIONS.md STATUS.md
reports/phase1.md
```

The verifier is a pure pipeline: `load_graph` validates structure and raises
`GraphError` (CLI exit 2) for any schema problem; `run_checks` then produces
findings over a clean graph; `report.build_pack` records a run as a tamper-
evident hash chain.

## 2. Tests

`python -m pytest -q` → **91 passed** (0 failed).

Coverage: pattern subsumption truth table (incl. `db` vs `db/*`, `dbx`, `*`
cases, invalid patterns rejected, no-joint-coverage); window containment across
all bounded/unbounded combinations; each D-class with one positive and one
negative case; D5's missing-cap convention (and that it is blocked by the D1/D6
gate) and the single-child-never-fires case; input errors (two roots, zero
roots, dangling parent, duplicate id, cycle, bad pattern, bad data-class enum,
bad purpose enum, bad timestamp, depth_budget off-root, missing evidence ref,
unknown node, duplicate cap, bad schema tag) raising schema errors; CLI exit
codes 0/1/2 and `--json`; evidence-pack hash chain verifying and detecting
payload edit, entry drop, reorder, and header tamper; bench regeneration
byte-identical and GATE 1.

## 3. Bench metrics

```
class     planted  detected   recall
D1              8         8    1.000
D2              6         6    1.000
D3              6         6    1.000
D4              6         6    1.000
D5              8         8    1.000
D6              8         8    1.000
D7              6         6    1.000
-------------------------------------
D8 detected: 4 of 4 (scored separately — presence-only, not a GATE 1 class)
clean cases: 68   FP cases: 0   FP rate: 0.000   FP findings: 0
extra findings on planted cases: 0
```

Composition (verified): D1×8, D2×6, D3×6, D4×6, D5×8, D6×8, D7×6, D8×4, clean×68
= 120. Clean set includes 10 restatement chains, 8 deep valid chains (depth
4–6), 8 wide valid fan-outs (3–5 children, cap sums ≤ parent), 8 tightened
chains, and 34 mixed valid graphs (depth 2–4). Node kinds/tiers, resource
patterns, cap names, and purposes are varied across cases by index-driven
selection (no RNG), so the verifier cannot pass by memorizing shapes.

Determinism: re-running `bench.generate_dev` reproduces `cases.jsonl`
byte-identically; `manifest.cases_sha256` matches the file digest (asserted in
`tests/test_bench.py`).

### Extra-findings investigation

**Extra findings on planted cases: 0. Clean false positives: 0.** No
investigation was forced — the generator and verifier agreed on the first run.
The construction choices that keep planted cases single-finding (each verified
by the zero-extra result and by the per-class tests) were:

- D1 planting adds a non-protected element on exactly one authority dimension,
  so it cannot also trip D6 (caveats untouched) or D7 (no protected action).
- D2 chains are sized so **exactly one** edge exceeds the effective budget
  (last edge only); intermediate edges restate and stay within budget.
- D3 uses a no-redelegation parent with a single otherwise-valid child; the
  pinned D6 excludes redelegation, so only D3 fires.
- D5 children each pass D1 and D6 (carry the cap at a share ≤ parent), so the
  D1/D6 gate is satisfied and only the parent's cap-sum triggers D5. The
  missing-cap convention was deliberately **not** used to plant D5 (omitting a
  cap trips D6 first); this is documented and unit-tested rather than planted.
- D7 keeps the protected action present on every ancestor (so no D1), issued to
  a T2/T3 holder by a non-root issuer.
- All planted/clean edges except the D8 cases carry `evidence.kind !=
  "none"`, so no stray D8.

## 4. GATE 1 self-judgement

**GATE 1: PASS.**
- Per-class recall D1–D7: all **1.000** (D1 8/8, D2 6/6, D3 6/6, D4 6/6, D5 8/8,
  D6 8/8, D7 6/6).
- Clean false-positive cases: **0** (FP rate 0.000, 0 FP findings over 68 clean cases).
- pytest: **green (91 passed)**.

(D8 is scored separately and is not a GATE 1 class; 4/4 detected.)

## 5. Semantic decisions taken

Recorded in `DECISIONS.md`:
- D-001 `purposes` set-valued (the design's "purpose enum" → closed-vocabulary set).
- D-002 `depth_budget` on root only; effective budget = `min(max_depth, root.depth_budget)`.
- D-003/D-004 `issued_at` required; timestamp grammar exactly `YYYY-MM-DDTHH:MM:SSZ`.
- D-005 single-pattern resource subsumption (no joint coverage; conservative).
- D-006 D3 reported on the child; D6 does not cover redelegation.
- D-007 D5 pinned cap-sum mechanic, gated by children passing D1/D6, reported on parent.
- D-008 D7 v1 direct-grant-from-root rule.
- D-009 D8 presence-only; `evidence.ref` null only when kind none.
- D-010 root skips parent-relative checks (D1/D3/D4/D6); D2/D7/D8 apply to all edges.
- D-011 deterministic finding order.
- D-012 structural problems are input errors (exit 2), never findings.
- D-013 evidence-pack hash-chain construction.

## 6. Known limitations

- **No signature verification** — D8 is presence-only; cryptographic validity is
  the source format's verifier's job, out of scope for v1.
- **Single-pattern subsumption is conservative** — resource set subset requires
  each child pattern to be covered by one parent pattern; joint coverage by
  several parent patterns is not honored and may raise a conservative D1.
- **D7 is the pinned v1 rule** — a direct-grant-from-root heuristic, not full
  graph path-reachability analysis.

## 7. Not done / Phase 2 notes

Out of scope for Phase 1 and untouched here: normalizers (UCAN JWT, RFC 8693
act-chains, attenu-guard bundle, framework handoff descriptors → `dgraph/1`);
baselines scored on Part A (attenu-guard verifier, a naive per-edge subset
checker expected to miss D5/D7, UCAN reference validation); SARIF output; the
Part B framework-default audit; and the sealed holdout with pre-registered
predictions for GATE 2. `SPEC.md` is written to be sufficient for a Phase 2
session without this prompt. No publication assets, no LICENSE decision, no
README polish beyond a factual local draft — Phase 3, on the owner's separate
confirmation.
