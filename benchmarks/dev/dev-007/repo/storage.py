"""In-memory persisted documents using the record codec."""

import json

from codec import decode, encode
from schema import Record


class RecordStorage:
    def __init__(self) -> None:
        self.documents: dict[str, str] = {}

    def save(self, key: str, record: Record) -> None:
        self.documents[key] = json.dumps(encode(record))

    def load(self, key: str) -> Record:
        return decode(json.loads(self.documents[key]))
