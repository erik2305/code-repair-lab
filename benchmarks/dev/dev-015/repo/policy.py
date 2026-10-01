"""Evaluate ordered access rules for one group and resource."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    group: str
    resource: str
    effect: str


def evaluate_policy(group: str, resource: str, rules: tuple[Rule, ...]) -> bool:
    for rule in rules:
        if rule.group == group and rule.resource in (resource, "*"):
            return rule.effect == "allow"
    return False
