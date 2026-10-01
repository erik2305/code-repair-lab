from window import page_from_cursor, window


def test_final_window_includes_last_item() -> None:
    assert window(["a", "b", "c", "d"], 2, 2) == ["c", "d"]


def test_earlier_window_keeps_requested_count() -> None:
    assert window(["a", "b", "c", "d"], 0, 2) == ["a", "b"]


def test_cursor_page_uses_offset_and_size() -> None:
    assert page_from_cursor(["a", "b", "c", "d"], "p:1", 2) == ["b", "c"]
