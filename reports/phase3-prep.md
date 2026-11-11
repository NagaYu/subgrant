# SubGrant — Phase 3 prep (public export)

Date: 2026-11-11 · Local only · Python 3.11+ (developed on 3.13), stdlib
runtime, `pytest` for tests.

This is the clean public evaluation export of SubGrant, prepared locally in a
sibling folder for the owner's final confirmation. The development repository is
the source of truth; its HEAD at export time was
`f3e4e9375138590ce835c386f79f21041747965f` (the GATE 2 commit), verified before
any work began. **Nothing in this export is published; no remote is configured.**

## 1. Export inventory

Copied **byte-identically** from the development repository (verified with
`diff -r` / `cmp`):

```
subgrant/            core verifier + normalizers/ (14 modules)
packs/               delegation-policy-v1.json
tests/               full pytest suite (12 test files + helpers/conftest/__init__)
SPEC.md              DECISIONS.md (then appended — §4 below)
bench/__init__.py  bench/generate_dev.py  bench/score.py
bench/generate_dev_ext.py  bench/score_ext.py  bench/score_baselines.py
bench/dev/           cases.jsonl + manifest.json + score.json + score_baselines.json
bench/dev_ext/       ucan/ (13) + rfc8693/ (8) + descriptor/ (11) + manifest.json + score_ext.json
fixtures/attenu/     5 interop vectors + PROVENANCE.md
audit/frameworks.md  audit/descriptors/ (8 files)
reports/phase1.md    reports/phase2.md    reports/gate2.md
```

New or appended files (the only ones not byte-identical to the dev repo):
`README.md`, `LICENSE`, `.gitignore`, `reports/phase3-prep.md` (this file), the
appended Phase 3 entries in `DECISIONS.md`, and the uncommitted `hf-staging/`
tree (§5).

**Committed file count: 96.** (`hf-staging/`, 36 files, is git-ignored and not
committed.)

The regenerated score files `bench/dev/score.json` and
`bench/dev/score_baselines.json` were refreshed by the verification runs in §3
and are committed as regenerated.

## 2. Exclusions confirmed

- **Sealed holdout — fully excluded.** `bench/holdout/` does not exist in the
  export (cases, generator, `PREDICTIONS.md`, `AUTHORING.md`, manifest, score —
  none copied, in whole or in part, under any name). `bench/score_holdout.py` is
  excluded (its comparison logic is identical to the public `bench/score.py`).
  The public materials state only the aggregate holdout facts (a sealed 120-case
  holdout exists, is not published, GATE 2 passed on it); `reports/gate2.md`
  carries those aggregate facts and the seal-verification record, including the
  holdout case-file **sha256 digest** (a one-way integrity anchor that reveals
  nothing about the cases).
- **Phase prompt files and the design paper — excluded.**
  `claude-code-prompt-*.md` and `subgrant-design.md` are not present.
- **Also excluded:** the JSON Schema directory `schema/` (documentary only —
  no code reads it; the real validation is in `subgrant/graph.py`), `STATUS.md`
  (dev-repo status ledger), `.pytest_cache/`, `__pycache__/`, and the dev repo's
  `.git`.
- **`pyproject.toml`** was listed in the Phase 3 inventory but **does not exist
  in the development repository** (not tracked, not present). It could not be
  copied and is not fabricated. Runtime is the Python standard library only, so
  no packaging file is required to run the verifier, the benches, or the tests;
  this is recorded here for transparency.

## 3. Verification (run in the export folder)

| Step | Command | Result |
| --- | --- | --- |
| 1 | `python -m pytest` | **128 passed**, 0 failed |
| 2 | `python -m bench.score` | **GATE 1 PASS** — recall D1–D7 = 1.000 each, clean FP 0/68, D8 4/4, extras 0 (identical to Phase 1/2) |
| 3 | `python -m bench.score_ext` | ucan 13/13, rfc8693 8/8, descriptor 11/11 — all expressible round-trips pass |
| 4 | `python -m bench.score_baselines` | identical to `reports/phase2.md` §4 (see below) |
| 5 | Part B spot check | 8 descriptors normalized + verified; findings match `audit/frameworks.md` |

**Baselines (step 4), identical to `reports/phase2.md` §4:**
- SubGrant: D1–D7 all 1.000; D8 4/4; clean FP 0; extras 0.
- B0 (naive per-edge): D1 1.000, D2 **0.167**, D3 1.000, D4 1.000, D5 **0.000**,
  D6 1.000, D7 **0.000**; D8 0/4.
- B2 (UCAN-spec, over UCAN-expressible dev_ext): D1 1.000 (1), D4 **0.500** (2),
  D7 **0.000** (1); clean FP 0.
- B1 (attenu-guard, 5 vendored vectors): 4 **agree**, 1 **diverge**
  (`reject_bad_signature` — a corrupted signature a presence-only offline
  verifier cannot see).

**Part B spot check (step 5):** each framework descriptor produces **D8 on e1,
e2, e3**; **`langgraph-deepagents` and `claude-agent-sdk` additionally produce
D7 on e3**. This matches `audit/frameworks.md` exactly (the two inherit-by-default
frameworks propagate a protected action to the third agent).

## 4. DECISIONS.md append

Appended to the export copy of `DECISIONS.md` (the dev repo's copy is untouched):
**D-021** (export excludes the sealed holdout and `score_holdout.py`),
**D-022** (license = portfolio's unified All-Rights-Reserved text),
**D-023** (HF assets staged locally, uploaded only at publication).

## 5. Hugging Face staging (local only — nothing uploaded)

`hf-staging/` is listed in `.gitignore` and is **not committed**. Contents:

- `hf-staging/dataset/` — a future `NagaYu/subgrant-bench` dataset:
  `cases.jsonl` (the dev 120, byte-identical to `bench/dev/cases.jsonl`),
  `dev_ext/` (the 3-format representations + `manifest.json`), and a dataset-card
  `README.md` (what the bench is, composition, scoring rule, headline numbers,
  the sealed-holdout note, `license: other` / All Rights Reserved, portfolio
  contact).
- `hf-staging/space/` — a future Static Space demo: a single self-contained
  `index.html` (no server, no external scripts/styles/fonts/images — only the
  portfolio hyperlink) presenting the headline tables (dev, baselines, Part B),
  the D1–D8 class list, and three worked dev examples (D5 fan-out `case-0027`,
  D7 `case-0043`, clean `case-0053`) with graph JSON and the verifier's
  precomputed findings side by side. All numbers copied from the audited reports.

## 6. Secrecy and identity sweeps

Both sweeps were run with the system `grep` (not the gitignore-respecting
wrapper), so they cover the uncommitted `hf-staging/` tree as well.

- **Secrecy:** `bench/holdout/` absent; `bench/score_holdout.py` absent;
  `grep -r "holdout-"` (case-id prefix) → **0 hits**; no file named
  `PREDICTIONS.md` or `AUTHORING.md` exists. (The word "holdout" appears only in
  the permitted aggregate statements in `SPEC.md` and the reports.)
- **Identity:** **no email address** appears in any file (the user's address and
  all email-shaped tokens → 0 hits, excluding the git-author `noreply` address
  used only in commit metadata); the portfolio URL
  `https://nagayu-portfolio.nagayu.workers.dev/en` is the only contact, in
  `LICENSE`, `README.md`, and the two `hf-staging/` files. No owner API keys or
  secrets anywhere. The only "secret"-labeled values are the HS256 **test-only**
  keys inside the vendored attenu-guard interop vectors (`fixtures/attenu/`,
  public upstream test material documented in `PROVENANCE.md`); SubGrant reads
  only decoded payloads and verifies no signatures, so these are inert.

## 7. Status

Nothing is published; no remote exists; publication awaits the owner's final
confirmation of exact texts and targets.

## 8. Corrections (post-audit)

An independent audit of the initial export commit
(`791d80fd4e29631feed8a5dd3b1122f4ff22da8a`) found two small defects, fixed in a
second export commit (`SubGrant: export corrections — dgraph/1 JSON Schema,
case-0027 erratum`). Both are export-copy only; the dev repo is unchanged.

- **Fix 1 — added `schema/dgraph-1.json`.** The machine-readable `dgraph/1` JSON
  Schema was missing from the export inventory. It is now copied byte-identically
  from the dev repo (sha256
  `e746e96e16060faf019c00142fd0e0214dced0e0f9eeb35d28b2d07bd4249b6f`), and the
  `README.md` §8 Layout block lists it.
- **Fix 2 — case-0027 erratum in `reports/phase2.md` §4.** The B0-vs-SubGrant D5
  illustration described case-0027 as "`spend_usd=100` and two children at 60";
  the actual case is `api_calls=100` with four children at 30 (4 × 30 = 120 >
  100). Corrected to match the case in `bench/dev/cases.jsonl` (the `README.md`
  worked example and the Space demo were already correct).

`python -m pytest` still reports **128 passed** after the corrections.
