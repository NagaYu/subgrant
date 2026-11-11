"""Format normalizers: each maps one source document to a ``dgraph/1`` dict.

Common contract (Phase 2 §2):
  * Input is one JSON document; output is a ``dgraph/1`` document that must pass
    ``subgrant.graph.load_graph``. Malformed input raises :class:`NormalizeError`
    (a ``GraphError`` subclass), surfaced by the CLI as exit code 2 — never a
    partial graph.
  * Dimensions a format does not carry are set to a chain-wide constant so they
    can neither create nor mask findings. Defaults (unless a format overrides):
    ``purposes=["read"]``, ``caps=[]``, ``data_classes=["internal"]``,
    ``tools=[]`` (abilities go to ``actions``).
  * Node kinds/tiers: the root authority node is ``kind="human"``,
    ``trust_tier="T0"``; every other node is ``kind="agent"``,
    ``trust_tier="T2"`` unless the input explicitly carries a tier.
  * Edge ids are assigned ``e1..eN`` in root-first order so that a representation
    of a known graph round-trips to the same edge ids (dev_ext requirement).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable

from ..graph import GraphError

# Chain-wide constants (Phase 2 §2 common rule).
CONST_PURPOSES = ["read"]
CONST_CAPS: list = []
CONST_DATA_CLASSES = ["internal"]
CONST_TOOLS: list = []

_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*://")


class NormalizeError(GraphError):
    """Malformed input to a normalizer (an input error; CLI exit 2)."""


def unix_to_ts(seconds: Any, *, field: str) -> str:
    """Convert integer unix seconds (UTC) to the pinned ``YYYY-MM-DDTHH:MM:SSZ``."""
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
        raise NormalizeError(f"{field}: expected a unix-seconds number, got {seconds!r}")
    try:
        dt = datetime.fromtimestamp(int(seconds), tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise NormalizeError(f"{field}: not a valid unix timestamp: {seconds!r} ({exc})")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def strip_scheme(resource: str) -> str:
    """Strip a leading ``<scheme>://`` prefix; ``"*"`` is returned unchanged."""
    if resource == "*":
        return resource
    return _SCHEME_RE.sub("", resource)


def get_registry() -> dict[str, Callable[[Any], dict]]:
    """Return the format-name -> normalize(doc) registry (imported lazily)."""
    from . import attenu, descriptor, rfc8693, ucan

    return {
        "ucan": ucan.normalize,
        "rfc8693": rfc8693.normalize,
        "attenu": attenu.normalize,
        "descriptor": descriptor.normalize,
    }


def normalize(fmt: str, doc: Any) -> dict:
    """Normalize ``doc`` from format ``fmt`` to a ``dgraph/1`` dict."""
    registry = get_registry()
    if fmt not in registry:
        raise NormalizeError(f"unknown format {fmt!r}; known: {sorted(registry)}")
    return registry[fmt](doc)
