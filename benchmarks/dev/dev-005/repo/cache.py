"""Keyed cache for derived record views."""

from collections.abc import Callable


class SummaryCache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.computations = 0

    def get(self, key: str, compute: Callable[[], str]) -> str:
        if key not in self.values:
            self.values[key] = compute()
            self.computations += 1
        return self.values[key]

    def invalidate(self, key: str) -> None:
        self.values.pop(key, None)
