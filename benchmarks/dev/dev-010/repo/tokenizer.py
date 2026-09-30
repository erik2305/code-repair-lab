"""Split a tiny query into key=value fields."""


def split_fields(text: str) -> list[str]:
    return text.split(";")
