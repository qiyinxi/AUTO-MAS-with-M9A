import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[2]
INTERFACE_SRC = ROOT_DIR / "plugins/automas_maafw_interface/src"
AGENT_ENV_SRC = ROOT_DIR / "plugins/automas_maafw_agent_env/src"
for source_path in (str(INTERFACE_SRC), str(AGENT_ENV_SRC)):
    if source_path not in sys.path:
        sys.path.insert(0, source_path)

from automas_maafw_agent_env.env import AGENT_ENV_MANIFEST_NAME
from automas_maafw_agent_env.planner import (
    MaaFWAgentEnvError,
    build_maafw_agent_command_plans,
    venv_python_exe,
)
from automas_maafw_agent_env.service import MaaFWAgentEnvService


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class MaaFWAgentEnvPluginTest(unittest.TestCase):
    def test_embedded_agent_uses_isolated_subprocess_plan(self) -> None:
        with TemporaryDirectory() as directory:
            project_path = Path(directory) / "project"
            (project_path / "agent").mkdir(parents=True)
            (project_path / "agent/main.py").write_text("print('agent')", encoding="utf-8")

            plans = build_maafw_agent_command_plans(
                project_path,
                {
                    "child_exec": "{PROJECT_DIR}/python/python.exe",
                    "embedded": True,
                },
                managed_env_root=Path(directory) / "maafw_agent_venvs",
            )

            self.assertEqual(len(plans), 1)
            plan = plans[0]
            self.assertFalse(plan.embedded)
            self.assertEqual(plan.runtimeKind, "isolated_venv")
            self.assertIn("embedded agent", plan.fallbackReason or "")
            self.assertEqual(plan.childArgs, ["-u", str((project_path / "agent/main.py").resolve())])
            self.assertEqual(plan.command[-1], "<socket_id>")
            self.assertEqual(plan.command[0], str(venv_python_exe(plan.isolatedVenvPath or "")))

    def test_project_python_is_classified_without_venv(self) -> None:
        with TemporaryDirectory() as directory:
            project_path = Path(directory) / "project"
            python_path = project_path / "python/python.exe"
            python_path.parent.mkdir(parents=True)
            python_path.write_text("", encoding="utf-8")

            plans = build_maafw_agent_command_plans(
                project_path,
                {"child_exec": "python/python.exe", "child_args": ["-m", "agent"]},
            )

            self.assertEqual(plans[0].runtimeKind, "project_python")
            self.assertEqual(plans[0].executable, str(python_path.resolve()))
            self.assertIsNone(plans[0].isolatedVenvPath)

    def test_rejects_agent_exec_path_escape(self) -> None:
        with TemporaryDirectory() as directory:
            project_path = Path(directory) / "project"
            project_path.mkdir()

            with self.assertRaisesRegex(MaaFWAgentEnvError, "路径越界"):
                build_maafw_agent_command_plans(
                    project_path,
                    {"child_exec": "../outside/python.exe"},
                )

    def test_prepare_env_writes_manifest_and_shim_when_install_is_disabled(self) -> None:
        with TemporaryDirectory() as directory:
            project_path = Path(directory) / "project"
            (project_path / "agent").mkdir(parents=True)
            (project_path / "agent/main.py").write_text("print('agent')", encoding="utf-8")
            _write_json(project_path / "interface.json", {"interface_version": 2})
            (project_path / "requirements.txt").write_text("demo-package==1.0\n", encoding="utf-8")

            service = MaaFWAgentEnvService()
            managed_env_root = Path(directory) / "maafw_agent_venvs"
            plans = service.build_command_plans(
                project_path,
                {"child_exec": "python/python.exe", "embedded": True},
                managed_env_root=managed_env_root,
            )
            venv_path = Path(plans[0].isolatedVenvPath or "")

            completed = type("Completed", (), {"returncode": 0, "stdout": "pip 24", "stderr": ""})
            def run_side_effect(command, **kwargs):
                if "-m" in command and "venv" in command:
                    target = Path(command[-1])
                    python_path = venv_python_exe(target)
                    python_path.parent.mkdir(parents=True)
                    python_path.write_text("", encoding="utf-8")
                    (target / "pyvenv.cfg").write_text("home=test", encoding="utf-8")
                return completed()

            with patch(
                "automas_maafw_agent_env.env.subprocess.run",
                side_effect=run_side_effect,
            ):
                result = service.prepare_env(
                    project_path,
                    {"child_exec": "python/python.exe", "embedded": True},
                    managed_env_root=managed_env_root,
                    install_dependencies=False,
                )

            manifest = json.loads(
                (venv_path / AGENT_ENV_MANIFEST_NAME).read_text(encoding="utf-8")
            )
            self.assertEqual(result.preparedVenvs, [str(venv_path)])
            self.assertEqual(manifest["projectPath"], str(project_path.resolve()))
            self.assertIn("demo-package==1.0", manifest["requirements"])
            self.assertTrue((venv_path / ".auto_mas_shims/sitecustomize.py").is_file())


if __name__ == "__main__":
    unittest.main()
