import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
INTERFACE_SRC = ROOT_DIR / "plugins/automas_maafw_interface/src"
SCRIPT_MAAFW_SRC = ROOT_DIR / "plugins/automas_script_maafw/src"
ADB_SRC = ROOT_DIR / "plugins/automas_maafw_controller_adb/src"
WIN32_SRC = ROOT_DIR / "plugins/automas_maafw_controller_win32/src"
PACK_M9A_SRC = ROOT_DIR / "plugins/automas_script_maafw_pack_m9a/src"
for source_path in (
    str(INTERFACE_SRC),
    str(SCRIPT_MAAFW_SRC),
    str(ADB_SRC),
    str(WIN32_SRC),
    str(PACK_M9A_SRC),
):
    if source_path not in sys.path:
        sys.path.insert(0, source_path)

from automas_maafw_controller_adb.service import MaaFWAdbControllerService
from automas_maafw_controller_win32.service import (
    MaaFWWin32ControllerService,
    MaaFWWin32Window,
)
from automas_script_maafw.registry import MaaFWRegistryService
from automas_script_maafw_pack_m9a.service import M9APackService


class MaaFWControllerPluginTest(unittest.TestCase):
    def test_adb_provider_definition_and_device_spec(self) -> None:
        service = MaaFWAdbControllerService()

        definition = service.get_provider_definition()
        self.assertEqual(definition["key"], "adb")
        self.assertEqual(definition["controllerTypes"], ["Adb"])

        spec = service.build_device_spec(
            adb_path="adb.exe",
            address="127.0.0.1:5555",
            screencap_methods=1,
            input_methods=2,
            config={"k": "v"},
        )
        self.assertEqual(spec["type"], "Adb")
        self.assertEqual(spec["adbPath"], "adb.exe")
        self.assertEqual(spec["address"], "127.0.0.1:5555")
        self.assertEqual(spec["config"], {"k": "v"})

    def test_win32_provider_matches_interface_window_regex(self) -> None:
        service = MaaFWWin32ControllerService()
        controller = {
            "name": "pc",
            "type": "Win32",
            "win32": {
                "class_regex": "GameWindow",
                "window_regex": "Reverse",
            },
        }
        windows = [
            MaaFWWin32Window(hWnd=1, className="OtherWindow", windowName="Reverse"),
            MaaFWWin32Window(hWnd=2, className="GameWindowClass", windowName="Reverse 1999"),
        ]

        matches = service.match_controller_windows(controller, windows)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].hWnd, 2)
        self.assertEqual(matches[0].controllerName, "pc")

    def test_win32_provider_rejects_nested_quantifier_regex(self) -> None:
        service = MaaFWWin32ControllerService()
        controller = {
            "name": "pc",
            "type": "Win32",
            "win32": {
                "class_regex": "(a+)+$",
                "window_regex": "Reverse",
            },
        }
        windows = [
            MaaFWWin32Window(hWnd=1, className="a" * 128, windowName="Reverse"),
        ]

        with self.assertRaisesRegex(RuntimeError, "nested quantifiers"):
            service.match_controller_windows(controller, windows)

    def test_registry_collects_controller_providers_and_m9a_pack(self) -> None:
        registry = MaaFWRegistryService()
        adb_service = MaaFWAdbControllerService()
        win32_service = MaaFWWin32ControllerService()
        m9a_service = M9APackService()

        registry.register_controller_provider(adb_service.get_provider_definition())
        registry.register_controller_provider(win32_service.get_provider_definition())
        registry.register_project_pack(m9a_service.get_definition())

        self.assertEqual(
            [item["key"] for item in registry.list_controller_providers()],
            ["adb", "win32"],
        )
        self.assertEqual(registry.get_project_pack("m9a")["display_name"], "M9A")

        registry.unregister_controller_provider("adb")
        registry.unregister_project_pack("m9a")
        self.assertIsNone(registry.get_controller_provider("adb"))
        self.assertIsNone(registry.get_project_pack("m9a"))


if __name__ == "__main__":
    unittest.main()
