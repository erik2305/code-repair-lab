"""Resolve data references across included manifests."""

from manifest import ManifestCatalog
from paths import resolve_reference


def collect_data(catalog: ManifestCatalog, root: str) -> tuple[str, ...]:
    data: list[str] = []

    def visit(manifest: str, base: str) -> None:
        for reference in catalog.references(manifest):
            if reference.endswith(".manifest"):
                child = resolve_reference(base, reference)
                visit(child, base)
            else:
                data.append(resolve_reference(base, reference))

    visit(root, root)
    return tuple(data)
