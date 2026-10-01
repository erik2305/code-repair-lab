from resolver import NoCandidateError, resolve


def test_inclusive_minimum_accepts_boundary_release() -> None:
    assert resolve(["2"], ">=2") == "2"


def test_release_below_minimum_is_rejected() -> None:
    try:
        resolve(["1"], ">=2")
    except NoCandidateError:
        pass
    else:
        raise AssertionError("releases below the minimum must be rejected")
