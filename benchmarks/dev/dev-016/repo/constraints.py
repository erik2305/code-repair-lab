"""Check a release against a simple minimum-version constraint."""

from versions import version_key


def accepts(release: str, constraint: str) -> bool:
    if not constraint.startswith(">="):
        raise ValueError("only inclusive minimum constraints are supported")
    minimum = constraint[2:]
    return version_key(release) > version_key(minimum)
