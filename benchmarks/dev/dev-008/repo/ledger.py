"""Externally visible activity for accepted orders."""


class Ledger:
    def __init__(self) -> None:
        self.entries: list[tuple[str, int]] = []

    def record(self, item: str, quantity: int) -> None:
        self.entries.append((item, quantity))
