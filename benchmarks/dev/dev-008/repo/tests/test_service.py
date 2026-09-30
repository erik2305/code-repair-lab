import pytest


def test_rejected_order_keeps_stock() -> None:
    from service import OrderService

    service = OrderService({"widget": 5})
    with pytest.raises(ValueError, match="customer"):
        service.place_order(" ", "widget", 2)
    assert service.inventory.stock["widget"] == 5


def test_rejected_order_keeps_ledger_empty() -> None:
    from service import OrderService

    service = OrderService({"widget": 5})
    with pytest.raises(ValueError, match="customer"):
        service.place_order(" ", "widget", 2)
    assert service.ledger.entries == []


def test_accepted_order_updates_both_states() -> None:
    from service import OrderService

    service = OrderService({"widget": 5})
    service.place_order("Ada", "widget", 2)
    assert service.inventory.stock["widget"] == 3
    assert service.ledger.entries == [("widget", 2)]
