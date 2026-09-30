from manifest import ManifestCatalog
from resolver import collect_data


def test_nested_manifest_resolves_its_own_data() -> None:
    catalog = ManifestCatalog(
        {
            "root/main.manifest": ("sections/part.manifest",),
            "root/sections/part.manifest": ("data.txt",),
        }
    )
    assert collect_data(catalog, "root/main.manifest") == ("root/sections/data.txt",)


def test_deeper_include_uses_its_declaring_manifest() -> None:
    catalog = ManifestCatalog(
        {
            "root/main.manifest": ("sections/part.manifest",),
            "root/sections/part.manifest": ("sub/child.manifest",),
            "root/sections/sub/child.manifest": ("data.txt",),
        }
    )
    assert collect_data(catalog, "root/main.manifest") == (
        "root/sections/sub/data.txt",
    )


def test_top_level_relative_data() -> None:
    catalog = ManifestCatalog({"root/main.manifest": ("data.txt",)})
    assert collect_data(catalog, "root/main.manifest") == ("root/data.txt",)
