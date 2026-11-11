# SubGrant — Phase 2 report

Date: 2026-11-11 · Local build · Python 3.11+ (developed on 3.13), stdlib
runtime, `pytest` for tests. Phase 2 adds normalizers, a multi-format dev
extension (dev_ext), baselines, SARIF output, and the Part B framework-default
audit. **GATE 2 is not judged in this phase** (see §7).

## 1. What was built

```
subgrant/normalizers/__init__.py   registry + common constants + NormalizeError
subgrant/normalizers/ucan.py       UCAN delegation-chain -> dgraph/1
subgrant/normalizers/rfc8693.py    RFC 8693 act-chain -> dgraph/1
subgrant/normalizers/attenu.py     attenu-guard Delegation-Token chain -> dgraph/1
subgrant/normalizers/descriptor.py framework handoff descriptor -> dgraph/1
subgrant/baselines.py              B0 naive checker, B2 UCAN-spec checker
subgrant/sarif.py                  SARIF 2.1.0 emitter
subgrant/cli.py                    + normalize <format> <file>; verify --sarif
bench/generate_dev_ext.py          dev_ext generator (hand inverters + build/check)
bench/dev_ext/{ucan,rfc8693,descriptor}/*.json, manifest.json, score_ext.json
bench/score_ext.py                 dev_ext round-trip scorer
bench/score_baselines.py           baseline scorer over dev 120 + vectors + dev_ext
fixtures/attenu/                   5 vendored attenu-guard interop vectors + PROVENANCE.md
audit/descriptors/<framework>.json 8 framework descriptors (§2.4 format)
audit/frameworks.md                Part B table + per-framework notes + sources
```

Core (`patterns.py`, `graph.py`, `checks.py`) is unchanged — no core bug was
found, so no core edit was made. New capability is additive.

The CLI now supports `python -m subgrant normalize <format> <file>` (prints the
`dgraph/1` JSON; piping into `verify` works) and `python -m subgrant verify
--sarif <graph.json>`; plain `verify`/`report` exit codes are unchanged.

## 2. Normalizer mapping tables

Common constants (dimensions a format does not carry): `tools=[]` (abilities →
`actions`), `caps=[]`, `purposes=["read"]`, `data_classes=["internal"]`,
non-root holder tier `T2`, root authority `T0`, edge ids `e1..eN` root-first.
Malformed input → `NormalizeError` (CLI exit 2). Details in DECISIONS D-014.

### 2.1 ucan (DECISIONS D-015)
| dgraph/1 field | source |
| --- | --- |
| issuer / holder | `iss` / `aud` |
| actions | union of `att[].can` |
| resources | each `att[].with` with leading `<scheme>://` stripped; `*` kept; must `validate_pattern` |
| parent_edge | the single `prf` index (0/multiple/forward/invalid → input error) |
| issued_at | `nbf`; else **inherit parent link's issued_at**; root w/o `nbf` → `2026-01-01T00:00:00Z` |
| expires_at | `exp` (null → null) |
| evidence | `{"kind":"signature","ref":"ucan:<i>"}`; redelegation=true |
| tools/caps/purposes/data_classes | constants |

### 2.2 rfc8693 (DECISIONS D-016)
| dgraph/1 field | source |
| --- | --- |
| edges | edge 0 = `iss→sub`; each nested `act` adds `prev_holder → act.sub` (outermost = most recent) |
| actions | level `scope` split on whitespace; **a level with no scope inherits the previous level's actions** |
| issued_at / expires_at | `iat` / `exp`, **shared by all edges** |
| evidence | `{"kind":"attestation","ref":"rfc8693:act-chain"}`; redelegation=true |
| resources/tools/caps/purposes/data_classes | constants (resources `[]`) |

### 2.3 attenu (DECISIONS D-017; mapping derived from vendored material, see `fixtures/attenu/PROVENANCE.md`)
attenu-guard serializes a chain as compact JWS **Delegation Tokens**; only the
payloads are decoded (no signature verification). Mapping table:

| dgraph/1 field | source (DT payload) |
| --- | --- |
| edges | one per token, root-first by `del_depth` (0..n-1 linear) |
| issuer / holder | root authority = `iss` (T0); edge k>0 = `sub[k-1] → sub[k]` (T2) |
| resources | `authorization_details[].scopes`, scope grammar → pattern grammar (`.`→`/`: `crm.*`→`crm/*`) |
| actions / tools | `[]` (scopes modeled as resources) |
| caps | numeric `max` constraints → `{name:key, limit:max}`; rank/min/one_of/prefix ignored (v1) |
| depth_budget | root `del_max_depth` |
| issued_at / expires_at | `iat` / `exp` (unix seconds) |
| evidence | `{"kind":"signature","ref":"attenu:<jti>"}`; redelegation=true |

Consequence (reported, not hidden): modeling scopes as resources means SubGrant
*agrees* with attenu that `crm.read ⊆ crm.*`; but SubGrant's D7 keys off
`actions` (empty here) so it does not fire on attenu chains, and SubGrant is
blind to signature/par_hash/encoding failures — the B1 divergences (§4).

### 2.4 descriptor (DECISIONS D-018)
| dgraph/1 field | source |
| --- | --- |
| edges | one per generation; root edge `gen0→gen0`; edge i>0 = `gen[i-1]→gen[i]` |
| authority | `inherit` → parent edge's authority verbatim; `scoped` → generation i's; `none` → empty |
| windows | uniform `issued_at=2026-01-01T00:00:00Z`, `expires_at=null`; depth_budget absent; redelegation=true |
| evidence | "signed token"→signature, "logged attestation"→attestation, "none"→none (ref `descriptor:<framework>`) |
| data_classes | `["internal"]` |

The §2.4 contract shows 2–3 generations; the normalizer accepts any N≥1 linear
generations so dev_ext can represent longer chains.

## 3. dev_ext results

24 cases selected (§3): planted #1,#2 of D1–D7 (14), planted D8 #1 (1), and 9
cleans (first 2 restatement/deep/wide/tightened + first 1 mixed). Selected ids
and per-format expressibility are listed in `bench/dev_ext/manifest.json`.

Representations are built by hand-inverting the §2 mapping; a (case, format)
pair is expressible only when the format can structurally and dimensionally
reproduce the case's `expected` findings (DECISIONS D-019 — the §3 rfc8693
fan-out escape generalized to all formats/dimensions). `expected` was never
edited.

| format | expressible | round-trip passed | failed | inexpressible |
| --- | --- | --- | --- | --- |
| ucan | 13 | 13 | 0 | 11 |
| rfc8693 | 8 | 8 | 0 | 16 |
| descriptor | 11 | 11 | 0 | 13 |

**All expressible representations round-trip to their expected findings (0
mismatches).** Inexpressibility is always a genuine format limit, confirmed by
build-then-verify, not a bug:

- **ucan** drops tools/caps/purposes/evidence and forces non-root tier T2 → cannot
  express D1-via-tools, D5, D6, D8, or a D7 chain with a *trusted* T1 intermediate
  (it over-flags D7 on the depth-3 D7 case). It carries actions/resources/windows,
  so it expresses D1-via-actions, both D4 cases, the depth-2 D7 case, and all cleans.
- **rfc8693** carries only actions (+ one shared window) → expresses D1-via-actions,
  both D7 chains? no: it also forces T2 on intermediates, so only the depth-2 D7 is
  expressible; it cannot express tools/resources D1, D2-via-depth_budget, D3, D4,
  D5, D6, D8, or fan-outs. Expresses the clean chains.
- **descriptor** carries tools/actions/resources/caps/purposes per generation →
  expresses both D1 cases and both D6 cases; its root edge is issued by the root
  authority, so it expresses the depth-3 D7 (on e3) but not the depth-2 D7 (on e2);
  it cannot express D2-via-depth_budget, D3, D4 (uniform window), the per-edge D8,
  or fan-outs.

No mismatch required a representation or normalizer fix: every expressible case
passed on the first build/verify, and every inexpressible case was a dropped
dimension or an unrepresentable shape, recorded with its reason in the manifest.

## 4. Baselines

Scored with the same comparison rule as `bench/score.py` (a planted case is
detected only when class **and** edge match). Full data in
`bench/dev/score_baselines.json`.

### Recall over the dev 120 (per-class D1–D7)

| verifier | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | clean FP | extras |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **SubGrant** | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 4/4 | 0 | 0 |
| **B0 (naive)** | 1.000 | 0.167 | 1.000 | 1.000 | 0.000 | 1.000 | 0.000 | 0/4 | 0 | 0 |

B0 matches its pre-registered expectation: recall 0 on **D5** (no fan-out
aggregation) and **D7** (no tier/reachability), misses **D2** cases planted via
a root `depth_budget` (catches only the 1 of 6 that breaches the raw
`max_depth`), and misses all **D8** (no evidence check). It raises no clean false
positives and no extras on what it does check.

### B2 (UCAN-spec) over the UCAN-expressible dev_ext cases

| class | recall | cases |
| --- | --- | --- |
| D1 | 1.000 | 1 |
| D4 | 0.500 | 2 |
| D7 | 0.000 | 1 |

B2 catches scope/ability/resource widening (D1) and an `exp` that exceeds the
parent (D4), but its UCAN-1.0 rule is **exp-only** for the window, so it misses
the D4 case planted as a *start-time* (issued-before-parent) violation (1 of 2),
and it has no D7/D5/D8 concept. No clean false positives.

### B1 (attenu-guard) per vendored interop vector

| vector | attenu verdict | SubGrant | agree? |
| --- | --- | --- | --- |
| valid_chain | accept | (clean) | ✅ |
| reject_widened_scope | reject (not_narrower) | D1 e3 | ✅ |
| reject_depth_exceeded | reject (depth_invalid) | D2 e3 | ✅ |
| reject_nonmonotonic_exp | reject (expired) | D4 e3 | ✅ |
| reject_bad_signature | reject (signature_invalid) | (clean) | ❌ |

B1(b) (installing attenu-guard's own verifier into a throwaway venv and running
the 24 dev_ext graphs through it) was **not run**: no install was attempted, to
keep the project zero-maintenance and fully offline per Phase 2 §0 (network is
for vendoring evidence only). Recorded as skipped; B1(a) above is the scored
attenu comparison.

### Divergences (individually, with graph facts)

- **B0 vs SubGrant — D5 (×8):** every fan-out recombination (e.g. case-0027: a
  parent with cap `api_calls=100` and four children at 30 each — 4 × 30 = 120 >
  100 — each individually valid) is invisible to B0's per-edge checker; SubGrant
  flags D5 on the parent.
- **B0 vs SubGrant — D7 (×6):** e.g. case-0043 routes `data.delete` to a T2
  holder via a non-root issuer; B0 has no tier logic and accepts it.
- **B0 vs SubGrant — D2 (×5):** case-0009/0010/0012/0013/0014 breach a root
  `depth_budget` tighter than `max_depth`; B0 checks only `max_depth`.
- **B0 vs SubGrant — D8 (×4):** B0 has no evidence check.
- **B2 vs SubGrant — D7 (case-0043):** SubGrant flags the confused-deputy reach;
  B2 (attenuation-only) has no such concept.
- **B2 vs SubGrant — D4 (case-0022):** a child whose window *starts before* its
  parent's; SubGrant's full window containment flags it, B2's exp-only rule does not.
- **B1 vs SubGrant — reject_bad_signature:** attenu rejects a corrupted
  signature; SubGrant reads only decoded payloads (presence-only, v1) and
  accepts. This is the sharp boundary of a format-neutral offline verifier: it
  sees scope/depth/window/cap narrowing, not the format's own cryptography.

These divergences are reported, not smoothed; no side was tuned to reduce them.

## 5. Part B — framework-default audit

Full table, per-framework notes, and sources are in `audit/frameworks.md`;
descriptors are in `audit/descriptors/`. Each descriptor is normalized through
§2.4 and run through the core verifier.

| Framework | Default posture | Checks child⊆parent? | Handoff evidence | SubGrant findings |
| --- | --- | --- | --- | --- |
| LangGraph / deepagents | inherit-all | No | none | D7 e3; D8 e1,e2,e3 |
| OpenAI Agents SDK | scoped | No | none | D8 e1,e2,e3 |
| CrewAI | scoped (delegation off by default) | No | none | D8 e1,e2,e3 |
| AutoGen (AgentChat) | scoped | No | none | D8 e1,e2,e3 |
| Google ADK | scoped | No | none | D8 e1,e2,e3 |
| Claude Agent SDK | inherit | No | none | D7 e3; D8 e1,e2,e3 |
| Pydantic AI | scoped (`inherit_tools=False`) | No | none | D8 e1,e2,e3 |
| A2A (reference) | scoped | No | none (card signed for identity) | D8 e1,e2,e3 |

**Headline:** no framework checks child ⊆ parent by default, and none records a
delegation-authority binding on the handoff (D8 fires on every edge of every
scenario). The two inherit-all frameworks — **LangGraph/deepagents** and the
**Claude Agent SDK** — additionally propagate the protected action
`funds.transfer` to the third agent, which SubGrant flags as a confused-deputy
reachability breach (**D7**). The most newsworthy single finding (a candidate
Phase 3 beachhead) is the deepagents inherit-all + replace-not-intersect default.
Versions were read on 2026-11-11; several patch levels could not be confirmed
from public pages and are marked for re-pinning at repo creation.

## 6. GATE 1 regression confirmation

- **pytest: 128 passed** (Phase 1 + Phase 2), 0 failed.
- **Dev bench re-scored GATE 1 = PASS**: per-class recall D1–D7 all **1.000**,
  clean FP cases **0**, D8 detected **4/4** — identical to Phase 1.
- **`bench/dev/cases.jsonl` sha256 unchanged**:
  `6858bed2b96ecd855cc862f7cf69e684e32ae982b5781dd7b7574da5ccf3c706` (asserted
  in `tests/test_phase2_bench.py`).
- dev_ext regenerates byte-identically; core modules untouched.

## 7. GATE 2 statement

**GATE 2 is NOT judged in this phase.** The sealed holdout is authored
independently in a later session, with predictions pre-registered before
authoring. Nothing in Phase 2 was created against, tuned to, or evaluated on any
holdout; no holdout was created, approximated, or inspected. dev_ext reuses only
the *public* dev cases whose truth is already known.

## 8. Known limitations and Phase 3 notes

- **attenu scopes → resources** (D-017): a deliberate, recorded mapping so the
  two verifiers can be honestly compared; it means SubGrant's D7 never fires on
  attenu chains and SubGrant cannot see signature/par_hash failures.
- **B1(b) not run**: attenu-guard's own verifier was not installed (zero-
  maintenance / offline). Only B1(a), the vendored-vector comparison, is scored.
- **dev_ext coverage is bounded by format expressibility** (D-019): e.g. D8 is
  expressible in none of the three formats, so no format round-trips the D8 case;
  D2-via-depth_budget and D3 are expressible in none. This is an honest property
  of the formats, documented per case in the manifest.
- **Part B is a pinned-snapshot audit** from public docs/source only (no installs,
  no live runs); some versions are unconfirmed at patch level and marked for
  re-pinning. SubGrant findings describe the modeled scenario, not an overall
  security judgement of each framework.
- **Phase 3** (separate, owner-confirmed): publication prep — clean export repo,
  HF dataset with dev only, a Static Space demo, entrance drafts — only on the
  owner's final confirmation of exact texts and targets. The sealed holdout +
  GATE 2 are authored independently before any publication.
