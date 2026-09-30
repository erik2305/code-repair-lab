from service import SummaryService


def test_update_refreshes_summary() -> None:
    service = SummaryService({"item": "old"})
    assert service.get_summary("item") == "item: old"
    service.update("item", "new")
    assert service.get_summary("item") == "item: new"


def test_repeated_read_reuses_cached_summary() -> None:
    service = SummaryService({"item": "value"})
    assert service.get_summary("item") == "item: value"
    assert service.get_summary("item") == "item: value"
    assert service.cache.computations == 1


def test_updating_one_record_keeps_other_cached_summary() -> None:
    service = SummaryService({"first": "one", "second": "two"})
    service.get_summary("first")
    service.get_summary("second")
    service.update("first", "changed")
    assert service.get_summary("second") == "second: two"
