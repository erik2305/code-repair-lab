from identifiers import canonicalize_identifier
from registry import Registry


def test_canonicalization_contract() -> None:
    assert canonicalize_identifier("  User-ID  ") == "user-id"


def test_exact_identifier_lookup() -> None:
    registry = Registry()
    registry.register("user-id", "user record")
    assert registry.lookup("user-id") == "user record"


def test_lookup_is_case_insensitive() -> None:
    registry = Registry()
    registry.register("User-ID", "user record")
    assert registry.lookup("user-id") == "user record"


def test_lookup_ignores_surrounding_whitespace() -> None:
    registry = Registry()
    registry.register("user-id", "user record")
    assert registry.lookup(" user-id ") == "user record"


def test_lookup_accepts_combined_case_and_whitespace() -> None:
    registry = Registry()
    registry.register("User-ID", "user record")
    assert registry.lookup(" user-id ") == "user record"


def test_unrelated_identifiers_stay_distinct() -> None:
    import pytest

    registry = Registry()
    registry.register("user-id", "user record")
    registry.register("order-id", "order record")
    assert registry.lookup("user-id") == "user record"
    assert registry.lookup("order-id") == "order record"
    with pytest.raises(KeyError):
        registry.lookup("missing-id")


def test_equivalent_duplicate_registration_is_rejected() -> None:
    import pytest

    registry = Registry()
    registry.register("User-ID", "first")
    with pytest.raises(ValueError, match="already registered"):
        registry.register(" user-id ", "second")
