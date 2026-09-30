"""Customer acceptance rule for orders."""


def validate_customer(customer: str) -> None:
    if not customer.strip():
        raise ValueError("customer is required")
