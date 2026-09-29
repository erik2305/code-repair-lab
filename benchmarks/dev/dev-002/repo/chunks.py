"""Sequence chunking utility."""

from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


def chunk_items(items: Sequence[T], size: int) -> list[list[T]]:
    """Divide items into ordered, non-empty groups of at most size items."""
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError("size must be a positive integer")

    groups: list[list[T]] = []
    for start in range(0, len(items) - size + 1, size):
        groups.append(list(items[start : start + size]))
    return groups
