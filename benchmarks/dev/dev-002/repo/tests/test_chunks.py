from chunks import chunk_items


def test_exact_division() -> None:
    assert chunk_items([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]


def test_keeps_one_item_final_chunk() -> None:
    assert chunk_items([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_keeps_larger_partial_final_chunk() -> None:
    assert chunk_items([1, 2, 3, 4, 5], 3) == [[1, 2, 3], [4, 5]]


def test_empty_input() -> None:
    assert chunk_items([], 3) == []


def test_size_larger_than_input() -> None:
    assert chunk_items([1, 2], 5) == [[1, 2]]


def test_rejects_invalid_size() -> None:
    import pytest

    for size in (0, -1, True, 1.5):
        with pytest.raises(ValueError, match="positive integer"):
            chunk_items([1, 2], size)  # type: ignore[arg-type]
