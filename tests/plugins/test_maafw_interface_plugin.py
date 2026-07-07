import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT_DIR = Path(__file__).resolve().parents[2]
INTERFACE_SRC = ROOT_DIR / "plugins/automas_maafw_interface/src"
if str(INTERFACE_SRC) not in sys.path:
    sys.path.insert(0, str(INTERFACE_SRC))

from automas_maafw_interface.service import MaaFWInterfaceService
from automas_maafw_interface.preview import resolve_description


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class MaaFWInterfacePluginTest(unittest.TestCase):
    def test_loads_import_scan_select_and_normalizes_execution_payload(self) -> None:
        with TemporaryDirectory() as directory:
            project_path = Path(directory)
            (project_path / "profiles").mkdir()
            _write_json(project_path / "profiles/daily.json", {"name": "daily"})
            _write_json(project_path / "profiles/weekly.json", {"name": "weekly"})
            _write_json(
                project_path / "fragments/tasks.json",
                {
                    "task": [
                        {
                            "name": "Daily",
                            "label": "Daily Task",
                            "entry": "Daily",
                            "option": ["profile"],
                        }
                    ],
                    "option": {
                        "profile": {
                            "type": "scan_select",
                            "label": "Profile",
                            "scan_dir": "profiles",
                            "scan_filter": "*.json",
                            "default_case": "daily.json",
                        }
                    },
                    "preset": [
                        {
                            "name": "daily",
                            "task": [
                                {
                                    "name": "Daily",
                                    "enabled": True,
                                    "option": {"profile": "daily.json"},
                                }
                            ],
                        }
                    ],
                },
            )
            _write_json(
                project_path / "interface.json",
                {
                    "interface_version": 2,
                    "name": "sample-maafw",
                    "version": "1.0.0",
                    "github": "AUTO-MAS-Project/sample-maafw",
                    "controller": [
                        {"name": "win32", "type": "win32", "option": ["mode"]}
                    ],
                    "resource": [
                        {
                            "name": "default",
                            "path": ["resource"],
                            "controller": ["win32"],
                        }
                    ],
                    "option": {
                        "mode": {
                            "type": "select",
                            "default_case": "normal",
                            "cases": [
                                {"name": "normal", "label": "Normal"},
                                {"name": "fast", "label": "Fast"},
                            ],
                        }
                    },
                    "import": ["fragments/tasks.json"],
                },
            )

            service = MaaFWInterfaceService()
            interface = service.load(project_path, force_reload=True)
            snapshot = service.build_default_snapshot(interface, preset="daily")
            tasks, options = service.normalize_execution_payload(
                interface,
                ["Daily", "Daily", "Missing"],
                {"Daily": {"mode": "fast", "profile": "weekly.json"}},
                controller="win32",
                resource="default",
            )

            self.assertEqual(interface.name, "sample-maafw")
            self.assertEqual([task.name for task in interface.task], ["Daily"])
            self.assertEqual(
                [case.name for case in interface.option["profile"].cases or []],
                ["daily.json", "weekly.json"],
            )
            self.assertEqual(snapshot.taskOrder, ["Daily"])
            self.assertTrue(snapshot.taskChecked["Daily"])
            self.assertEqual(snapshot.taskOptions["Daily"]["profile"], "daily.json")
            self.assertEqual(tasks, ["Daily"])
            self.assertEqual(
                options,
                {"Daily": {"mode": "fast", "profile": "weekly.json"}},
            )

    def test_description_preview_does_not_read_html_file(self) -> None:
        with TemporaryDirectory() as directory:
            project_path = Path(directory)
            (project_path / "desc.html").write_text(
                "<script>alert(1)</script>",
                encoding="utf-8",
            )
            (project_path / "desc.md").write_text("safe markdown", encoding="utf-8")

            self.assertEqual(
                resolve_description(project_path, "desc.html"),
                "desc.html",
            )
            self.assertEqual(
                resolve_description(project_path, "desc.md"),
                "safe markdown",
            )


if __name__ == "__main__":
    unittest.main()
