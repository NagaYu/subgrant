# Part B — framework delegation-default audit

What each framework does **by default** when an orchestrator delegates a
research subtask to a sub-agent, which delegates a formatting subtask to a third
agent — not what a careful developer could configure. Each row's descriptor
(`audit/descriptors/<framework>.json`) is written in the §2.4 descriptor format
and normalized through the core verifier; the "SubGrant findings" column is the
verifier's output on that descriptor.

Standard scenario (identical for all 8): the orchestrator holds tools
`[search, read_db, write_db, send_email, pay]` (`pay` → protected action
`funds.transfer`), actions `[data.read, data.write, communicate.send,
funds.transfer]`, resources `["db/project-x/*"]`, caps `[{spend_usd: 100}]`,
purposes `[read, write, communicate, transact]`.

All versions and behaviours were read from public documentation/source as
surfaced on **2026-11-11**; some versions could not be confirmed to the patch
level from the sources and are marked accordingly. Re-verify at repo creation
(portfolio standard). Where documentation is silent, the cell says
"not documented" rather than a guess.

## Audit table

| Framework | Version (as of 2026-11-11) | Scoped delegation exists? | Default posture | Checks child ⊆ parent? | Handoff evidence | SubGrant findings |
| --- | --- | --- | --- | --- | --- | --- |
| LangGraph / deepagents | deepagents 0.7.6 (langchain 1.3.15) | Yes (`tools`/`permissions` per sub-agent) | **inherit-all** (sub-agent inherits parent tools; an explicit `tools` list *replaces*, not intersects) | No | none | D7 e3; D8 e1,e2,e3 |
| OpenAI Agents SDK | openai-agents 0.13.5 | Yes (each `Agent` has its own `tools`; `handoffs`) | scoped (handoff target carries its own tools; no inheritance) | No | none | D8 e1,e2,e3 |
| CrewAI | crewai 1.15.19 | Yes (`allow_delegation`, default **False**) | scoped; delegation **off by default** | No | none | D8 e1,e2,e3 |
| AutoGen (AgentChat) | autogen-agentchat 0.7.5 | Yes (nested teams / `SocietyOfMindAgent`) | scoped (inner agents have their own tools) | No | none | D8 e1,e2,e3 |
| Google ADK | google-adk 1.28.0 | Yes (`sub_agents` transfer; `AgentTool`) | scoped (sub-agent/AgentTool has its own tools) | No | none | D8 e1,e2,e3 |
| Claude Agent SDK | Claude Code v2.1.198 | Yes (per-subagent `tools` field) | **inherit** (subagent uses the parent tool set unless `tools` restricts) | No | none | D7 e3; D8 e1,e2,e3 |
| Pydantic AI | pydantic-ai harness (experimental, 2026-07) | Yes (`SubAgent`; `inherit_tools`, default **False**) | scoped (sub-agent does **not** inherit parent tools by default) | No | none | D8 e1,e2,e3 |
| A2A (reference) | A2A 1.0.1 / a2a-sdk (Python) | Yes (remote agent has its own AgentCard skills) | scoped (remote agent runs with its own authority; no parent relation) | No | none (card is signed for identity, not the delegation) | D8 e1,e2,e3 |

Headline: **no framework checks child ⊆ parent by default, and none records a
delegation-authority binding on the handoff** (so SubGrant's D8 fires on every
edge of every scenario). The two inherit-all frameworks — **LangGraph/deepagents**
and the **Claude Agent SDK** — additionally propagate the protected action
`funds.transfer` down to the third agent, which SubGrant flags as a
confused-deputy reachability breach (**D7**). The six scoped frameworks avoid
amplification *when the developer scopes the sub-agent*, but nothing in them
enforces that scoping.

## Per-framework notes

**LangGraph / deepagents.** Scoped delegation exists: a sub-agent spec may set
`tools` and (deepagents ≥ 0.5.2) `permissions`. But the **default** is
inherit-all — a sub-agent inherits the main agent's tools, and an explicit
`tools` list *replaces* the inherited set entirely rather than intersecting with
it (so a child can even hold tools the parent lacks). Nothing checks child ⊆
parent. No handoff token is recorded. Descriptor uses `child_credentials:
inherit`; SubGrant reports D7 (e3: `funds.transfer` reaches the third agent via
a non-root issuer) and D8 on every edge.
Maintainer-confirmed intended behaviour (ccurme, LangChain, 2026-11-11; issue #7679 closed as not planned — "This is intended behavior.")
Sources: docs.langchain.com/oss/python/deepagents/subagents, .../permissions.md.

**OpenAI Agents SDK.** Delegation is via `handoffs` (control transfer) or
agents-as-tools. Each `Agent` defines its own `tools`; a handoff target is a
separate agent with its own tools — no inheritance and no subset enforcement are
documented. Handoff is a tool call, not an authority token. `child_credentials:
scoped`; SubGrant reports only D8. Sources:
openai.github.io/openai-agents-python/handoffs, /tools.

**CrewAI.** `allow_delegation` defaults to **False** in current v1.15.x; agents
each carry their own `tools` (default empty). When delegation is enabled the
agent gains delegate-work / ask-question collaboration tools, but nothing checks
that the delegate's authority is a subset of the delegator's. Modeled scoped,
with the default-off caveat. SubGrant reports only D8. Sources:
docs.crewai.com/en/concepts/agents, /collaboration.

**AutoGen (AgentChat).** Multi-agent composition is via teams and nested teams
(`SocietyOfMindAgent`); inner agents hold their own tools and there is no
documented parent→child tool inheritance or subset check. No handoff authority
token. Modeled scoped; SubGrant reports only D8. Sources:
microsoft.github.io/autogen/0.7.x AgentChat tutorial.

**Google ADK.** Two delegation shapes: `sub_agents` (control transfer, shared
session) and `AgentTool` (encapsulated, separate session). In both, the
sub-agent/tool carries its own tools; no child ⊆ parent check is documented. No
handoff authority token. Modeled scoped; SubGrant reports only D8. Sources:
adk.dev tools/agent-managed, cloud.google.com blog "sub-agents vs agents-as-tools".

**Claude Agent SDK.** Subagents are invoked through the `Agent` tool and can be
restricted via a `tools` field; when that field is omitted the subagent uses the
parent's allowed tool set (inherit by default). No subset check between a
subagent and its parent is enforced by the framework. No delegation token.
Modeled `child_credentials: inherit`; SubGrant reports D7 (e3) and D8 on every
edge. Sources: docs.claude.com/en/api/agent-sdk/subagents, permissions.

**Pydantic AI.** The experimental harness exposes `SubAgent`s; `inherit_tools`
defaults to **False**, so a sub-agent does *not* inherit the parent's tools by
default (it carries its own, plus the parent's only when `inherit_tools=True`).
No child ⊆ parent enforcement. No handoff authority token. Modeled scoped;
SubGrant reports only D8. Sources: ai.pydantic.dev/multi-agent-applications,
pydantic.dev/docs/ai/harness/subagents.

**A2A (reference).** A2A delegates tasks to remote agents, each advertising its
own authority via a signed AgentCard (`AgentCardSignature`, a JWS over the
canonicalized card). The card signature establishes *agent identity*, not a
*delegation authority binding*: the task send (`SendMessage`) carries no proof
that the remote agent's authority is a subset of the delegator's, and there is
no parent→child narrowing relationship by design. Modeled scoped with
`handoff_evidence: none`; SubGrant reports only D8. Sources: a2a-protocol.org,
github.com/a2aproject/A2A.

## Method and honesty notes

- Pinned snapshots only; no installs, no live runs (zero-maintenance). Each
  factual claim cites the documentation or source page above.
- "SubGrant findings" are produced by normalizing each descriptor through §2.4
  and running the core verifier — they describe the *scenario as modeled in the
  descriptor*, which encodes the documented default, not a judgement of the
  framework's overall security.
- Descriptor structural note: in the §2.4 mapping the root edge is the root
  authority holding its own authority (issuer = holder = generation 0), so the
  first delegation edge (e2) is issued *by* the root authority and never fires
  D7; a confused-deputy reachability breach therefore surfaces on e3 (the
  second delegation) for the inherit-all frameworks. This is a property of the
  descriptor encoding, not a claim that e2 is safe.
- Several patch-level versions could not be confirmed from the public pages
  surfaced (Claude Agent SDK, Pydantic AI, exact A2A patch); these are marked in
  the table and must be re-pinned at repo creation.
