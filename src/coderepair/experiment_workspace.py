"""Disposable experiment directories with normal inherited filesystem permissions."""

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


@contextmanager
def temporary_experiment_workspace(scratch_root: Path) -> Iterator[Path]:
    """Yield a unique parent for create_workspace; remove only that child on exit.

    Ordinary mkdir (not tempfile's mode=0o700) preserves project ACL inheritance
    on Windows. The caller materializes its repository into child / "workspace".
    """
    parent = scratch_root.absolute()
    for directory in (*reversed(parent.parents), parent):
        if directory.is_symlink() or directory.is_junction():
            raise ValueError("experiment scratch ancestors must not be links")
        if directory.exists() and not directory.is_dir():
            raise NotADirectoryError("experiment scratch parent must be a directory")
    parent.mkdir(exist_ok=True)
    parent = parent.resolve()
    child = parent / f"workspace-{uuid4().hex}"
    child.mkdir()
    try:
        yield child
    finally:
        # Never recursively delete the persistent scratch parent or a snapshot.
        if child.is_symlink() or child.is_junction():
            raise ValueError("experiment scratch child was replaced by a link")
        shutil.rmtree(child)
