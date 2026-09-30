"""Order transition across inventory and ledger."""

from inventory import Inventory
from ledger import Ledger
from validators import validate_customer


class OrderService:
    def __init__(self, stock: dict[str, int]) -> None:
        self.inventory = Inventory(stock)
        self.ledger = Ledger()

    def place_order(self, customer: str, item: str, quantity: int) -> None:
        self.inventory.take(item, quantity)
        self.ledger.record(item, quantity)
        validate_customer(customer)
