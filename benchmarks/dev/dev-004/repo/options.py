"""Build options for a small configurable operation."""

from collections.abc import Mapping

DEFAULT_OPTIONS: dict[str, object] = {
    "timeout": 30,
    "retries": 2,
    "verbose": False,
}


def build_options(overrides: Mapping[str, object] | None = None) -> dict[str, object]:
    """Return the standard options with this call's overrides applied."""
    options = DEFAULT_OPTIONS
    if overrides:
        options.update(overrides)
    return dict(options)
