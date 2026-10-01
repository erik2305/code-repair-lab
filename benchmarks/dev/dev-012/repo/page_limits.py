"""Apply the service's page-size limits."""

MAX_PAGE_SIZE = 50


def bounded_size(requested: int) -> int:
    if requested <= 0:
        raise ValueError("page size must be positive")
    return min(requested, MAX_PAGE_SIZE)
