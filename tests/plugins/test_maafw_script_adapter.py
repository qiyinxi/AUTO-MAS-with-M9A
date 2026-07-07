import json
import sys
import types
import unittest
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_MAAFW_SRC = ROOT_DIR / "plugins/automas_script_maafw/src"
for source_path in (str(SCRIPT_MAAFW_SRC),):
    if source_path not in sys.path:
        sys.path.insert(0, source_path)

for module_name in ("win32api", "win32gui", "win32con", "win32process", "win32crypt"):
    sys.modules.setdefault(module_name, types.ModuleType(module_name))
win32com = types.ModuleType("win32com")
win32com_client = types.ModuleType("win32com.client")
win32com.client = win32com_client
sys.modules.setdefault("win32com", win32com)
sys.modules.setdefault("win32com.client", win32com_client)
sys.modules.setdefault("pythoncom", types.ModuleType("pythoncom"))
sys.modules.setdefault("pywintypes", types.ModuleType("pywintypes"))

from automas_script_maafw import adapter


class FakeScriptConfig:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], Any] = {
            ("Run", "WeeklyOnceTasks"): '["ExistingWeekly"]',
            ("Run", "MonthlyOnceTasks"): '["ExistingMonthly"]',
        }

    def get(self, group: str, key: str) -> Any:
        return self.values.get((group, key), "")

    async def set(self, group: str, key: str, value: Any) -> None:
        self.values[(group, key)] = value


class MaaFWScriptAdapterTest(unittest.IsolatedAsyncioTestCase):
    def test_extracts_pack_key_from_plugin_config_payload(self) -> None:
        self.assertEqual(
            adapter._extract_project_pack_key(
                {"PluginData": {"Config": {"pack": "m9a"}}}
            ),
            "m9a",
        )
        self.assertEqual(
            adapter._extract_project_pack_key({"Info": {"ProjectPack": "custom"}}),
            "custom",
        )
        self.assertEqual(
            adapter._extract_project_pack_key({}, default_pack_key="m9a"),
            "m9a",
        )

    def test_extracts_period_rules_from_pack_definition(self) -> None:
        rules = adapter._extract_period_rules(
            {
                "periodRules": [
                    {"task": "Psychube", "period": "weekly"},
                    {"task": "SleepDream", "period": "monthly"},
                    {"task": "", "period": "monthly"},
                    {"task": "Daily", "period": "daily"},
                ]
            }
        )

        self.assertEqual(rules, [("Psychube", "weekly"), ("SleepDream", "monthly")])

    async def test_applies_pack_period_rules_without_replacing_user_lists(self) -> None:
        script_config = FakeScriptConfig()

        changed = await adapter._apply_period_rules_to_script_config(
            script_config,  # type: ignore[arg-type]
            [
                ("Psychube", "weekly"),
                ("SleepDream", "monthly"),
                ("ExistingWeekly", "weekly"),
            ],
        )

        self.assertTrue(changed)
        self.assertEqual(
            json.loads(script_config.get("Run", "WeeklyOnceTasks")),
            ["ExistingWeekly", "Psychube"],
        )
        self.assertEqual(
            json.loads(script_config.get("Run", "MonthlyOnceTasks")),
            ["ExistingMonthly", "SleepDream"],
        )


if __name__ == "__main__":
    unittest.main()
