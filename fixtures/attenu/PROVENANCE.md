# Vendored attenu-guard material — provenance

Source project: **attenu-io/attenu-guard** (Apache-2.0), an in-process
permission enforcer for AI-agent delegation chains. Repository description:
"Permissions that narrow when one AI agent delegates: a sub-agent never holds
more than its parent. In-process, with a hash-chained audit log you verify
offline. Python and TypeScript, adapters for 19 frameworks and A2A."

- Repository: https://github.com/attenu-io/attenu-guard
- Branch fetched: `main`
- Access date: 2026-11-11
- License of source: Apache-2.0 (the vectors are test material from that repo).

These files are the interop **token test vectors** from `tests/vectors/` in that
repository. Each file is a JSON object with `description`, `signer`
(`alg`/`kid`/`secret_hex` — an HS256 test-only key), `now`, a root-first
`tokens` array of compact JWS Delegation Tokens, and either `expect: "accept"`
or `expect_reject_reason: "<reason>"`.

## Vendored files (sha256 of the vendored copy)

| file | upstream path | attenu verdict | sha256 (vendored) |
| --- | --- | --- | --- |
| valid_chain.json | tests/vectors/valid_chain.json | accept | `96b9e3bbfc3ce73e816857d585f83b31abaaccfbaea568fda9605f445f75c436` |
| reject_widened_scope.json | tests/vectors/reject_widened_scope.json | not_narrower | `8c317254b747a7730936de74695f8c84571d0d6a5ea75a1ae1a3b540c62e8e51` |
| reject_depth_exceeded.json | tests/vectors/reject_depth_exceeded.json | depth_invalid | `9f56a17ff61e6660fa677a92c14542d36c686d89b6bfb77a3a381853ef57a9a5` |
| reject_nonmonotonic_exp.json | tests/vectors/reject_nonmonotonic_exp.json | expired | `29e3ef2b48f3d2548176fb63630d7ff8331b5965342091afa4c11aca893e26cb` |
| reject_bad_signature.json | tests/vectors/reject_bad_signature.json | signature_invalid | `b501459c5f61b35b4ac27bd4fe80523529395efe255a919371e81c5aebc85628` |

## Notes and honesty caveats

- The content was obtained by fetching the raw GitHub files through a tool that
  passes page content through a summarizing model. The token payloads
  (base64url) decode cleanly and contain the documented claims, so the vendored
  copies are faithful for SubGrant's purposes (SubGrant reads only the decoded
  **payloads** and does not verify signatures). The HS256 signatures may not be
  byte-identical to upstream; this does not affect SubGrant, which is
  presence-only (D8). The sha256 values above are of the vendored copies in this
  repo, which is what Phase 2 §0 requires.
- The source also ships an evidence/audit **bundle** format (`entries`,
  `anchor`, `envelopes`; schema `schema/agent-audit.schema.json`) and an IETF
  draft `docs/draft-asor-wimse-agent-delegation-chain-01.md`. SubGrant's `attenu`
  normalizer targets the **Delegation Token chain** (the wire format), not the
  audit bundle. See DECISIONS D-017 for the mapping table.
- Format summary used for the normalizer (from the draft + these vectors): each
  DT payload carries `iss, sub, iat, exp, jti, del_depth, del_max_depth?(root),
  par_hash?(non-root), authorization_details:[{type:"agent_delegation",
  scopes:[...], constraints:[{key, max|rank|...}]}]`. Scope grammar is dotted
  with a trailing `.*` wildcard (`crm.*`, `crm.read`, `mail.send`).
