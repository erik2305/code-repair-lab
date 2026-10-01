from authorizer import is_allowed
from policy import Rule


def test_policy_flow_integration() -> None:
    rules = (
        Rule("operators", "*", "allow"),
        Rule("operators", "deploy", "deny"),
    )
    decision = is_allowed("on-call", "deploy", rules)
    assert decision is False, "explicit deny must override allow"
