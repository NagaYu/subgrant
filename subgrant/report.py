"""Evidence pack: a hash-chained JSON record plus a human-readable Markdown.

Wording discipline (portfolio standard): this is *evidence, not certification*.
The pack records what SubGrant checked and found; it asserts nothing about
cryptographic validity (see D8, presence-only in v1).

Hash chain
----------
Entries form a tamper-evident chain. Each entry's ``hash`` is::

    sha256( prev_hash || canonical_json({seq, type, payload}) )

encoded as hex, where ``prev_hash`` is the previous entry's ``hash`` (the
genesis ``prev`` is 64 zeros) and ``canonical_json`` uses sorted keys and
compact separators. Changing any payload, reordering, inserting, or dropping an
entry breaks the chain at that point, which :func:`verify_pack` detects.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from . import __version__
from .checks import Finding

GENESIS_PREV = "0" * 64


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _entry_hash(prev: str, seq: int, etype: str, payload: Any) -> str:
    h = hashlib.sha256()
    h.update(prev.encode("ascii"))
    h.update(_canonical({"seq": seq, "type": etype, "payload": payload}))
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_pack(
    graph_bytes: bytes,
    findings: list[Finding],
    pack: dict[str, Any],
    *,
    source: str | None = None,
) -> dict[str, Any]:
    """Build a hash-chained evidence pack from a verification run.

    ``graph_bytes`` is the exact input document bytes (recorded by digest).
    """
    header_payload = {
        "subgrant_version": __version__,
        "source": source,
        "graph_sha256": _sha256_bytes(graph_bytes),
        "policy_pack": {"pack": pack.get("pack"), "version": pack.get("version")},
        "finding_count": len(findings),
    }

    entries: list[dict[str, Any]] = []
    prev = GENESIS_PREV
    seq = 0
    h = _entry_hash(prev, seq, "header", header_payload)
    entries.append({"seq": seq, "type": "header", "payload": header_payload, "prev": prev, "hash": h})
    prev = h

    for f in findings:
        seq += 1
        payload = f.as_dict()
        h = _entry_hash(prev, seq, "finding", payload)
        entries.append({"seq": seq, "type": "finding", "payload": payload, "prev": prev, "hash": h})
        prev = h

    return {"schema": "subgrant-evidence/1", "entries": entries, "chain_tip": prev}


def verify_pack(pack_obj: dict[str, Any]) -> bool:
    """Return True iff the pack's hash chain is internally consistent."""
    entries = pack_obj.get("entries")
    if not isinstance(entries, list) or not entries:
        return False
    prev = GENESIS_PREV
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            return False
        if entry.get("seq") != i:
            return False
        if entry.get("prev") != prev:
            return False
        recomputed = _entry_hash(prev, i, entry.get("type"), entry.get("payload"))
        if recomputed != entry.get("hash"):
            return False
        prev = entry["hash"]
    return prev == pack_obj.get("chain_tip")


def to_markdown(pack_obj: dict[str, Any]) -> str:
    """Render the evidence pack as human-readable Markdown."""
    entries = pack_obj.get("entries", [])
    header = entries[0]["payload"] if entries else {}
    findings = [e["payload"] for e in entries if e.get("type") == "finding"]

    lines: list[str] = []
    lines.append("# SubGrant evidence pack")
    lines.append("")
    lines.append("_Evidence, not certification._ SubGrant records what it checked and found;")
    lines.append("it does not verify cryptographic signatures (D8 is presence-only in v1).")
    lines.append("")
    lines.append("## Run")
    lines.append("")
    lines.append(f"- SubGrant version: `{header.get('subgrant_version', '?')}`")
    lines.append(f"- Source: `{header.get('source') or '(stdin)'}`")
    lines.append(f"- Graph SHA-256: `{header.get('graph_sha256', '?')}`")
    pp = header.get("policy_pack", {})
    lines.append(f"- Policy pack: `{pp.get('pack')}` v`{pp.get('version')}`")
    lines.append(f"- Chain tip: `{pack_obj.get('chain_tip', '?')}`")
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    if not findings:
        lines.append("No findings. Every delegation edge narrows or restates authority.")
    else:
        lines.append(f"{len(findings)} finding(s):")
        lines.append("")
        lines.append("| Class | Edge |")
        lines.append("| --- | --- |")
        for f in findings:
            lines.append(f"| {f['class']} | `{f['edge']}` |")
    lines.append("")
    return "\n".join(lines)
