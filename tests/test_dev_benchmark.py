from pathlib import Path

from coderepair.tasks import SnapshotSource, load_task


def test_dev_001_manifest_and_snapshot_exist() -> None:
    task_directory = (
        Path(__file__).resolve().parents[1] / "benchmarks" / "dev" / "dev-001"
    )

    task = load_task(task_directory / "task.yaml")

    assert task.id == "dev-001"
    assert task.source == SnapshotSource(type="snapshot", path="repo")
    assert (task_directory / task.source.path).is_dir()
