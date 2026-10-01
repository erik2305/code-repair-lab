"""Recognize canonical groups and their public aliases."""

GROUPS = frozenset({"operators", "guests"})
ALIASES = {"on-call": "operators"}


class UnknownGroupError(LookupError):
    pass


def require_group(name: str) -> str:
    if name not in GROUPS:
        raise UnknownGroupError(name)
    return name


def expand_alias(name: str) -> str:
    return ALIASES.get(name, name)
