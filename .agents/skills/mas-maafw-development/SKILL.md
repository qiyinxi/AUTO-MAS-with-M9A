---
name: mas-maafw-development
description: Use when working on AUTO-MAS MaaFW/MFW integration, including app/task/MaaFW, MaaFW config/schema/API/frontend surfaces, ProjectInterface parsing, run plan construction, task option/preset handling, MaaFW agent Python environments, controller/resource selection, or MaaFw package/import issues.
---

# MAS MaaFW Development

## Objective
Keep MaaFW development anchored to the current AUTO-MAS implementation so future agents do not rediscover the same file map, runtime model, and package naming traps.

## Hard Facts
1. `requirements.txt` uses distribution package `maafw==5.8.1` / `MaaFw`.
2. The Python import module is `maa`, not `maafw`; use `import maa`, `from maa.controller import ...`, `from maa.resource import Resource`, etc.
3. `importlib.metadata.version("maafw")` is valid for distribution metadata; it does not imply `import maafw` is valid.
4. Legacy MaaFW agent code may expect `maa.resource.resource`; the current runner writes a `sitecustomize.py` shim that maps it to `maa.agent.agent_server.AgentServer` inside isolated agent venvs.

## Current Surface Map
Backend MaaFW implementation lives in `app/task/MaaFW/`:

1. `manager.py`: `MaaFWManager`, task lifecycle, script/user config locking, auto-update before run, dispatch to `AutoProxy`.
2. `AutoProxy.py`: per-user execution, period-once task filtering, controller/resource selection, emulator/game startup, `MaaFWRunner` orchestration.
3. `runner.py`: MaaFW library client mode, resource/controller/tasker setup, agent process startup, isolated agent venv preparation, pip health repair, compatibility shim, task execution logs.
4. `run_plan.py`: convert ProjectInterface + selected preset/snapshot into `MaaFWRunPlan`; choose controller/resource, resolve resource paths, build PI env, classify agent `child_exec`.
5. `task_config.py`: normalize task order, checked state, presets, option defaults, and execution payloads.
6. `interface_loader.py`: load `interface.json` / `interface.jsonc`, merge `import`, expand `scan_select`, validate references, cache in memory and `data/cache/maafw_interface_loader`.
7. `interface_models.py`: Pydantic model contract for MaaFW ProjectInterface.
8. `interface_preview.py`: API/UI preview data, i18n resolution, description file loading, preset snapshots.
9. `pipeline_override.py`: convert selected task options into MaaFW pipeline override payloads.
10. `project_updater.py`: MirrorChyan/GitHub update detection and zip apply before resources load.
11. `window_service.py`: Win32/Gamepad window discovery and handle resolution.
12. `control_capabilities.py`: ADB emulator extra capability discovery for MuMu/LDPlayer style integrations.

Cross-module surfaces:

1. `app/api/scripts.py`: MaaFW endpoints for `/maafw/interface/preview`, `/maafw/agent-env/prepare`, `/maafw/asset`, `/maafw/windows/preview`.
2. `app/models/config.py`: `MaaFWConfig`, `MaaFWUserConfig`, config registration in global collections and `CONFIG_BOOK`.
3. `app/models/schema.py`: MaaFW config, preview, agent env, and window preview API schemas.
4. `app/core/task_manager.py`: maps `MaaFWConfig` to `MaaFWManager`.
5. `frontend/src/composables/useMaaFWApi.ts`: frontend MaaFW API normalization and calls.
6. `frontend/src/views/EditView/Script/MaaFWScriptEdit.vue`: project/script-level UI.
7. `frontend/src/views/EditView/User/MaaFWUserEdit.vue`, `MaaFWTaskOptionEditor.vue`, `MaaFWDescriptionView.vue`: user task/preset/options UI.
8. Generated frontend API files under `frontend/src/api/**` must not be hand edited; regenerate from backend OpenAPI when schema changes.

## Runtime Model
1. MaaFW projects are PI v2.5-style ProjectInterface projects. AUTO-MAS reads `interface.json` / `interface.jsonc` and does not implement recognition nodes itself.
2. Run flow is `MaaFWManager` -> `AutoProxyTask` -> `build_maafw_run_plan` -> `MaaFWRunner`.
3. Controller types currently handled by runtime are `Adb`, `Win32`, `Gamepad`, and `PlayCover`.
4. Resource paths and agent executable paths must stay within the MaaFW project root after `{PROJECT_DIR}` replacement.
5. Task selection should prefer normalized snapshots/presets from `task_config.py`; do not pass raw UI payloads straight into runner logic.
6. MFW GUI behavior is per-task tolerant: an individual `post_task` failure is logged and later selected tasks continue. AUTO-MAS should aggregate per-task failures in `MaaFWRunResult` instead of aborting the whole run plan on the first MaaFW task failure; initialization, controller/resource, agent startup, stop, and timeout failures still abort the run.
7. Weekly/monthly once behavior is script-level config (`Run.WeeklyOnceTasks`, `Run.MonthlyOnceTasks`) plus user data record `Data.PeriodTaskRecords`.

## Agent Python Environment
1. Do not run project agents in AUTO-MAS's main Python environment unless the project explicitly provides a working Python or binary.
2. `run_plan.py` classifies `child_exec` as `project_python`, `project_binary`, `isolated_venv`, or `external`.
3. Missing bundled project Python paths like `python/python.exe` fall back to a per-project isolated venv under `config/maafw_agent_venvs/maafw_venv_<hash>`.
4. `runner.py` installs the MaaFW project's own `requirements.txt` into isolated venvs and appends `json-with-comments` if absent.
5. The agent process environment strips `VIRTUAL_ENV`, `PYTHONHOME`, `PYTHONUSERBASE`, `PIP_TARGET`, `PIP_PREFIX`, and `PIP_USER`.
6. For isolated venv agent runs, `PYTHONPATH` must include the compatibility shim directory before the MaaFW project root.
7. Keep `Library` in client mode in AUTO-MAS; accidental agent-server mode can poison the process.
8. On Windows, force `PYTHONIOENCODING=utf-8` for MaaFW runner workers and agent subprocesses, and keep worker stdout/stderr configured as UTF-8. Otherwise JSONL logs may parse while Chinese payload text becomes `��` because pipes default to the system ANSI code page.

## Change Workflow
1. Start by reading nearby MaaFW files instead of copying MaaEnd/M9A/SRC behavior blindly.
2. For backend-only MaaFW runtime changes, combine this skill with `mas-code-standards`, `mas-module-boundary`, and `mas-function-design` as needed.
3. For schema/API changes, also use `mas-data-model`, `mas-schema-naming`, and `mas-api-contract`; regenerate frontend API clients rather than editing generated files.
4. For `frontend/` or Vue changes, also use `mas-frontend-standards`; for UI/layout/control behavior, add `mas-frontend-ui`.
5. Keep compatibility edits local to MaaFW registration points and runtime boundaries; do not refactor unrelated script types.
6. If user-visible MaaFW behavior changes, consider whether `res/version.json` needs a next-version entry.

## Verification
Use the workspace `.venv` when available:

```powershell
.\.venv\Scripts\python.exe -c "import maa; print('maa import ok')"
.\.venv\Scripts\python.exe -c "import ast, pathlib; ast.parse(pathlib.Path('app/task/MaaFW/runner.py').read_text(encoding='utf-8'))"
.\.venv\Scripts\python.exe -m pip check
```

For touched backend modules, run a syntax parse on the specific files if full tests are not practical. If Codex sandbox cannot execute `python.exe`, request escalation and explain that the Python executable lives outside the workspace sandbox.

## Avoid
1. Do not write `import maafw`; use `import maa`.
2. Do not hand edit generated OpenAPI frontend files.
3. Do not put runtime project data, `runtime/`, cache contents, or generated isolated venvs into commits.
4. Do not collapse MaaFW agent isolation into AUTO-MAS `.venv`.
5. Do not bypass `interface_loader.py` validation for imported interface fragments, `scan_select`, path traversal, or duplicate task/option/preset names.
6. Do not treat `MaaFW` as the same architecture as `MaaEnd`/MXU or `M9A`/MFAA without checking the actual ProjectInterface and runtime path.
