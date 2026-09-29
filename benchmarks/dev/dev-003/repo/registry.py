"""Small registry indexed by canonical identifiers."""

from identifiers import canonicalize_identifier


class Registry:
    """Store distinct values by their canonical identifier."""

    def __init__(self) -> None:
        self._entries: dict[str, str] = {}

    def register(self, identifier: str, value: str) -> None:
        key = canonicalize_identifier(identifier)
        if key in self._entries:
            raise ValueError("identifier is already registered")
        self._entries[key] = value

    def lookup(self, identifier: str) -> str:
        return self._entries[identifier]
