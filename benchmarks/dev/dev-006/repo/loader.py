"""Stable public boundary for external configuration data."""

from errors import ConfigError, EntrySyntaxError
from parser import parse_config


def load_config(text: str) -> dict[str, int]:
    try:
        return parse_config(text)
    except EntrySyntaxError as error:
        raise ConfigError("invalid configuration") from error
