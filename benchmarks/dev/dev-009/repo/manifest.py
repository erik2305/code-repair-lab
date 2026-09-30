"""Small in-memory catalog of manifest declarations."""


class ManifestCatalog:
    def __init__(self, declarations: dict[str, tuple[str, ...]]) -> None:
        self.declarations = dict(declarations)

    def references(self, manifest: str) -> tuple[str, ...]:
        return self.declarations[manifest]
