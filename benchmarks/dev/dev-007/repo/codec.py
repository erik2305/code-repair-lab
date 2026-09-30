"""Persisted record representations."""

from schema import Record


def encode(record: Record) -> dict[str, object]:
    return {"version": 2, "payload": {"name": record.name, "age": record.age}}


def decode(data: dict[str, object]) -> Record:
    return Record(name=data["name"], age=data["age"])
