import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[2]
INTERFACE_SRC = ROOT_DIR / "plugins/automas_maafw_interface/src"
AGENT_ENV_SRC = ROOT_DIR / "plugins/automas_maafw_agent_env/src"
RUNNER_SRC = ROOT_DIR / "plugins/automas_maafw_runner/src"
for source_path in (str(INTERFACE_SRC), str(AGENT_ENV_SRC), str(RUNNER_SRC)):
    if source_path not in sys.path:
        sys.path.insert(0, source_path)

from automas_maafw_interface.models import MaaFWInterface
from automas_maafw_runner.models import MaaFWDeviceConfig, MaaFWRunResult
from automas_maafw_runner.service import MaaFWRunnerService


def _build_interface() -> MaaFWInterface:
    return MaaFWInterface.model_validate(
        {
            "interface_version": 2,
            "name": "sample-runner",
            "version": "1.0.0",
            "controller": [
                {
                    "name": "adb",
                    "type": "Adb",
                    "attach_resource_path": ["resource/attached"],
                }
            ],
            "resource": [
                {"name": "default", "path": ["resource/base"], "controller": ["adb"]}
            ],
            "option": {
                "mode": {
                    "type": "select",
                    "default_case": "normal",
                    "cases": [
                        {
                            "name": "normal",
                            "pipeline_override": {"A": {"value": 1}},
                        },
                        {
                            "name": "hard",
                            "pipeline_override": {"A": {"value": 2}},
                        },
                    ],
                }
            },
            "task": [
                {
                    "name": "Daily",
                    "entry": "DailyEntry",
                    "default_check": True,
                    "option": ["mode"],
                    "pipeline_override": {"Root": {"enabled": True}},
                },
                {
                    "name": "PCOnly",
                    "entry": "PCEntry",
                    "default_check": True,
                    "controller": ["win32"],
                },
            ],
        }
    )


class MaaFWRunnerPluginTest(unittest.TestCase):
    def test_build_plan_filters_tasks_and_builds_pipeline_override(self) -> None:
        with TemporaryDirectory() as directory:
            project_path = Path(directory)
            (project_path / "resource/base").mkdir(parents=True)
            (project_path / "resource/attached").mkdir(parents=True)

            service = MaaFWRunnerService()
            plan = service.build_plan(
                project_path,
                _build_interface(),
                controller_name="adb",
                resource_name="default",
                task_names=["Daily", "PCOnly"],
                task_options={"Daily": {"mode": "hard"}},
            )

            self.assertEqual(plan.projectName, "sample-runner")
            self.assertEqual(plan.controllerName, "adb")
            self.assertEqual(plan.resourceName, "default")
            self.assertEqual([task.name for task in plan.tasks], ["Daily"])
            self.assertEqual(plan.tasks[0].pipelineOverride["A"]["value"], 2)
            self.assertTrue(plan.tasks[0].pipelineOverride["Root"]["enabled"])
            self.assertEqual([item.name for item in plan.skippedTasks], ["PCOnly"])
            self.assertTrue(plan.resource.paths[0].isDir)
            self.assertTrue(plan.resource.attachedPaths[0].isDir)

    def test_create_job_file_and_parse_worker_result(self) -> None:
        with TemporaryDirectory() as directory:
            project_path = Path(directory) / "project"
            (project_path / "resource/base").mkdir(parents=True)
            (project_path / "resource/attached").mkdir(parents=True)

            service = MaaFWRunnerService()
            plan = service.build_plan(
                project_path,
                _build_interface(),
                task_names=["Daily"],
                task_options={},
            )
            payload = service.create_job_payload(
                plan,
                MaaFWDeviceConfig(type="Adb", address="127.0.0.1:5555"),
            )

            result_data = MaaFWRunResult(
                success=True,
                projectName="sample-runner",
                controllerName="adb",
                resourceName="default",
                completedTasks=["Daily"],
            ).model_dump(mode="json")

            class FakeProcess:
                stdout = [
                    json.dumps({"type": "log", "message": "running"}),
                    json.dumps({"type": "result", "data": result_data}),
                ]
                returncode = 0

                def wait(self, timeout=None):
                    return 0

                def poll(self):
                    return 0

                def terminate(self):
                    return None

            logs: list[str] = []
            with patch(
                "automas_maafw_runner.service.subprocess.Popen",
                return_value=FakeProcess(),
            ):
                result = service.run_worker(
                    payload,
                    work_dir=Path(directory) / "work",
                    worker_command=["fake-worker"],
                    send_log=logs.append,
                )

            job_payload = json.loads(
                (Path(directory) / "work/maafw-runner-job.json").read_text(encoding="utf-8")
            )
            self.assertEqual(job_payload["plan"]["projectName"], "sample-runner")
            self.assertEqual(logs, ["running"])
            self.assertTrue(result.success)
            self.assertEqual(result.completedTasks, ["Daily"])


if __name__ == "__main__":
    unittest.main()
