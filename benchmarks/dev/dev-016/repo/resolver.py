"""Choose the latest compatible release from an available index."""

from constraints import accepts


class NoCandidateError(LookupError):
    pass


def resolve(releases: list[str], constraint: str) -> str:
    candidates = [release for release in releases if accepts(release, constraint)]
    if not candidates:
        raise NoCandidateError(constraint)
    return max(candidates)
