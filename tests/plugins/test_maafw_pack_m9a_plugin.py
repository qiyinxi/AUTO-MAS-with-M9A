import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
PACK_SRC = ROOT_DIR / "plugins/automas_script_maafw_pack_m9a/src"
SCRIPT_MAAFW_SRC = ROOT_DIR / "plugins/automas_script_maafw/src"
INTERFACE_SRC = ROOT_DIR / "plugins/automas_maafw_interface/src"
UPDATE_SRC = ROOT_DIR / "plugins/automas_maafw_project_update/src"
for source_path in (str(PACK_SRC), str(SCRIPT_MAAFW_SRC), str(INTERFACE_SRC), str(UPDATE_SRC)):
    if source_path not in sys.path:
        sys.path.insert(0, source_path)

from automas_script_maafw_pack_m9a.plugin import Plugin
from automas_script_maafw_pack_m9a.service import M9APackService


class M9APackPluginTest(unittest.TestCase):
    def test_plugin_registers_m9a_script_type_with_maafw_hooks(self) -> None:
        plugin = Plugin(ctx=object())  # type: ignore[arg-type]
        adapters = list(plugin.build_script_adapters())

        self.assertEqual(len(adapters), 1)
        definition = adapters[0]
        self.assertEqual(definition.type_key, "M9A")
        self.assertEqual(definition.metadata["framework"], "maafw")
        self.assertEqual(definition.metadata["project_pack"], "m9a")
        self.assertTrue(definition.metadata["m9a_standalone"])

    def test_definition_declares_only_pack_rules_without_defaults(self) -> None:
        definition = M9APackService().get_definition()
        payload = definition.model_dump(mode="json")

        self.assertEqual(definition.key, "m9a")
        self.assertEqual(
            [(rule.task, rule.period) for rule in definition.periodRules],
            [("Psychube", "weekly"), ("SleepDream", "monthly")],
        )
        for forbidden_key in (
            "projectSource",
            "defaultProject",
            "defaultController",
            "defaultResource",
            "defaultPreset",
            "defaultTaskQueue",
            "dailyTemplate",
            "weeklyTemplate",
            "monthlyTemplate",
        ):
            self.assertNotIn(forbidden_key, payload)

    def test_translates_runner_result_for_m9a_notification(self) -> None:
        content = M9APackService().translate_notification(
            {
                "success": False,
                "completedTasks": ["Daily"],
                "failedTask": "SleepDream",
                "errorMessage": "node failed",
            },
            user_name="Alice",
            started_at="2026-07-07 10:00:00",
            ended_at="2026-07-07 10:05:00",
        )

        self.assertEqual(content.title, "Alice 的 M9A 任务未完成")
        self.assertIn("已完成任务: Daily", content.text)
        self.assertIn("失败任务: SleepDream", content.text)
        self.assertIn("失败原因: node failed", content.text)

    def test_migration_draft_is_create_only_and_keeps_legacy_payload(self) -> None:
        draft = M9APackService().create_migration_draft(
            {
                "Info": {"Path": "D:/M9A"},
                "Run": {
                    "IfAutoUpdateAfterQueue": True,
                    "WeeklyOnceTasks": ["Psychube"],
                },
            },
            [
                {
                    "Info": {"Name": "Main"},
                    "Task": {"Queue": [{"name": "Daily"}]},
                    "Notify": {"Enabled": True},
                }
            ],
            script_name="M9A Migrated",
        )

        self.assertEqual(draft.script["Info"]["Name"], "M9A Migrated")
        self.assertEqual(draft.script["Meta"]["PluginTypeKey"], "M9A")
        self.assertEqual(draft.script["PluginData"]["Config"]["pack"], "m9a")
        self.assertEqual(
            draft.script["PluginData"]["Config"]["legacy"]["path"],
            "D:/M9A",
        )
        self.assertEqual(draft.users[0]["Info"]["Name"], "Main")
        self.assertEqual(draft.users[0]["Meta"]["PluginTypeKey"], "M9A")
        self.assertTrue(draft.users[0]["PluginData"]["Config"]["legacy"]["notifyEnabled"])
        self.assertTrue(any("不覆盖旧 M9A 配置" in item for item in draft.warnings))


if __name__ == "__main__":
    unittest.main()
