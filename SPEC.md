# SPEC — SubGrant `dgraph/1` and the D1–D8 checks (Phase 1)

This document is self-contained: a Phase 2 session can work from it without the
Phase 1 build prompt. It pins the document shape, the resource grammar, window
containment, the depth model, the policy pack, and each check class. Pins that
override `subgrant-design.md` are cross-referenced to `DECISIONS.md`.

SubGrant is a **verifier and bench**, never an enforcer and never a token
format. It checks, offline, that authority only ever narrows (or restates) as
one agent delegates to another.

---

## 1. The `dgraph/1` document

A JSON object:

```json
{
  "schema": "dgraph/1",
  "nodes": [{"id": "n0", "kind": "human|agent|service", "trust_tier": "T0|T1|T2|T3"}],
  "edges": [{
    "id": "e1",
    "parent_edge": null,
    "issuer": "n0", "holder": "n1",
    "authority": {
      "tools": ["tool.search"],
      "actions": ["data.read"],
      "resources": ["db/project-x/*"],
      "data_classes": ["internal"]
    },
    "caveats": {
      "issued_at": "2026-01-01T00:00:00Z",
      "expires_at": "2026-02-01T00:00:00Z",
      "redelegation": true,
      "depth_budget": 6,
      "caps": [{"name": "spend_usd", "limit": 100}],
      "purposes": ["read"]
    },
    "evidence": {"kind": "signature|attestation|none", "ref": "sig:abc"}
  }]
}
```

### Nodes
- `id`: non-empty string, unique.
- `kind`: one of `human | agent | service`.
- `trust_tier`: one of `T0 | T1 | T2 | T3`.

### Edges
- `id`: non-empty string, unique across edges.
- `parent_edge`: `null` (root) or the id of another edge.
- `issuer`, `holder`: node ids (must be declared in `nodes`).
- `authority`:
  - `tools`, `actions`: arrays of strings, **set** semantics (duplicates ignored).
  - `resources`: array of resource patterns (closed grammar, §2), set semantics.
  - `data_classes`: array drawn only from `public | internal | confidential |
    restricted`, set semantics.
- `caveats`:
  - `issued_at`: UTC ISO-8601 `YYYY-MM-DDTHH:MM:SSZ` (required) — see DECISIONS D-003/D-004.
  - `expires_at`: same grammar, or `null` for unbounded (required key).
  - `redelegation`: boolean.
  - `depth_budget`: positive integer, **root edge only**, may be absent (DECISIONS D-002).
  - `caps`: array of `{name: string, limit: number}`; cap names unique per edge.
  - `purposes`: array drawn only from `read | write | communicate | execute |
    transact | administer | delegate`, set semantics (DECISIONS D-001).
- `evidence`:
  - `kind`: one of `signature | attestation | none`.
  - `ref`: string, or `null` only when `kind == "none"` (DECISIONS D-009).

### Structural invariants (input errors, CLI exit 2 — DECISIONS D-012)
Exactly one root edge; no dangling `parent_edge`; no duplicate edge id; no cycle
in the parent relation; all patterns legal; all enums in vocabulary; all
timestamps well-formed; `issuer`/`holder` are declared nodes. Any violation is a
schema error, never a finding.

---

## 2. Resource patterns (closed grammar)

A pattern is exactly one of:
- `"*"` — matches everything;
- a literal containing no `*` — matches only itself;
- a literal prefix ending in `/*` (and no other `*`) — a prefix wildcard.

Anything else is an input error. No regex, no natural-language matching (the
ReleaseSeal V4 ceiling: semantics stay mechanical).

**Subsumption** `p ⊆ q` holds iff: `q == "*"`, or `p == q`, or `q` ends in `/*`
and (`p == q[:-2]` or `p` starts with `q[:-1]`). So `db/*` subsumes the bare
prefix `db` and anything under `db/`, but not `dbx`.

**Set subset** `A ⊆ B` iff every pattern in `A` is subsumed by **some single**
pattern in `B`. Joint coverage by several patterns in `B` is out of scope — a
conservative choice (DECISIONS D-005).

---

## 3. Window containment

Child window `⊆` parent window iff:
`child.issued_at >= parent.issued_at` **and** (`parent.expires_at is null` **or**
(`child.expires_at` is non-null **and** `child.expires_at <= parent.expires_at`)).

So an unbounded parent contains any child; a bounded parent never contains an
unbounded child.

---

## 4. Depth

An edge's depth = number of edges on the path from the root (root = 1).
Effective budget = `pack.max_depth`, tightened by the root edge's `depth_budget`
when present (`min`). See DECISIONS D-002.

---

## 5. Policy pack

`packs/delegation-policy-v1.json`:

```json
{"pack": "delegation-policy", "version": "1.0.0", "max_depth": 6,
 "protected_actions": ["funds.transfer", "data.delete", "iam.grant",
   "iam.modify", "code.push_protected", "pii.export", "secret.read",
   "infra.destroy"]}
```

---

## 6. Check classes

A finding names a class and the edge id the definition points at. For an edge
`e` with parent `p`; root edges skip the parent-relative checks (D1, D3, D4, D6).
Applicability is pinned in DECISIONS D-010.

- **D1 Amplification** — any of: `e.tools ⊄ p.tools`, `e.actions ⊄ p.actions`,
  `e.data_classes ⊄ p.data_classes`, or `e.resources` not a subset of
  `p.resources` under §2. Reported on `e`.
- **D2 Depth breach** — `depth(e)` exceeds the effective budget (§4). Reported on `e`.
- **D3 Re-delegation breach** — `p.redelegation == false` and `e` exists.
  Reported on `e` (DECISIONS D-006).
- **D4 Lifetime breach** — `e`'s window is not contained in `p`'s (§3). On `e`.
- **D5 Fan-out recombination** — on a parent `p` with children `c1..ck` (k ≥ 2),
  when every child individually passes D1 and D6, D5 fires if for some cap name
  the child-sum exceeds `p`'s limit. Omitted-cap counts as the parent's full
  limit; cap names `p` lacks are ignored. Reported on `p` (DECISIONS D-007).
- **D6 Caveat drop / weakening** — any of: a cap in `p` absent in `e`; a
  same-name cap in `e` with a higher limit than in `p`; `e.purposes ⊄
  p.purposes`. Reported on `e`.
- **D7 Confused-deputy reachability** — `e` grants a protected action (pack list)
  to a holder with `trust_tier` `T2`/`T3`, and `e.issuer` is not the root
  authority node. Reported on `e` (v1 heuristic, DECISIONS D-008).
- **D8 Unbound delegation** — `e.evidence.kind == "none"`. Presence check only;
  signatures are not verified in v1 (DECISIONS D-009). Reported on `e`.

Finding order is deterministic: sorted by `(edge document index, class)`
(DECISIONS D-011).

---

## 7. Commands and outputs

- `python -m subgrant verify <graph.json>` — findings to stdout; exit 0 (clean),
  1 (findings), 2 (input error). `--json` emits findings as JSON; `--pack` loads
  an alternate policy pack.
- `python -m subgrant report <graph.json>` — a hash-chained evidence pack
  (`--format json|md`). *Evidence, not certification.*

Evidence-pack hash chain: DECISIONS D-013.

---

## 8. Known limitations (v1)
- No signature verification (D8 is presence-only).
- Single-pattern resource subsumption is conservative (no joint coverage).
- D7 is the pinned v1 direct-grant rule, not full reachability analysis.

## 9. Phase 2 (built — see DECISIONS D-014..D-020, reports/phase2.md)
Normalizers target this `dgraph/1` document: `ucan`, `rfc8693`, `attenu`
(Delegation-Token chain; scopes → resources, D-017), `descriptor` (framework
handoff). CLI: `python -m subgrant normalize <format> <file>` and `verify
--sarif` (SARIF 2.1.0: D1–D7 `error`, D8 `note`). Baselines (`subgrant/
baselines.py`): B0 naive per-edge checker (recall 0 on D5/D7 by construction),
B2 minimal UCAN-1.0 attenuation checker. dev_ext (`bench/dev_ext/`) carries
multi-format representations of known dev cases and round-trips verdicts;
expressibility is bounded by what each format carries (D-019). The Part B audit
(`audit/`) pins 8 frameworks' delegation defaults. Core semantics (§1–§8) are
frozen and unchanged in Phase 2.

## 10. Not built yet (Phase 3)
The sealed holdout is authored independently with pre-registered predictions
(GATE 2), before any publication. Publication prep (export repo, HF dataset with
dev only, demo, entrance drafts) is Phase 3, on the owner's confirmation.
