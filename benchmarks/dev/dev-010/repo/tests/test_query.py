from query import parse_query


def test_escaped_separator_stays_inside_value() -> None:
    assert parse_query(r"name=Red\;Blue;kind=Primary") == {
        "name": "red;blue",
        "kind": "primary",
    }


def test_quoted_separator_stays_inside_value() -> None:
    assert parse_query('name="Red;Blue";kind=Primary') == {
        "name": "red;blue",
        "kind": "primary",
    }


def test_ordinary_fields_and_normalization() -> None:
    assert parse_query("name= Ada ;kind= Primary ") == {
        "name": "ada",
        "kind": "primary",
    }
