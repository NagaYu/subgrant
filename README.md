# SubGrant

**An offline, format-neutral verifier for agent delegation chains.** SubGrant
checks whether authority only ever *narrows* when one agent delegates to
another — across token formats and framework handoffs — without running any of
the agents. Same input, same findings: no model calls, no network.

---

## 1. What it is / is not

SubGrant is three things:

- a **verifier** that reads a delegation chain and reports where a child edge
  holds more authority than its parent;
- a **public benchmark** of planted and clean delegation chains, with a scoring
  rule and baselines; and
- a **framework-default audit** of how eight popular agent frameworks hand
  authority from one agent to the next by default.

It is **not** a runtime enforcer — that layer exists, and
[attenu-guard](https://github.com/attenu-io/attenu-guard) (Apache-2.0) is
credited as the in-process enforcer SubGrant is compared against. It is **not** a
token format — [UCAN 1.0](https://github.com/ucan-wg), Biscuit, and
[RFC 8693](https://www.rfc-editor.org/rfc/rfc8693) already exist. SubGrant reads
delegation chains *offline* and reports narrowing violations *deterministically*.

## 2. Headline results

All numbers below are audited (see `reports/`). Recall is per check-class; a
planted case is counted detected only when the finding matches on **both** the
check class and the edge.

| Evaluation | Result |
| --- | --- |
| **Dev bench** (120 cases, public) | recall D1–D7 = **1.000** each; clean FP **0/68**; D8 **4/4** — GATE 1 **PASS** |
| **Sealed holdout** (120 cases, *not published*) | recall D1–D7 = **1.000** each; D8 **4/4**; clean FP **0/68**; extra findings **0** — GATE 2 **PASS** |
| **Baseline B0** (naive per-edge) | **0.000** on D5 and D7; **0.167** on D2; matches SubGrant on D1/D3/D4/D6 |
| **Baseline B2** (UCAN-spec) | misses the D7 case and **half** the D4 cases |
| **attenu-guard vectors** | agrees on **4 of 5**; the one divergence is a corrupted signature |
| **Framework audit** (8 frameworks, 2026-11-11) | **none** checks child ⊆ parent by default; **none** binds delegation authority on the handoff |

Details:

- **Sealed holdout.** A 120-case holdout was authored by a separate session.
  SubGrant's predictions were **pre-registered in git before the holdout was
  authored**, by a session that never ran the verifier; the holdout itself is
  **not published** (see §7). GATE 2 passed on the first and only scoring run.
- **Baselines (on dev).** A naive per-edge checker (**B0**) matches SubGrant on
  D1/D3/D4/D6 but scores **0.000 on D5** (it cannot aggregate fan-out
  recombination) and **0.000 on D7** (no trust-tier/reachability logic), and
  **0.167 on D2** (it checks only the raw `max_depth`, missing breaches planted
  via a tighter root `depth_budget`). A UCAN-1.0-spec checker (**B2**) catches
  scope/ability widening but **misses the D7 case and half the D4 cases** (its
  window rule is `exp`-only, so it cannot see a start-time violation). Against
  attenu-guard's own interop vectors, SubGrant **agrees on 4 of 5**; the single
  divergence is `reject_bad_signature` — a corrupted signature that a
  presence-only offline verifier *cannot* see (stated as a limitation, §9, not
  smoothed over).
- **Framework-default audit.** Across eight frameworks (documented defaults as
  of 2026-11-11), **none checks child ⊆ parent by default, and none records a
  delegation-authority binding on the handoff** — so D8 fires on every edge of
  every scenario. The two inherit-by-default frameworks
  (**LangGraph/deepagents** and the **Claude Agent SDK**) additionally propagate
  a protected action (`funds.transfer`) down to the third agent, which SubGrant
  flags as a confused-deputy reachability breach (**D7**).

## 3. Quickstart

Runtime is the Python standard library only (Python ≥ 3.11). No install step.

```bash
# verify a graph: exit 0 (clean) / 1 (findings) / 2 (input error)
python -m subgrant verify path/to/graph.json

# normalize a source format to dgraph/1, then verify
python -m subgrant normalize ucan path/to/chain.json
python -m subgrant normalize ucan path/to/chain.json | python -m subgrant verify -

# SARIF 2.1.0 output (D1–D7 = error, D8 = note)
python -m subgrant verify --sarif path/to/graph.json
```

### Worked example — a D5 fan-out (bench/dev `case-0027`)

A parent edge `e1` grants a `100`-call budget; it fans out to four children
(`e2`–`e5`), **each** granted `30` calls. Every child individually stays within
its parent, so a per-edge checker sees nothing. But `4 × 30 = 120 > 100`: the
children *recombine* to exceed the parent. SubGrant reports **D5 on the parent
edge `e1`**. (JSON reformatted for readability; semantics are `case-0027`.)

```json
{
  "schema": "dgraph/1",
  "nodes": [
    {"id": "n0", "kind": "service", "trust_tier": "T0"},
    {"id": "n1", "kind": "agent", "trust_tier": "T1"},
    {"id": "n2", "kind": "agent", "trust_tier": "T1"},
    {"id": "n3", "kind": "agent", "trust_tier": "T1"},
    {"id": "n4", "kind": "agent", "trust_tier": "T1"},
    {"id": "n5", "kind": "agent", "trust_tier": "T1"}
  ],
  "edges": [
    {"id": "e1", "parent_edge": null, "issuer": "n0", "holder": "n1",
     "authority": {"tools": ["tool.fetch", "tool.summarize"], "actions": ["index.update", "report.generate"], "resources": ["files/reports/*"], "data_classes": ["public"]},
     "caveats": {"issued_at": "2026-01-01T00:00:00Z", "expires_at": "2026-06-30T00:00:00Z", "redelegation": true, "caps": [{"name": "api_calls", "limit": 100}], "purposes": ["read"]},
     "evidence": {"kind": "attestation", "ref": "att:e1"}},

    {"id": "e2", "parent_edge": "e1", "issuer": "n1", "holder": "n2",
     "authority": {"tools": ["tool.fetch", "tool.summarize"], "actions": ["index.update", "report.generate"], "resources": ["files/reports/*"], "data_classes": ["public"]},
     "caveats": {"issued_at": "2026-01-01T00:00:00Z", "expires_at": "2026-06-30T00:00:00Z", "redelegation": true, "caps": [{"name": "api_calls", "limit": 30}], "purposes": ["read"]},
     "evidence": {"kind": "attestation", "ref": "att:e2"}}

    // e3, e4, e5 are identical to e2 (holders n3, n4, n5; cap api_calls = 30 each)
  ]
}
```

```console
$ python -m subgrant verify case-0027.json --json
[
  {"class": "D5", "edge": "e1"}
]
$ echo $?
1
```

## 4. Check classes (D1–D8)

One line each; full definitions in `SPEC.md` §6, pinned mechanics in
`DECISIONS.md`. For an edge `e` with parent `p`, root edges skip the
parent-relative checks (D1, D3, D4, D6).

- **D1 Amplification** — `e`'s tools, actions, resources, or data-classes are
  not a subset of `p`'s.
- **D2 Depth breach** — `e`'s depth exceeds the effective budget
  (`pack.max_depth`, tightened by the root edge's `depth_budget`).
- **D3 Re-delegation breach** — `p` has `redelegation: false` yet `e` exists
  (reported on the child `e`).
- **D4 Lifetime breach** — `e`'s validity window is not contained in `p`'s.
- **D5 Fan-out recombination** — among siblings that each pass D1/D6, the sum of
  an additive cap exceeds `p`'s limit (reported on the parent). *v1: additive
  caps only.*
- **D6 Caveat drop / weakening** — a cap in `p` is absent or raised in `e`, or
  `e`'s purposes are not a subset of `p`'s.
- **D7 Confused-deputy reachability** — `e` grants a protected action to a
  `T2`/`T3` holder and `e`'s issuer is not the root authority. *v1: the
  direct-grant-from-root rule, not full path reachability.*
- **D8 Unbound delegation** — `e.evidence.kind == "none"`. *Presence only; no
  signature verification.*

## 5. Formats

The native document is **`dgraph/1`** (`SPEC.md` §1). Normalizers map four source
formats onto it:

| Format | Source | Notes |
| --- | --- | --- |
| **UCAN** | UCAN 1.0 delegation chains | `prf` links give the parent relation |
| **RFC 8693** | token-exchange `act` chains | the `act` chain *is* the delegation chain |
| **attenu-guard** | Delegation-Token chains (compact JWS) | payloads only; scopes → resources |
| **descriptor** | framework handoff descriptors | one edge per generation |

Each format carries only some of the `dgraph/1` dimensions; the dropped
dimensions (and the constants used to fill them, chosen so they can neither
create nor mask a finding) are documented in `SPEC.md` and
`DECISIONS.md` **D-014–D-019**. This bounds what each format can express — which
the benchmark measures directly (§6).

## 6. The benchmark

- **Dev** (`bench/dev/`, 120 cases, public): **D1×8, D2×6, D3×6, D4×6, D5×8,
  D6×8, D7×6, D8×4, clean×68**. Generated deterministically (no RNG); the
  case-file digest is anchored in the manifest and asserted by the tests.
- **dev_ext** (`bench/dev_ext/`): 24 dev cases re-expressed in each format and
  round-tripped (normalize → verify). Round-trip results: **ucan 13/13,
  rfc8693 8/8, descriptor 11/11** of the *expressible* pairs; the remaining
  pairs are format-inexpressible, each with a recorded reason in the manifest
  (e.g. UCAN drops caps, so it cannot express D5/D6).
- **Scoring rule**: a planted case is detected only when a finding matches on
  **both class and edge**; clean cases must raise no D1–D7 finding; extra
  findings on planted cases are counted separately.
- **Sealed holdout**: a second 120-case corpus, authored independently, with
  SubGrant's predictions **pre-registered in git before** the holdout was
  written. It is **sealed and never published** — this repository contains only
  the aggregate result (GATE 2 PASS; numbers in §2), never the holdout cases,
  generator, predictions, or score.

## 7. Framework-default audit (Part B)

What each framework does **by default** when an orchestrator delegates to a
sub-agent that delegates to a third agent — not what a careful developer could
configure. Full table, per-framework notes, and sources in `audit/frameworks.md`.

| Framework | Default posture | Checks child ⊆ parent? | Handoff evidence | SubGrant findings |
| --- | --- | --- | --- | --- |
| LangGraph / deepagents | inherit-all | No | none | **D7 e3**; D8 e1,e2,e3 |
| OpenAI Agents SDK | scoped | No | none | D8 e1,e2,e3 |
| CrewAI | scoped (delegation off by default) | No | none | D8 e1,e2,e3 |
| AutoGen (AgentChat) | scoped | No | none | D8 e1,e2,e3 |
| Google ADK | scoped | No | none | D8 e1,e2,e3 |
| Claude Agent SDK | inherit | No | none | **D7 e3**; D8 e1,e2,e3 |
| Pydantic AI | scoped (`inherit_tools=False`) | No | none | D8 e1,e2,e3 |
| A2A (reference) | scoped | No | none (card signed for identity) | D8 e1,e2,e3 |

**Headline:** no framework checks child ⊆ parent by default, and none records a
delegation-authority binding on the handoff (D8 fires on every edge). The two
inherit-by-default frameworks also propagate a protected action to the third
agent (D7 on `e3`). These findings describe the *scenario as modeled*, which
encodes each framework's documented default — not an overall security judgement
of the framework.

## 8. Layout

```
subgrant/             core verifier (graph, patterns, checks, report, cli, sarif)
subgrant/normalizers/ ucan, rfc8693, attenu, descriptor → dgraph/1
subgrant/baselines.py B0 naive + B2 UCAN-spec baseline checkers
packs/                pinned policy pack (delegation-policy-v1)
bench/                generators + scorers; bench/dev/, bench/dev_ext/
fixtures/attenu/      vendored attenu-guard interop vectors + PROVENANCE.md
audit/                framework descriptors + frameworks.md
tests/                pytest suite
SPEC.md DECISIONS.md  specification + pinned mechanics
reports/              phase1.md, phase2.md, gate2.md
```

## 9. Limitations (honest, prominent)

- **Presence-only evidence.** D8 checks that evidence is present, not valid —
  SubGrant performs **no cryptographic verification**. It agrees with
  attenu-guard on scope/depth/window/cap narrowing but cannot see a corrupted
  signature (the one B1 divergence, §2).
- **Resource subsumption is single-pattern only.** A child resource must be
  covered by *one* parent pattern; joint coverage by several parent patterns is
  out of scope (conservative — may raise a D1 a human would accept).
- **The framework audit is a pinned documentation snapshot** (2026-11-11) from
  public docs/source — not live testing. Some patch-level versions are
  unconfirmed and marked for re-pinning.
- **attenu scopes are modeled as resources**, so SubGrant's D7 (which keys off
  actions) **never fires on attenu chains**. This is a deliberate, recorded
  mapping (`DECISIONS.md` D-017) that lets the two verifiers be honestly
  compared.

## 10. License & contact

**All Rights Reserved** — see [`LICENSE`](LICENSE). These Materials are made
public solely so they can be read and evaluated; no license to use, copy, or
create derivative works is granted.

Licensing or transfer inquiries: **https://nagayu-portfolio.nagayu.workers.dev/en**
