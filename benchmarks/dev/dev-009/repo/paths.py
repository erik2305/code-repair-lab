"""Portable relative reference resolution."""

import posixpath


def resolve_reference(declaring_manifest: str, reference: str) -> str:
    return posixpath.normpath(
        posixpath.join(posixpath.dirname(declaring_manifest), reference)
    )
