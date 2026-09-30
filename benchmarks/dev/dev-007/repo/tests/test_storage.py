import json

from schema import Record
from storage import RecordStorage


def test_current_record_roundtrip() -> None:
    storage = RecordStorage()
    record = Record("Ada", 37)
    storage.save("person", record)
    assert storage.load("person") == record


def test_legacy_record_remains_readable() -> None:
    storage = RecordStorage()
    storage.documents["person"] = json.dumps({"name": "Ada", "age": 37})
    assert storage.load("person") == Record("Ada", 37)


def test_new_writes_use_current_format() -> None:
    storage = RecordStorage()
    storage.save("person", Record("Ada", 37))
    assert json.loads(storage.documents["person"])["version"] == 2
