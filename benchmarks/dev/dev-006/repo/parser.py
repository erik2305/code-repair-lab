"""Parse a small external numeric configuration format."""

from errors import EntrySyntaxError, NumericValueError


def parse_config(text: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        if "=" not in line:
            raise EntrySyntaxError("expected key=value entry")
        key, raw = line.split("=", 1)
        if not key.strip():
            raise EntrySyntaxError("entry key is empty")
        try:
            values[key.strip()] = int(raw.strip())
        except ValueError as error:
            raise NumericValueError("entry value must be an integer") from error
    return values
