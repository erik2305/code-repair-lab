import pytest


def test_invalid_numeric_value_uses_public_error() -> None:
    import loader
    from errors import ConfigError

    with pytest.raises(ConfigError):
        loader.load_config("retries=many")


def test_internal_failure_is_not_relabelled(monkeypatch: pytest.MonkeyPatch) -> None:
    import loader

    def broken_parser(_text: str) -> dict[str, int]:
        raise RuntimeError("internal parser failure")

    monkeypatch.setattr(loader, "parse_config", broken_parser)
    with pytest.raises(RuntimeError, match="internal parser failure"):
        loader.load_config("retries=3")


def test_malformed_entry_uses_public_error() -> None:
    import loader
    from errors import ConfigError

    with pytest.raises(ConfigError):
        loader.load_config("missing separator")


def test_valid_numeric_entry() -> None:
    import loader

    assert loader.load_config("retries=3") == {"retries": 3}
