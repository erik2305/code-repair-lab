"""The small record shared by storage and serialization."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Record:
    name: str
    age: int
