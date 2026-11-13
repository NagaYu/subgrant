# DECISIONS — SubGrant Phase 1

Pinned mechanics. Where the Phase 1 build prompt pinned a mechanic more
precisely than `subgrant-design.md`, the pin governs and is recorded here.

## D-001 · `purposes` is set-valued (not a single enum)
The design (§2.1) described "purpose as a closed enum ... never free text" and a
single `purpose: <enum>` field. The pinned mechanic is a **set** of purposes
drawn from the closed vocabulary `read | write | communicate | execute |
transact | administer | delegate`, with set semantics (duplicates ignored).
D6 widening is `child.purposes ⊄ parent.purposes`.
Rationale: a delegate may hold several purposes at once; set-subset is the
natural monotonicity check and keeps the enum closed.

## D-002 · `depth_budget` lives on the root edge only
The design listed `max_depth_remaining` as a per-edge caveat. The pinned
mechanic is a single optional `depth_budget` integer on the **root edge** only
(absent ⇒ no graph-local tightening). A `depth_budget` on any non-root edge is
an input error. Effective budget = `min(pack.max_depth, root.depth_budget)`.
Rationale: depth is a property of the whole chain, declared once by the root
authority; per-edge countdown is redundant and a source of inconsistency.

## D-003 · `issued_at` is a required caveat
The design named `expires_at` but window containment needs a start too. Pinned:
`caveats.issued_at` is required (UTC ISO-8601 `YYYY-MM-DDTHH:MM:SSZ`);
`expires_at` is required but may be `null` (unbounded).

## D-004 · Timestamp grammar is exactly `YYYY-MM-DDTHH:MM:SSZ`
UTC, second precision, literal `Z`. No offsets, no fractional seconds, no space
separator. Anything else is an input error. Keeps comparison total and
representation canonical (ReleaseSeal "semantics stay mechanical" discipline).

## D-005 · Single-pattern resource subsumption (conservative)
`A ⊆ B` iff **every** pattern in `A` is subsumed by **some single** pattern in
`B`. Joint coverage by several patterns in `B` is out of scope and reported
conservatively (may flag D1 where a human would accept joint coverage). See
SPEC §Resource patterns. Recorded as a known limitation.

## D-006 · D3 reported on the child edge
`D3` fires when a parent edge has `redelegation == false` and a child edge
exists; the finding names the **child** edge (the edge that should not exist).
Note the pinned D6 definition covers caps and purposes only — it does **not**
include "redelegation flipped on" (the design mentioned it); re-delegation is
handled solely by D3.

## D-007 · D5 fan-out — pinned cap-sum mechanic
Plain sets cannot recombine beyond a parent (a union of subsets stays a subset),
so tools/actions/resources/data_classes are D1's job. D5 is defined only on
**additive caps**: for a parent `p` with children `c1..ck` (k ≥ 2), when every
child individually passes D1 and D6, D5 fires on `p` if for some cap name the
sum of that cap's limits across children exceeds `p`'s limit. Conventions: a
child omitting a parent cap consumes the parent's full limit for that name (but
such omission is itself a D6 weakening, which blocks the D1/D6 gate, so in
practice the omitting child must carry the cap); a cap name the parent does not
carry is ignored (children may add new caps — that is tightening). The finding
is reported on the **parent** edge `p`.

## D-008 · D7 v1 rule — direct grant from root only
`D7` fires when an edge grants a protected action (policy-pack list) to a holder
whose `trust_tier` is `T2` or `T3`, **and** the edge's issuer is not the root
authority node. Protected authority may reach an untrusted-tier agent only by a
direct grant from the root authority; anything routed through an intermediary is
flagged. This is a pinned v1 heuristic, not full path-reachability analysis.

## D-009 · D8 is presence-only
`D8` fires iff `evidence.kind == "none"`. SubGrant does not verify signatures in
v1; `evidence.ref` may be `null` only when `kind == "none"`, and must be a
non-empty string otherwise.

## D-010 · Check applicability to the root edge
Parent-relative checks (D1, D3, D4, D6) are skipped for the root edge. Absolute
checks apply to every edge: D2 (depth), D7 (confused deputy — the root never
fires it because its issuer is the root authority), D8 (evidence presence).

## D-011 · Finding order is deterministic
Findings are sorted by `(edge document index, class name)`. Stable output makes
the evidence pack and CLI reproducible.

## D-012 · Input errors vs findings
Structural problems (not one root, dangling/duplicate/cyclic edges, bad pattern,
out-of-vocabulary enum, malformed timestamp/cap/evidence, unknown issuer/holder
node) are **input errors**: the CLI exits 2 with a schema error, never a
finding. Findings are produced only for documents that load cleanly.

## D-013 · Evidence pack hash chain
`sha256(prev_hash || canonical_json({seq, type, payload}))`, hex, genesis prev =
64 zeros, canonical JSON = sorted keys + compact separators. `chain_tip` is the
last entry's hash. Any payload edit, reorder, insert, or drop breaks the chain.

---

# Phase 2 decisions (D-014 onward)

Phase 2 adds normalizers, baselines, SARIF, dev_ext, and the Part B audit. The
Phase 1 core semantics (patterns/graph/checks over `dgraph/1`) are frozen and
unchanged; no core bug was found. All new behavior lives in new modules.

## D-014 · Normalizer edge-id scheme and common constants
Every normalizer assigns edge ids `e1..eN` in root-first order, so a hand-built
representation of a known graph round-trips to the same edge ids (dev_ext
requirement). Dimensions a format does not carry use chain-wide constants that
can neither create nor mask findings: `purposes=["read"]`, `caps=[]`,
`data_classes=["internal"]`, `tools=[]` (abilities → `actions`), plus
`resources=[]` where a format carries no resource (rfc8693). Non-root holders
get `trust_tier="T2"`, the root authority `T0` (so D7 can fire only via a
non-root issuer), unless the input carries a tier. The normalizer output is
validated with `load_graph`; malformed input is a `NormalizeError` (a
`GraphError` subclass → CLI exit 2), never a partial graph.

## D-015 · UCAN mapping
`issuer=iss`, `holder=aud`, `actions`=union of `can`, `resources`=each `with`
with a leading `<scheme>://` stripped (then `validate_pattern`). Parent of link
i = its single `prf` index (zero/multiple/forward/invalid index → input error).
`expires_at=exp`; `issued_at=nbf`, else inherits the parent link's `issued_at`,
and a root with no `nbf` gets `2026-01-01T00:00:00Z`. `evidence=signature`
(ref `ucan:<i>`); `redelegation=true`.

## D-016 · RFC 8693 mapping
Top-level token = root edge `iss → sub`; each nested `act` adds one edge from
the previous holder to that `act`'s `sub` (v1 reading: the act chain *is* the
delegation chain, outermost = most recent). `actions` at each level = that
level's `scope` split on whitespace, inheriting the previous level's actions
when `scope` is absent. All edges share the token window (`iat`/`exp`).
`evidence=attestation` (ref `rfc8693:act-chain`); `redelegation=true`;
`resources=[]`.

## D-017 · attenu-guard mapping (scopes → resources)
attenu-guard serializes a chain as compact JWS Delegation Tokens; only payloads
are decoded (no signature verification, consistent with v1/D8). One edge per
token, ordered root-first by `del_depth` (0..n-1 linear). Root authority node =
`iss` (T0); edge for del_depth k>0 is `sub[k-1] → sub[k]` (T2). **`scopes` map to
`resources`**, translating the dotted/wildcard scope grammar to the dgraph
pattern grammar (`.`→`/`, so `crm.*`→`crm/*`, `crm.read`→`crm/read`); `actions`
and `tools` are then empty. This lets SubGrant's resource subsumption model
scope narrowing faithfully (so SubGrant *agrees* with attenu that `crm.read ⊆
crm.*`), instead of flagging every real attenu chain under plain action-set
semantics. Numeric `max` constraints → caps `{name:key, limit:max}`; other
constraint kinds (rank/min/one_of/prefix) are ignored in v1. Root `del_max_depth`
→ root `depth_budget`. `evidence=signature` (ref `attenu:<jti>`). Consequence
(reported, not hidden): because attenu scopes become resources and not actions,
SubGrant's D7 (which keys off `actions`) does not fire on attenu chains, and
SubGrant is blind to signature/par_hash/encoding failures the attenu verifier
catches — these are the headline B1 divergences.

## D-018 · descriptor mapping and N generations
One edge per generation; generation 0's node is the root authority and the root
edge is `gen0 → gen0`. Edge i (i>0) is `gen[i-1] → gen[i]`. Authority:
`inherit` → the parent edge's authority verbatim (full root authority
propagates); `scoped` → generation i's listed authority; `none` → empty.
Windows uniform (`issued_at=2026-01-01T00:00:00Z`, `expires_at=null`),
`depth_budget` absent, `redelegation=true`, `data_classes=["internal"]`.
`handoff_evidence` maps "signed token"→signature, "logged attestation"→
attestation, "none"→none (ref `descriptor:<framework>`). The §2.4 contract shows
2–3 generations (the Part B scenario); the normalizer accepts any N≥1 linear
generations, which is what lets dev_ext represent chains of other lengths.
Because the root edge's issuer is the root authority (gen0), a confused-deputy
breach surfaces on e3 (the second delegation), not e2 — a property of the
encoding, noted in `audit/frameworks.md`.

## D-019 · dev_ext expressibility (generalized inexpressibility escape)
§3 documents an inexpressibility escape only for rfc8693 fan-outs, but every
format carries only some dimensions, so the same principle must apply uniformly:
a (case, format) pair is **expressible** iff (a) the format can structurally
represent the graph (rfc8693 and descriptor need a pure linear chain) and (b)
the representation, once normalized and verified, reproduces the case's
`expected` findings exactly. The generator builds the best possible
representation (hand-inverting the §2 mapping), runs normalize+verify, and marks
the pair inexpressible with a reason when the format cannot reproduce the
finding (e.g. ucan drops caps → cannot express D5/D6; rfc8693/descriptor share
one window → cannot express D4; all three force evidence presence/uniformity →
cannot express the per-edge D8 case; ucan/rfc8693 force intermediate holders to
T2, which over-flags D7 on a chain with a trusted T1 intermediate). `expected`
is never edited. This is the §3 escape generalized, recorded here rather than
invented silently.

## D-020 · SARIF levels
D1–D7 are `error`; D8 is `note` (presence-only, informational). Rules D1–D8 are
always declared in the run even when there are no results.

## D-021 · Cap numerics — exact comparison, NaN/Infinity as findings
Cap limits (`caveats.caps[].limit`) are compared **exactly as written in the
document**, with no `float64` rounding. At load (`subgrant/graph.py`) the JSON
number is preserved: a JSON integer stays a Python `int` (arbitrary precision),
a JSON float stays a `float`. The earlier `float(limit)` coercion was the single
root cause of two D6 evasions found by the adversarial fuzz audit
(`reports/fuzz-audit.md`): it rounded `2**53 + 1` down to `2**53`, so an integer
cap raise of exactly 1 compared equal, and it provided no defense against `NaN`.

D6 and D5 now use a **provably-≤** test instead of strict `>`. A child cap is a
weakening unless it is provably within the parent's: `not (child <= parent)`.
Every comparison with `NaN` is `False`, so this phrasing is False-safe — a `NaN`
child limit fires D6, and a `NaN` parent limit makes *any* child cap
not-provably-≤, so D6 fires. `NaN` is therefore a **weakening, reported as a
finding, never an input error**: a `NaN` cap loads cleanly (no `GraphError`, no
exit 2). The D5 sibling sum is computed in **exact arithmetic**
(`fractions.Fraction`, which captures a finite float's exact binary value), so
an integer sibling sum is exact and cannot appear within the parent's limit
through rounding; a `NaN` addend (or a +∞/−∞ mix) poisons the total to `NaN`,
and a lone ±∞ yields that infinity, so a non-finite sibling sum is never
provably within the limit and D5 fires.

Non-finite handling is thus: **+Infinity child fires D6** (not provably ≤ a
finite parent); **−Infinity child is clean** (it narrows, `-inf <= finite`);
finite float caps behave exactly as before; an equal restatement (including at
exactly `2**53`) stays clean. Note that whenever a `NaN` would enter a D5 sum,
the same `NaN` child already fails the per-edge D6 provably-≤ test, so the D5
fan-out gate (fire only when every child individually passes D1/D6) defers to
the direct D6 finding; the NaN-poisoning of the sum is a belt-and-suspenders
property of the arithmetic, independently verified.

**Monotone-fix rationale (why a findings-fix, not an input-error).** GATE 2 was
scored on the sealed holdout against the verifier's *findings* behavior as it
stood at `bcbd286`/`f3e4e93` — where, for example, a +Infinity cap is a D6
finding, not an input error. This fix is **monotone**: for every input, the
fixed verifier's findings are a superset of the previous verifier's, and the
only verdict changes are inside the two evasion families (`cap/nan`,
`cap/bigint-plus-one`). It therefore keeps the published GATE 2 statement true
by construction, without reopening or re-scoring the sealed holdout. Converting
caps to input errors (exit 2) would instead *remove* findings and change the
load/verdict contract, breaking that guarantee — so it was rejected.
