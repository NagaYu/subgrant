"""Load and validate ``dgraph/1`` delegation-graph documents.

Any structural problem with the document is an *input error* — a
:class:`GraphError` — which the CLI surfaces as exit code 2. Input errors are
never reported as findings; findings (D1-D8) are only produced for documents
that load cleanly.

Pinned input-error conditions (§2 of the Phase 1 spec):
  * not exactly one root edge (``parent_edge: null``)
  * a dangling ``parent_edge`` (points at a missing edge)
  * a duplicate edge id
  * a cycle in the parent relation
  * an illegal resource pattern
  * an out-of-vocabulary ``data_classes`` or ``purposes`` value
  * a malformed timestamp, cap, evidence, node, or missing required field
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .patterns import PatternError, validate_pattern

SCHEMA_ID = "dgraph/1"

NODE_KINDS = frozenset({"human", "agent", "service"})
TRUST_TIERS = frozenset({"T0", "T1", "T2", "T3"})
DATA_CLASSES = frozenset({"public", "internal", "confidential", "restricted"})
PURPOSES = frozenset(
    {"read", "write", "communicate", "execute", "transact", "administer", "delegate"}
)
EVIDENCE_KINDS = frozenset({"signature", "attestation", "none"})

_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class GraphError(ValueError):
    """Raised for any structural (schema) problem in a dgraph/1 document."""


def parse_timestamp(value: str, *, field: str) -> datetime:
    """Parse a pinned UTC ISO-8601 timestamp ``YYYY-MM-DDTHH:MM:SSZ``.

    Returns a timezone-aware :class:`datetime` in UTC. Raises
    :class:`GraphError` on any other shape.
    """
    if not isinstance(value, str):
        raise GraphError(f"{field}: timestamp must be a string, got {type(value).__name__}")
    try:
        dt = datetime.strptime(value, _TS_FORMAT)
    except ValueError:
        raise GraphError(
            f"{field}: timestamp must match YYYY-MM-DDTHH:MM:SSZ (UTC), got {value!r}"
        )
    return dt.replace(tzinfo=timezone.utc)


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise GraphError(msg)


def _check_str_list(value: Any, *, field: str) -> list[str]:
    _require(isinstance(value, list), f"{field}: must be an array")
    for item in value:
        _require(isinstance(item, str), f"{field}: entries must be strings")
    return value


def _check_enum_list(value: Any, vocab: frozenset[str], *, field: str) -> list[str]:
    items = _check_str_list(value, field=field)
    for item in items:
        _require(item in vocab, f"{field}: {item!r} not in {sorted(vocab)}")
    return items


class Edge:
    """A validated delegation edge. Attributes mirror the document fields.

    ``caps`` is normalized to a ``{name: limit}`` dict (duplicate cap names are
    an input error). Set-valued fields are stored as frozensets; ``resources``
    stays an ordered unique list because subset checks walk patterns.
    """

    __slots__ = (
        "id",
        "parent_edge",
        "issuer",
        "holder",
        "tools",
        "actions",
        "resources",
        "data_classes",
        "issued_at",
        "expires_at",
        "redelegation",
        "depth_budget",
        "caps",
        "purposes",
        "evidence_kind",
        "evidence_ref",
    )

    def __init__(self, raw: dict[str, Any], *, is_root_candidate: bool) -> None:
        _require(isinstance(raw, dict), "edge: must be an object")

        eid = raw.get("id")
        _require(isinstance(eid, str) and eid != "", "edge: 'id' must be a non-empty string")
        self.id = eid
        ctx = f"edge {eid}"

        _require("parent_edge" in raw, f"{ctx}: missing 'parent_edge'")
        parent = raw["parent_edge"]
        _require(
            parent is None or (isinstance(parent, str) and parent != ""),
            f"{ctx}: 'parent_edge' must be null or a non-empty string",
        )
        self.parent_edge = parent

        for fld in ("issuer", "holder"):
            val = raw.get(fld)
            _require(isinstance(val, str) and val != "", f"{ctx}: '{fld}' must be a non-empty string")
        self.issuer = raw["issuer"]
        self.holder = raw["holder"]

        authority = raw.get("authority")
        _require(isinstance(authority, dict), f"{ctx}: 'authority' must be an object")
        self.tools = frozenset(_check_str_list(authority.get("tools"), field=f"{ctx}.authority.tools"))
        self.actions = frozenset(
            _check_str_list(authority.get("actions"), field=f"{ctx}.authority.actions")
        )
        self.data_classes = frozenset(
            _check_enum_list(
                authority.get("data_classes"), DATA_CLASSES, field=f"{ctx}.authority.data_classes"
            )
        )
        resources = _check_str_list(authority.get("resources"), field=f"{ctx}.authority.resources")
        validated: list[str] = []
        seen: set[str] = set()
        for pat in resources:
            try:
                validate_pattern(pat)
            except PatternError as exc:
                raise GraphError(f"{ctx}.authority.resources: {exc}")
            if pat not in seen:  # set semantics, duplicates ignored
                seen.add(pat)
                validated.append(pat)
        self.resources = validated

        caveats = raw.get("caveats")
        _require(isinstance(caveats, dict), f"{ctx}: 'caveats' must be an object")

        self.issued_at = parse_timestamp(caveats.get("issued_at"), field=f"{ctx}.caveats.issued_at")

        exp = caveats.get("expires_at", None)
        if exp is None:
            self.expires_at = None
        else:
            self.expires_at = parse_timestamp(exp, field=f"{ctx}.caveats.expires_at")

        redel = caveats.get("redelegation")
        _require(isinstance(redel, bool), f"{ctx}.caveats.redelegation: must be a boolean")
        self.redelegation = redel

        # depth_budget appears only on the root edge, may be absent.
        if "depth_budget" in caveats:
            _require(
                is_root_candidate,
                f"{ctx}.caveats.depth_budget: only the root edge may carry 'depth_budget'",
            )
            db = caveats["depth_budget"]
            _require(
                isinstance(db, int) and not isinstance(db, bool) and db >= 1,
                f"{ctx}.caveats.depth_budget: must be a positive integer",
            )
            self.depth_budget = db
        else:
            self.depth_budget = None

        caps_raw = caveats.get("caps", [])
        _require(isinstance(caps_raw, list), f"{ctx}.caveats.caps: must be an array")
        caps: dict[str, float] = {}
        for cap in caps_raw:
            _require(isinstance(cap, dict), f"{ctx}.caveats.caps: each cap must be an object")
            name = cap.get("name")
            limit = cap.get("limit")
            _require(isinstance(name, str) and name != "", f"{ctx}.caveats.caps: 'name' must be a non-empty string")
            _require(
                isinstance(limit, (int, float)) and not isinstance(limit, bool),
                f"{ctx}.caveats.caps[{name}]: 'limit' must be a number",
            )
            _require(name not in caps, f"{ctx}.caveats.caps: duplicate cap name {name!r}")
            caps[name] = float(limit)
        self.caps = caps

        self.purposes = frozenset(
            _check_enum_list(caveats.get("purposes"), PURPOSES, field=f"{ctx}.caveats.purposes")
        )

        evidence = raw.get("evidence")
        _require(isinstance(evidence, dict), f"{ctx}: 'evidence' must be an object")
        ekind = evidence.get("kind")
        _require(ekind in EVIDENCE_KINDS, f"{ctx}.evidence.kind: must be one of {sorted(EVIDENCE_KINDS)}")
        self.evidence_kind = ekind
        eref = evidence.get("ref", None)
        _require(
            eref is None or isinstance(eref, str),
            f"{ctx}.evidence.ref: must be a string or null",
        )
        if ekind == "none":
            # ref may be null when kind is none.
            self.evidence_ref = eref
        else:
            _require(
                isinstance(eref, str) and eref != "",
                f"{ctx}.evidence.ref: must be a non-empty string when kind is {ekind!r}",
            )
            self.evidence_ref = eref


class Graph:
    """A validated dgraph/1 document.

    Exposes ``edges`` (dict id->Edge), ``nodes`` (dict id->node dict),
    ``root`` (the single root Edge), ``children`` (dict parent-id->list[Edge]),
    and ``depth`` (dict edge-id->int, root = 1).
    """

    __slots__ = ("nodes", "edges", "root", "children", "depth", "order")

    def __init__(self, nodes, edges, root, children, depth, order) -> None:
        self.nodes = nodes
        self.edges = edges
        self.root = root
        self.children = children
        self.depth = depth
        self.order = order  # edge ids in document order, for stable reporting

    def parent_of(self, edge: Edge) -> Edge | None:
        if edge.parent_edge is None:
            return None
        return self.edges[edge.parent_edge]

    def trust_tier(self, node_id: str) -> str:
        return self.nodes[node_id]["trust_tier"]


def load_graph(doc: Any) -> Graph:
    """Validate a parsed JSON ``doc`` and return a :class:`Graph`.

    Raises :class:`GraphError` on any structural problem.
    """
    _require(isinstance(doc, dict), "document: top level must be a JSON object")
    _require(doc.get("schema") == SCHEMA_ID, f"document: 'schema' must be {SCHEMA_ID!r}")

    raw_nodes = doc.get("nodes")
    _require(isinstance(raw_nodes, list) and raw_nodes, "document: 'nodes' must be a non-empty array")
    nodes: dict[str, dict[str, Any]] = {}
    for n in raw_nodes:
        _require(isinstance(n, dict), "node: must be an object")
        nid = n.get("id")
        _require(isinstance(nid, str) and nid != "", "node: 'id' must be a non-empty string")
        _require(nid not in nodes, f"node: duplicate id {nid!r}")
        kind = n.get("kind")
        _require(kind in NODE_KINDS, f"node {nid}: 'kind' must be one of {sorted(NODE_KINDS)}")
        tier = n.get("trust_tier")
        _require(tier in TRUST_TIERS, f"node {nid}: 'trust_tier' must be one of {sorted(TRUST_TIERS)}")
        nodes[nid] = {"id": nid, "kind": kind, "trust_tier": tier}

    raw_edges = doc.get("edges")
    _require(isinstance(raw_edges, list) and raw_edges, "document: 'edges' must be a non-empty array")

    # First pass: find root candidates so depth_budget placement can be checked.
    root_ids = [e.get("id") for e in raw_edges if isinstance(e, dict) and e.get("parent_edge", "x") is None]

    edges: dict[str, Edge] = {}
    order: list[str] = []
    for raw in raw_edges:
        is_root_candidate = isinstance(raw, dict) and raw.get("parent_edge", "x") is None
        edge = Edge(raw, is_root_candidate=is_root_candidate)
        _require(edge.id not in edges, f"edge: duplicate id {edge.id!r}")
        _require(edge.issuer in nodes, f"edge {edge.id}: issuer {edge.issuer!r} is not a declared node")
        _require(edge.holder in nodes, f"edge {edge.id}: holder {edge.holder!r} is not a declared node")
        edges[edge.id] = edge
        order.append(edge.id)

    roots = [e for e in edges.values() if e.parent_edge is None]
    _require(len(roots) == 1, f"document: exactly one root edge required, found {len(roots)}")
    root = roots[0]

    # Dangling parent references.
    for edge in edges.values():
        if edge.parent_edge is not None:
            _require(
                edge.parent_edge in edges,
                f"edge {edge.id}: 'parent_edge' {edge.parent_edge!r} points at a missing edge",
            )

    # Cycle detection + depth computation by walking each edge to the root.
    depth: dict[str, int] = {}
    for edge in edges.values():
        path: list[str] = []
        seen: set[str] = set()
        cur: Edge | None = edge
        while cur is not None:
            if cur.id in seen:
                raise GraphError(f"document: cycle detected in parent_edge chain at {cur.id!r}")
            seen.add(cur.id)
            path.append(cur.id)
            cur = edges[cur.parent_edge] if cur.parent_edge is not None else None
        # root is depth 1; path length from this edge up to and including root.
        depth[edge.id] = len(path)

    children: dict[str, list[Edge]] = {eid: [] for eid in edges}
    for eid in order:
        edge = edges[eid]
        if edge.parent_edge is not None:
            children[edge.parent_edge].append(edge)

    return Graph(nodes=nodes, edges=edges, root=root, children=children, depth=depth, order=order)
