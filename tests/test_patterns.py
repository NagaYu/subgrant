"""Resource-pattern grammar and subsumption truth table (§3)."""

import pytest

from subgrant.patterns import PatternError, is_subsumed, set_subset, validate_pattern


@pytest.mark.parametrize("p", ["*", "db", "db/project-x/*", "a/b/c", "", "files/reports/*"])
def test_valid_patterns(p):
    assert validate_pattern(p) == p


@pytest.mark.parametrize("p", ["db/*/x", "*/x", "a*b", "db**", "a*"])
def test_invalid_patterns(p):
    with pytest.raises(PatternError):
        validate_pattern(p)


def test_invalid_pattern_type():
    with pytest.raises(PatternError):
        validate_pattern(5)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "p,q,expected",
    [
        # q == "*" subsumes anything
        ("anything", "*", True),
        ("db/x/*", "*", True),
        # equality
        ("db/project-x/*", "db/project-x/*", True),
        ("db", "db", True),
        # prefix: bare prefix equals q[:-2]
        ("db", "db/*", True),
        # prefix: p under the prefix
        ("db/project-x", "db/*", True),
        ("db/project-x/*", "db/*", True),
        ("db/a/b/c", "db/*", True),
        # the classic 'db' vs 'db/*' boundary: 'dbx' is NOT under 'db/*'
        ("dbx", "db/*", False),
        ("dbx/y", "db/*", False),
        # literal q only subsumes itself
        ("db/x", "db", False),
        ("db", "db/x", False),
        # '*' as p is only subsumed by '*'
        ("*", "db/*", False),
        ("*", "*", True),
        # unrelated
        ("logs/app/*", "db/project-x/*", False),
    ],
)
def test_subsumption_truth_table(p, q, expected):
    assert is_subsumed(p, q) is expected


def test_set_subset():
    assert set_subset(["db/x", "db/y"], ["db/*"]) is True
    assert set_subset(["db/x", "logs/a"], ["db/*"]) is False
    assert set_subset([], ["db/*"]) is True  # empty set is a subset
    # joint coverage is NOT honored (conservative choice): a single pattern in B
    # must cover each pattern in A.
    assert set_subset(["ab"], ["a", "b"]) is False
