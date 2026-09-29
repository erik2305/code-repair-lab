import options


def fresh_defaults() -> None:
    options.DEFAULT_OPTIONS = {"timeout": 30, "retries": 2, "verbose": False}


def test_default_options() -> None:
    fresh_defaults()
    assert options.build_options() == {"timeout": 30, "retries": 2, "verbose": False}


def test_override_applies_to_its_call() -> None:
    fresh_defaults()
    assert options.build_options({"timeout": 10}) == {
        "timeout": 10,
        "retries": 2,
        "verbose": False,
    }


def test_override_does_not_leak_into_later_call() -> None:
    fresh_defaults()
    options.build_options({"timeout": 10})
    assert options.build_options() == {"timeout": 30, "retries": 2, "verbose": False}


def test_independent_override_calls() -> None:
    fresh_defaults()
    options.build_options({"timeout": 10})
    assert options.build_options({"verbose": True}) == {
        "timeout": 30,
        "retries": 2,
        "verbose": True,
    }


def test_caller_overrides_are_unchanged() -> None:
    fresh_defaults()
    overrides = {"timeout": 10}
    options.build_options(overrides)
    assert overrides == {"timeout": 10}
