"""Resolve a caller group and evaluate its access policy."""

from groups import expand_alias, require_group
from policy import Rule, evaluate_policy


def is_allowed(group: str, resource: str, rules: tuple[Rule, ...]) -> bool:
    checked_group = require_group(group)
    canonical_group = expand_alias(checked_group)
    return evaluate_policy(canonical_group, resource, rules)
