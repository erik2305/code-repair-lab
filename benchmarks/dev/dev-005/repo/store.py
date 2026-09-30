"""Mutable source records for the summary service."""


class Store:
    def __init__(self, records: dict[str, str]) -> None:
        self.records = dict(records)

    def get(self, key: str) -> str:
        return self.records[key]

    def update(self, key: str, value: str) -> None:
        self.records[key] = value
