"""Remove absent fields from decoded packet records."""


def normalize_fields(fields: dict[str, int | None]) -> dict[str, int]:
    present = {name: value for name, value in fields.items() if value}
    if not present:
        raise ValueError("record contains no present fields")
    return present
