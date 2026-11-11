"""Resource-pattern subset semantics (pinned, §3 of the Phase 1 spec).

A pattern is exactly one of:
  * ``"*"``                  — matches everything
  * a literal with no ``*``  — matches only itself
  * a literal prefix ending in ``/*`` — a prefix wildcard

Anything else is an input error (raised as :class:`PatternError`).

Subsumption (``p`` is subsumed by ``q``, written ``p subset-of q``) holds iff:
  * ``q == "*"``, or
  * ``p == q``, or
  * ``q`` ends in ``/*`` and (``p == q[:-2]`` or ``p`` starts with ``q[:-1]``).

So ``q = "db/*"`` subsumes the bare prefix ``db`` (``q[:-2] == "db"``) and
anything under ``db/`` (``q[:-1] == "db/"``). It does not subsume ``dbx``.
"""

from __future__ import annotations


class PatternError(ValueError):
    """Raised when a resource pattern is outside the closed grammar."""


def validate_pattern(p: str) -> str:
    """Return ``p`` if it is a legal pattern, else raise :class:`PatternError`.

    Legal shapes: ``"*"``; a literal containing no ``*``; or a literal prefix
    ending in ``/*`` where the portion before ``/*`` itself contains no ``*``.
    """
    if not isinstance(p, str):
        raise PatternError(f"resource pattern must be a string, got {type(p).__name__}")
    if p == "*":
        return p
    if "*" not in p:
        return p
    # Contains at least one '*' and is not the bare '*'. Only legal form is
    # a prefix ending in exactly '/*' with no other '*'.
    if p.endswith("/*"):
        prefix = p[:-2]
        if "*" not in prefix:
            return p
    raise PatternError(f"illegal resource pattern: {p!r}")


def is_subsumed(p: str, q: str) -> bool:
    """Return True iff pattern ``p`` is subsumed by pattern ``q`` (``p subset-of q``).

    Both ``p`` and ``q`` are assumed already validated by
    :func:`validate_pattern`; callers validate at load time.
    """
    if q == "*":
        return True
    if p == q:
        return True
    if q.endswith("/*"):
        # q[:-2] is the prefix without the trailing '/*'; q[:-1] keeps the '/'.
        if p == q[:-2]:
            return True
        if p.startswith(q[:-1]):
            return True
    return False


def set_subset(a: list[str], b: list[str]) -> bool:
    """Return True iff resource set ``a`` subset-of resource set ``b``.

    ``a subset-of b`` iff every pattern in ``a`` is subsumed by *some single*
    pattern in ``b``. Joint coverage by several patterns in ``b`` is out of
    scope (conservative choice, recorded in SPEC.md).
    """
    for pa in a:
        if not any(is_subsumed(pa, pb) for pb in b):
            return False
    return True
