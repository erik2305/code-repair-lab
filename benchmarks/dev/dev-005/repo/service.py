"""Summary reads and record updates across store and cache."""

from cache import SummaryCache
from store import Store


class SummaryService:
    def __init__(self, records: dict[str, str]) -> None:
        self.store = Store(records)
        self.cache = SummaryCache()

    def get_summary(self, key: str) -> str:
        return self.cache.get(key, lambda: f"{key}: {self.store.get(key)}")

    def update(self, key: str, value: str) -> None:
        self.store.update(key, value)
