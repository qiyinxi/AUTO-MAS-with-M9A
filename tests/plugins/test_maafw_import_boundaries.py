import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
PLUGIN_SOURCES = (
    ROOT_DIR / "plugins/automas_maafw_interface/src",
    ROOT_DIR / "plugins/automas_maafw_project_update/src",
    ROOT_DIR / "plugins/automas_maafw_agent_env/src",
    ROOT_DIR / "plugins/automas_maafw_runner/src",
    ROOT_DIR / "plugins/automas_maafw_controller_win32/src",
    ROOT_DIR / "plugins/automas_script_maafw/src",
    ROOT_DIR / "plugins/automas_script_maafw_pack_m9a/src",
)


class MaaFWImportBoundaryTest(unittest.TestCase):
    def test_maafw_discovery_imports_do_not_load_maa_binding(self) -> None:
        env = os.environ.copy()
        python_path = os.pathsep.join(str(path) for path in PLUGIN_SOURCES)
        if env.get("PYTHONPATH"):
            python_path = f"{python_path}{os.pathsep}{env['PYTHONPATH']}"
        env["PYTHONPATH"] = python_path

        script = "\n".join(
            [
                "import importlib",
                "import sys",
                "import types",
                "for name in ('win32api', 'win32gui', 'win32con', 'win32process', 'win32crypt'):",
                "    sys.modules.setdefault(name, types.ModuleType(name))",
                "win32com = types.ModuleType('win32com')",
                "win32com_client = types.ModuleType('win32com.client')",
                "win32com.client = win32com_client",
                "sys.modules.setdefault('win32com', win32com)",
                "sys.modules.setdefault('win32com.client', win32com_client)",
                "sys.modules.setdefault('pythoncom', types.ModuleType('pythoncom'))",
                "sys.modules.setdefault('pywintypes', types.ModuleType('pywintypes'))",
                "importlib.import_module('app.core')",
                "importlib.import_module('automas_script_maafw.adapter')",
                "importlib.import_module('automas_script_maafw.runner_task')",
                "importlib.import_module('automas_script_maafw_pack_m9a.plugin')",
                "import app.task as task_pkg",
                "assert 'MaaFWManager' not in task_pkg.__all__",
                "raise SystemExit(1 if 'maa' in sys.modules else 0)",
            ]
        )

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT_DIR,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=result.stdout + result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
