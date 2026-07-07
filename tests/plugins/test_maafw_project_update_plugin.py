import json
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[2]
INTERFACE_SRC = ROOT_DIR / "plugins/automas_maafw_interface/src"
UPDATE_SRC = ROOT_DIR / "plugins/automas_maafw_project_update/src"
for source_path in (str(INTERFACE_SRC), str(UPDATE_SRC)):
    if source_path not in sys.path:
        sys.path.insert(0, source_path)

from automas_maafw_project_update import updater
from automas_maafw_project_update.updater import MaaFWProjectUpdateError


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _write_zip(package_path: Path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(package_path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


class MaaFWProjectUpdatePluginTest(unittest.IsolatedAsyncioTestCase):
    async def test_applies_full_package(self) -> None:
        with TemporaryDirectory() as directory:
            project_path = Path(directory) / "project"
            project_path.mkdir()
            _write_json(project_path / "interface.json", {"name": "old"})
            (project_path / "obsolete.txt").write_text("old", encoding="utf-8")

            package_path = Path(directory) / "full.zip"
            _write_zip(
                package_path,
                {
                    "package/interface.json": '{"name":"new"}',
                    "package/resource/data.txt": "new-data",
                },
            )

            await updater._apply_update_package(project_path, package_path, lambda _: None)

            self.assertEqual(
                json.loads((project_path / "interface.json").read_text(encoding="utf-8")),
                {"name": "new"},
            )
            self.assertEqual(
                (project_path / "resource/data.txt").read_text(encoding="utf-8"),
                "new-data",
            )
            self.assertEqual(
                (project_path / "obsolete.txt").read_text(encoding="utf-8"),
                "old",
            )
            self.assertFalse(package_path.exists())

    async def test_applies_incremental_package_with_changes_file(self) -> None:
        with TemporaryDirectory() as directory:
            project_path = Path(directory) / "project"
            project_path.mkdir()
            _write_json(project_path / "interface.json", {"name": "old"})
            (project_path / "remove.txt").write_text("remove-me", encoding="utf-8")
            (project_path / "keep.txt").write_text("keep", encoding="utf-8")

            package_path = Path(directory) / "incremental.zip"
            _write_zip(
                package_path,
                {
                    "package/interface.json": '{"name":"package-root"}',
                    "package/changes.json": json.dumps(
                        {"payload": "payload", "delete": ["remove.txt"]}
                    ),
                    "package/payload/interface.json": '{"name":"new"}',
                    "package/payload/add.txt": "added",
                },
            )

            await updater._apply_update_package(project_path, package_path, lambda _: None)

            self.assertEqual(
                json.loads((project_path / "interface.json").read_text(encoding="utf-8")),
                {"name": "new"},
            )
            self.assertEqual((project_path / "add.txt").read_text(encoding="utf-8"), "added")
            self.assertEqual((project_path / "keep.txt").read_text(encoding="utf-8"), "keep")
            self.assertFalse((project_path / "remove.txt").exists())

    async def test_rejects_unsafe_zip_member_path(self) -> None:
        with TemporaryDirectory() as directory:
            project_path = Path(directory) / "project"
            project_path.mkdir()
            _write_json(project_path / "interface.json", {"name": "old"})

            package_path = Path(directory) / "unsafe.zip"
            _write_zip(
                package_path,
                {
                    "package/interface.json": '{"name":"new"}',
                    "../escape.txt": "unsafe",
                },
            )

            with self.assertRaisesRegex(MaaFWProjectUpdateError, "unsafe path"):
                await updater._apply_update_package(project_path, package_path, lambda _: None)

            self.assertFalse((Path(directory) / "escape.txt").exists())
            self.assertEqual(
                json.loads((project_path / "interface.json").read_text(encoding="utf-8")),
                {"name": "old"},
            )

    async def test_restores_backup_when_full_package_apply_fails(self) -> None:
        with TemporaryDirectory() as directory:
            project_path = Path(directory) / "project"
            project_path.mkdir()
            _write_json(project_path / "interface.json", {"name": "old"})
            (project_path / "keep.txt").write_text("old-keep", encoding="utf-8")

            package_path = Path(directory) / "broken.zip"
            _write_zip(
                package_path,
                {
                    "package/interface.json": '{"name":"new"}',
                    "package/keep.txt": "new-keep",
                },
            )

            original_copy_path = updater._copy_path

            def fail_on_keep(source: Path, target: Path) -> None:
                if target.name == "keep.txt":
                    raise RuntimeError("copy failed")
                original_copy_path(source, target)

            with patch.object(updater, "_copy_path", side_effect=fail_on_keep):
                with self.assertRaisesRegex(RuntimeError, "copy failed"):
                    await updater._apply_update_package(
                        project_path,
                        package_path,
                        lambda _: None,
                    )

            self.assertEqual(
                json.loads((project_path / "interface.json").read_text(encoding="utf-8")),
                {"name": "old"},
            )
            self.assertEqual(
                (project_path / "keep.txt").read_text(encoding="utf-8"),
                "old-keep",
            )
            self.assertFalse((project_path / ".mas-update/backup").exists())

    async def test_download_error_sanitizes_secret_query_values(self) -> None:
        with TemporaryDirectory() as directory:
            project_path = Path(directory) / "project"
            project_path.mkdir()
            logs: list[str] = []

            async def fail_download(*args, **kwargs) -> None:
                raise RuntimeError(
                    "failed https://example.invalid/file.zip?cdk=SECRET&token=TOKEN"
                )

            with patch.object(updater, "DOWNLOAD_RETRY_TIMES", 1):
                with patch.object(updater, "_stream_update_package", side_effect=fail_download):
                    with self.assertRaises(MaaFWProjectUpdateError) as context:
                        await updater._download_update_package(
                            project_path,
                            "https://example.invalid/file.zip?cdk=SECRET&token=TOKEN",
                            expected_sha256=None,
                            proxy=None,
                            send_log=logs.append,
                        )

            combined = "\n".join([str(context.exception), *logs])
            self.assertNotIn("SECRET", combined)
            self.assertNotIn("TOKEN", combined)
            self.assertIn("cdk=***", combined)
            self.assertIsNone(context.exception.__cause__)

    async def test_mirrorchyan_check_error_sanitizes_secret_query_values(self) -> None:
        class FakeClient:
            def __init__(self, *args, **kwargs) -> None:
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

            async def get(self, *args, **kwargs):
                raise updater.httpx.RequestError(
                    "connect failed: https://mirrorchyan.com/latest?cdk=SECRET&token=TOKEN"
                )

        interface = type(
            "Interface",
            (),
            {
                "mirrorchyan_rid": "rid",
                "mirrorchyan_multiplatform": False,
            },
        )()

        with patch.object(updater.httpx, "AsyncClient", FakeClient):
            with self.assertRaises(MaaFWProjectUpdateError) as context:
                await updater._check_mirrorchyan_update(
                    interface,
                    current_version="1.0.0",
                    mirror_cdk="SECRET",
                    channel="stable",
                    proxy=None,
                )

        message = str(context.exception)
        self.assertNotIn("SECRET", message)
        self.assertNotIn("TOKEN", message)
        self.assertIn("cdk=***", message)
        self.assertIsNone(context.exception.__cause__)


if __name__ == "__main__":
    unittest.main()
