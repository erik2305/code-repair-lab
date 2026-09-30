"""Current stock levels."""


class Inventory:
    def __init__(self, stock: dict[str, int]) -> None:
        self.stock = dict(stock)

    def take(self, item: str, quantity: int) -> None:
        if quantity <= 0 or self.stock[item] < quantity:
            raise ValueError("invalid quantity")
        self.stock[item] -= quantity
