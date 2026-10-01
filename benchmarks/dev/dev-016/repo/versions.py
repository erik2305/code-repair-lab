"""Parse the resolver's numeric dotted-version format."""


def version_key(value: str) -> tuple[int, ...]:
    parts = value.split(".")
    if not parts or any(not part.isdecimal() for part in parts):
        raise ValueError("version must contain numeric dotted components")
    return tuple(int(part) for part in parts)
