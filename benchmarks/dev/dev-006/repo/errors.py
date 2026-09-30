"""Public and parser-level configuration errors."""


class ConfigError(ValueError):
    """External configuration input is malformed."""


class EntrySyntaxError(ValueError):
    """An entry does not use the required key=value syntax."""


class NumericValueError(ValueError):
    """A numeric entry has an invalid value."""
