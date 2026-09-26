from text_utils import normalize_name


def test_normalize_name_strips_surrounding_spaces() -> None:
    assert normalize_name("  Ada Lovelace  ") == "Ada Lovelace"


def test_normalize_name_strips_non_space_whitespace() -> None:
    assert normalize_name("\tAda Lovelace\n") == "Ada Lovelace"
