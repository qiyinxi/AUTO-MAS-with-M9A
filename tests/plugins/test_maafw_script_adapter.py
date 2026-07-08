import json
import sys
import types
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SOURCE_PATHS = (
    ROOT_DIR / "plugins/automas_script_maafw/src",
    ROOT_DIR / "plugins/automas_script_maafw_pack_m9a/src",
)
for source_path in SOURCE_PATHS:
    raw_path = str(source_path)
    if raw_path not in sys.path:
        sys.path.insert(0, raw_path)

for module_name in ("win32api", "win32gui", "win32con", "win32process", "win32crypt"):
    sys.modules.setdefault(module_name, types.ModuleType(module_name))
win32com = types.ModuleType("win32com")
win32com_client = types.ModuleType("win32com.client")
win32com.client = win32com_client
sys.modules.setdefault("win32com", win32com)
sys.modules.setdefault("win32com.client", win32com_client)
sys.modules.setdefault("pythoncom", types.ModuleType("pythoncom"))
sys.modules.setdefault("pywintypes", types.ModuleType("pywintypes"))

from automas_script_maafw_pack_m9a.schema import M9A_SCRIPT_GROUPS


def _field_default(group_key: str, field_name: str) -> object:
    for group in M9A_SCRIPT_GROUPS:
        if group.key != group_key:
            continue
        for field in group.fields:
            if field.name == field_name:
                return field.default
    raise AssertionError(f"Missing field {group_key}.{field_name}")


class M9APackSchemaTest(unittest.TestCase):
    def test_m9a_pack_initializes_new_script_defaults(self) -> None:
        self.assertEqual(_field_default("Info", "Name"), "新M9A脚本")
        self.assertEqual(
            json.loads(str(_field_default("Run", "DailyOnceTasks"))),
            ["Psychube"],
        )
        self.assertEqual(json.loads(str(_field_default("Run", "WeeklyOnceTasks"))), [])
        self.assertEqual(
            json.loads(str(_field_default("Run", "MonthlyOnceTasks"))),
            ["SleepDream"],
        )


if __name__ == "__main__":
    unittest.main()
