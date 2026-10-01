from authorizer import is_allowed
from groups import UnknownGroupError
from policy import Rule


def test_alias_group_can_be_authorized() -> None:
    rules = (Rule("operators", "deploy", "allow"),)
    assert is_allowed("on-call", "deploy", rules)


def test_canonical_group_uses_matching_rule() -> None:
    rules = (Rule("operators", "deploy", "allow"),)
    assert is_allowed("operators", "deploy", rules)


def test_unknown_group_is_rejected() -> None:
    try:
        is_allowed("unregistered", "deploy", ())
    except UnknownGroupError:
        pass
    else:
        raise AssertionError("unknown groups must be rejected")
