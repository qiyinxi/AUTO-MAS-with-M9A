from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core import Config
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaFWConfig, MaaFWUserConfig
from app.models.emulator import DeviceBase, DeviceInfo
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase
from app.plugins.pypi_site import get_plugin_import_paths
from app.services import Notify
from app.task.general.tools import execute_script_task
from app.utils import get_logger
from app.utils.constants import UTC4
from automas_maafw_interface.models import MaaFWController, MaaFWInterface
from automas_maafw_interface.service import MaaFWInterfaceService
from automas_maafw_runner.models import (
    MaaFWDeviceConfig,
    MaaFWRunPlan,
    MaaFWRunResult,
    MaaFWSkippedTaskPlan,
)
from automas_maafw_runner.run_plan import MaaFWRunPlanError
from automas_maafw_runner.service import MaaFWRunnerService


logger = get_logger("MaaFW 插件自动代理")

_RUNNING_PROJECT_PATHS: set[str] = set()
_RUNNING_PROJECT_PATHS_LOCK = asyncio.Lock()


def _build_worker_env() -> dict[str, str]:
    """构造 runner worker 子进程环境，确保插件包可被独立解释器导入。

    插件包仅安装在 plugins/pypi/site-packages（主进程通过 addsitedir 加载），
    子进程不会继承该运行时 sys.path 改动，因此需显式通过 PYTHONPATH 传入
    editable 安装的 src 目录与插件 site-packages。
    """
    env = os.environ.copy()
    import_paths = [str(path) for path in get_plugin_import_paths() if path.exists()]
    if not import_paths:
        return env
    extra = os.pathsep.join(import_paths)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{extra}{os.pathsep}{existing}" if existing else extra
    return env


class MaaFWPluginAutoProxyTask(TaskExecuteBase):
    """MaaFW 插件版 AutoProxy 执行器。"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MaaFWConfig,
        user_config: MultipleConfig[MaaFWUserConfig],
        emulator_manager: DeviceBase | None,
        project_update_logs: list[str] | None = None,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.emulator_manager = emulator_manager
        self.project_update_logs = list(project_update_logs or [])
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config = self.user_config[self.cur_user_uid]
        self.project_path = Path(self.script_config.get("Info", "Path")).resolve()
        self.interface_model: MaaFWInterface | None = None
        self.base_run_plan: MaaFWRunPlan | None = None
        self.run_plan: MaaFWRunPlan | None = None
        self.cur_user_log: LogRecord | None = None
        self.check_result = "-"
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        self.run_complete = False
        self.opened_emulator = False
        self.project_lock_key: str | None = None
        self.runner_process: asyncio.subprocess.Process | None = None
        self._cached_adb_address: str | None = None
        self._cached_device_info: DeviceInfo | None = None
        self._cached_adb_path: str | None = None

    async def check(self) -> str:
        proxy_times = (
            self.cur_user_config.get("Data", "ProxyTimes")
            if self.cur_user_config.get("Data", "LastProxyDate") == self.curdate
            else 0
        )
        if (
            self.script_config.get("Run", "ProxyTimesLimit") != 0
            and proxy_times >= self.script_config.get("Run", "ProxyTimesLimit")
        ):
            self.cur_user_item.status = "跳过"
            return "今日代理次数已达上限，跳过该用户"

        try:
            self.interface_model = MaaFWInterfaceService().load(self.project_path)
            self.base_run_plan = self._build_run_plan(self.interface_model)
            self.run_plan = self._filter_period_once_tasks(self.base_run_plan)
        except Exception as exc:
            self.cur_user_item.status = "异常"
            return f"无法构建 MaaFW 运行计划，请检查项目和任务配置: {exc}"

        if not self.run_plan.tasks:
            self.cur_user_item.status = "跳过"
            return "MaaFW 周期任务已在本周或本月完成，跳过本次运行"

        if self.run_plan.controllerType == "Adb":
            emulator_id = self.script_config.get("Emulator", "Id")
            emulator_index = self.script_config.get("Emulator", "Index")
            if emulator_id == "-" or emulator_index in ("", "-"):
                self.cur_user_item.status = "异常"
                return "当前 MaaFW controller 需要 ADB，请在脚本管理页选择模拟器和实例"
        elif self.run_plan.controllerType == "Win32":
            configured_hwnd = (
                self.cur_user_config.get("Device", "HWnd")
                or self.script_config.get("Device", "HWnd")
            )
            if not _optional_int(configured_hwnd):
                try:
                    controller = _find_controller(
                        self.interface_model,
                        self.run_plan.controllerName,
                    )
                    if not _match_controller_windows(controller):
                        self.cur_user_item.status = "异常"
                        return "当前 MaaFW controller 需要 Win32 窗口，请先打开游戏或配置窗口句柄"
                except Exception as exc:
                    self.cur_user_item.status = "异常"
                    return f"扫描 MaaFW Win32 窗口失败: {exc}"

        if not await self._try_enter_project_path():
            self.cur_user_item.status = "跳过"
            return "同一路径 MaaFW 脚本正在运行，已跳过本次启动"

        return "Pass"

    async def prepare(self) -> None:
        start_time = datetime.now()
        self.cur_user_item.log_record[start_time] = self.cur_user_log = LogRecord()
        if self.project_update_logs:
            self.cur_user_log.content.extend(self.project_update_logs)
            self.script_info.log = "".join(self.cur_user_log.content[-80:])

    async def main_task(self) -> None:
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        self.check_result = await self.check()
        if self.check_result != "Pass":
            if self.cur_user_item.status == "异常":
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={
                        "Error": f"用户 {self.cur_user_item.name} 检查未通过: {self.check_result}"
                    },
                )
            self.script_info.log = self.check_result
            return

        await self._mark_run_started()
        await self.prepare()
        self.cur_user_item.status = "运行"
        logger.info(f"开始代理 MaaFW 用户: {self.cur_user_uid}")

        try:
            for index in range(self.script_config.get("Run", "RunTimesLimit")):
                if self.run_complete:
                    break

                self._append_log(
                    f"用户 {self.cur_user_item.name} - 尝试次数: "
                    f"{index + 1}/{self.script_config.get('Run', 'RunTimesLimit')}"
                )
                if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
                    await execute_script_task(
                        Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                        "脚本前任务",
                    )

                try:
                    if self.run_plan is None or self.interface_model is None:
                        raise RuntimeError("MaaFW 运行计划尚未初始化")
                    device_config = await self._build_device_config(
                        self.run_plan,
                        self.interface_model,
                    )
                    result = await self._run_maafw(device_config)
                except Exception as exc:
                    message = f"MaaFW 运行异常: {exc}"
                    self._append_log(message)
                    if self.cur_user_log is not None:
                        self.cur_user_log.status = message
                    await Config.send_websocket_message(
                        id=self.task_info.task_id,
                        type="Info",
                        data={"Error": message},
                    )
                    continue
                finally:
                    if self.cur_user_config.get("Info", "IfScriptAfterTask"):
                        await execute_script_task(
                            Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                            "脚本后任务",
                        )

                await self._mark_period_tasks_completed(result.completedTasks)
                if result.success:
                    self.run_complete = True
                    if self.cur_user_log is not None:
                        self.cur_user_log.status = "Success!"
                    self._append_log("MaaFW 任务完成: " + ", ".join(result.completedTasks))
                else:
                    message = result.errorMessage or "MaaFW 任务失败"
                    if self.cur_user_log is not None:
                        self.cur_user_log.status = message
                    self._append_log(message)
                    self._refresh_run_plan_after_period_update()
                    if self.run_plan is not None and not self.run_plan.tasks:
                        self.run_complete = True
                        self._append_log("MaaFW 剩余周期任务已完成，停止本轮重试")
        finally:
            await self._shutdown_runner()
            await self._close_emulator()
            await self._release_project_path()

    async def final_task(self) -> None:
        await self._shutdown_runner()
        if self.check_result != "Pass":
            await self._release_project_path()
            return

        await self._close_emulator()
        await self._save_user_logs()
        if self.run_complete:
            if (
                self.cur_user_config.get("Data", "ProxyTimes") == 0
                and self.cur_user_config.get("Info", "RemainedDay") != -1
            ):
                await self.cur_user_config.set(
                    "Info",
                    "RemainedDay",
                    self.cur_user_config.get("Info", "RemainedDay") - 1,
                )
            await self.cur_user_config.set(
                "Data",
                "ProxyTimes",
                self.cur_user_config.get("Data", "ProxyTimes") + 1,
            )
            await self.cur_user_config.set("Data", "LastProxyStatus", "成功")
            self.cur_user_item.status = "完成"
            await self._send_success_notify()
        else:
            await self.cur_user_config.set("Data", "LastProxyStatus", "失败")
            if self.cur_user_item.status == "运行":
                self.cur_user_item.status = "异常"

        await self._release_project_path()

    async def on_crash(self, e: Exception) -> None:
        self.cur_user_item.status = "异常"
        logger.exception(f"MaaFW 插件自动代理任务出现异常: {e}")
        try:
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": f"MaaFW 插件自动代理任务出现异常: {e}"},
            )
        except Exception:
            pass
        await self._shutdown_runner()
        await self._close_emulator()
        await self._release_project_path()

    def _build_run_plan(self, interface_model: MaaFWInterface) -> MaaFWRunPlan:
        task_snapshot = _load_json_dict(self.cur_user_config.get("Task", "TaskSnapshot"))
        selected_preset = str(self.cur_user_config.get("Task", "SelectedPreset") or "").strip()
        controller_name = self._select_controller_name(interface_model)
        resource_name = self._select_resource_name(interface_model, controller_name)
        try:
            return MaaFWRunnerService().build_plan(
                self.project_path,
                interface_model,
                controller_name=controller_name,
                resource_name=resource_name,
                selected_preset=selected_preset if selected_preset and not task_snapshot else None,
                task_snapshot=task_snapshot or None,
            )
        except Exception as exc:
            raise MaaFWRunPlanError(str(exc)) from exc

    def _select_controller_name(self, interface_model: MaaFWInterface) -> str | None:
        configured_controller = str(
            self.script_config.get("Info", "Controller")
            or self.cur_user_config.get("Info", "Controller")
            or ""
        ).strip()

        wants_adb = self.script_config.get("Emulator", "Id") != "-"
        if wants_adb:
            if configured_controller:
                controller = _find_controller(interface_model, configured_controller)
                if controller.type == "Adb":
                    return controller.name
            adb_controller = next(
                (controller for controller in interface_model.controller if controller.type == "Adb"),
                None,
            )
            if adb_controller is not None:
                return adb_controller.name
        if configured_controller:
            return configured_controller
        return None

    def _select_resource_name(
        self,
        interface_model: MaaFWInterface,
        controller_name: str | None,
    ) -> str | None:
        configured_resource = str(
            self.script_config.get("Info", "Resource")
            or self.cur_user_config.get("Info", "Resource")
            or ""
        ).strip()
        if configured_resource:
            return configured_resource
        if controller_name is None:
            return None
        for resource in interface_model.resource:
            if not resource.controller or controller_name in resource.controller:
                return resource.name
        return None

    async def _build_device_config(
        self,
        plan: MaaFWRunPlan,
        interface_model: MaaFWInterface,
    ) -> MaaFWDeviceConfig:
        if plan.controllerType == "Adb":
            address, device_info = await self._resolve_adb_address()
            adb_path = await self._resolve_adb_path(address, device_info)
            return MaaFWDeviceConfig(
                type="Adb",
                adbPath=adb_path,
                address=address,
                screencapMethods=int(self.script_config.get("Device", "AdbScreencapMethods")),
                inputMethods=int(self.script_config.get("Device", "AdbInputMethods")),
            )

        if plan.controllerType == "Win32":
            controller = _find_controller(interface_model, plan.controllerName)
            return MaaFWDeviceConfig(
                type="Win32",
                hWnd=self._resolve_window_handle(controller),
                screencapMethod=int(self.script_config.get("Device", "Win32ScreencapMethod") or 0),
                mouseMethod=int(self.script_config.get("Device", "Win32MouseMethod") or 0),
                keyboardMethod=int(self.script_config.get("Device", "Win32KeyboardMethod") or 0),
            )

        raise RuntimeError(f"当前仅支持 Adb/Win32 controller: {plan.controllerType}")

    async def _resolve_adb_address(self) -> tuple[str, DeviceInfo | None]:
        if self._cached_adb_address is not None:
            return self._cached_adb_address, self._cached_device_info
        if self.emulator_manager is None:
            raise RuntimeError("当前 controller 需要 ADB，请在脚本管理页选择模拟器")

        emulator_index = self.script_config.get("Emulator", "Index")
        if emulator_index in ("", "-"):
            raise RuntimeError("当前 controller 需要 ADB，请在脚本管理页选择模拟器实例")

        self._append_log(f"正在启动模拟器: {emulator_index}")
        self.opened_emulator = True
        device_info = await self.emulator_manager.open(emulator_index)
        if Config.get("Function", "IfSilence"):
            with suppress(Exception):
                await self.emulator_manager.setVisible(emulator_index, False)
        if not device_info.adb_address or device_info.adb_address == "Unknown":
            raise RuntimeError("模拟器未返回可用 ADB 地址")

        self._cached_adb_address = device_info.adb_address
        self._cached_device_info = device_info
        self._append_log(f"模拟器启动完成，ADB 地址: {device_info.adb_address}")
        return device_info.adb_address, device_info

    async def _resolve_adb_path(
        self,
        address: str,
        device_info: DeviceInfo | None,
    ) -> str:
        if self._cached_adb_path is not None:
            return self._cached_adb_path
        configured_path = str(self.script_config.get("Device", "AdbPath") or "").strip()
        if configured_path and Path(configured_path).exists():
            self._cached_adb_path = configured_path
            return configured_path

        derived_path = self._derive_adb_path_from_emulator_config()
        if derived_path is not None and derived_path.exists():
            self._cached_adb_path = str(derived_path)
            return self._cached_adb_path

        title = f"（{device_info.title}）" if device_info else ""
        raise RuntimeError(f"无法找到 ADB 路径{title}，请检查脚本管理页的模拟器配置")

    def _derive_adb_path_from_emulator_config(self) -> Path | None:
        emulator_id = self.script_config.get("Emulator", "Id")
        if emulator_id == "-":
            return None
        with suppress(Exception):
            emulator_config = Config.EmulatorConfig[uuid.UUID(emulator_id)]
            emulator_path = Path(emulator_config.get("Info", "Path"))
            return emulator_path.parent / "adb.exe"
        return None

    def _resolve_window_handle(self, controller: MaaFWController) -> int:
        configured_hwnd = (
            self.cur_user_config.get("Device", "HWnd")
            or self.script_config.get("Device", "HWnd")
        )
        parsed_hwnd = _optional_int(configured_hwnd)
        if parsed_hwnd:
            return parsed_hwnd
        matches = _match_controller_windows(controller)
        if not matches:
            raise RuntimeError("未找到匹配 MaaFW Win32 controller 的窗口")
        return int(matches[0].hWnd)

    async def _run_maafw(self, device_config: MaaFWDeviceConfig) -> MaaFWRunResult:
        if self.run_plan is None:
            raise RuntimeError("MaaFW 运行计划尚未初始化")
        timeout = self.script_config.get("Run", "RunTimeLimit") * 60
        try:
            return await asyncio.wait_for(
                self._run_maafw_worker(device_config),
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            await self._terminate_runner_process()
            raise RuntimeError("MaaFW 任务运行超时") from exc
        except asyncio.CancelledError:
            await self._terminate_runner_process()
            raise

    async def _run_maafw_worker(
        self,
        device_config: MaaFWDeviceConfig,
    ) -> MaaFWRunResult:
        if self.run_plan is None:
            raise RuntimeError("MaaFW 运行计划尚未初始化")

        service = MaaFWRunnerService()
        payload = service.create_job_payload(self.run_plan, device_config)
        work_dir = Path.cwd() / "runtime" / "maafw_runner_jobs"
        job_path = await asyncio.to_thread(service.write_job_file, payload, work_dir)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "automas_maafw_runner.worker",
            str(job_path),
            cwd=str(Path.cwd()),
            env=_build_worker_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self.runner_process = process
        result_payload: dict[str, Any] | None = None
        try:
            if process.stdout is not None:
                async for raw_line in process.stdout:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        self._append_log(line)
                        continue

                    event_type = event.get("type")
                    if event_type == "log":
                        self._append_log(str(event.get("message") or ""))
                    elif event_type == "result" and isinstance(event.get("data"), dict):
                        result_payload = event["data"]
                    elif event_type == "error":
                        self._append_log(str(event.get("message") or ""))
            returncode = await process.wait()
        finally:
            if process.returncode is None:
                await self._terminate_runner_process()
            elif self.runner_process is process:
                self.runner_process = None
            with suppress(Exception):
                job_path.unlink()

        if result_payload is not None:
            return MaaFWRunResult.model_validate(result_payload)
        raise RuntimeError(f"MaaFW runner worker exited without result: {returncode}")

    async def _shutdown_runner(self) -> None:
        await self._terminate_runner_process()

    async def _terminate_runner_process(self) -> None:
        process = self.runner_process
        self.runner_process = None
        if process is None or process.returncode is not None:
            return

        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
        except ProcessLookupError:
            return
        except Exception as exc:
            logger.warning(f"MaaFW runner worker 清理失败: {exc}")

    def _filter_period_once_tasks(self, plan: MaaFWRunPlan) -> MaaFWRunPlan:
        daily_tasks = set(_load_json_list(self.script_config.get("Run", "DailyOnceTasks")))
        weekly_tasks = set(_load_json_list(self.script_config.get("Run", "WeeklyOnceTasks")))
        monthly_tasks = set(_load_json_list(self.script_config.get("Run", "MonthlyOnceTasks")))
        if not daily_tasks and not weekly_tasks and not monthly_tasks:
            return plan

        daily_key, weekly_key, monthly_key = _current_period_keys()
        records = self._load_period_task_records()
        runnable_tasks = []
        skipped_tasks = []
        for task in plan.tasks:
            daily_done = (
                task.name in daily_tasks and records["daily"].get(task.name) == daily_key
            )
            weekly_done = task.name in weekly_tasks and records["weekly"].get(task.name) == weekly_key
            monthly_done = (
                task.name in monthly_tasks and records["monthly"].get(task.name) == monthly_key
            )
            if daily_done or weekly_done or monthly_done:
                if daily_done:
                    reason = "今日已正常完成"
                elif monthly_done:
                    reason = "本月已正常完成"
                else:
                    reason = "本周已正常完成"
                skipped_tasks.append(
                    MaaFWSkippedTaskPlan(
                        name=task.name,
                        label=task.label,
                        entry=task.entry,
                        reason=reason,
                    )
                )
                continue
            runnable_tasks.append(task)
        return plan.model_copy(
            update={
                "tasks": runnable_tasks,
                "skippedTasks": [*plan.skippedTasks, *skipped_tasks],
            },
        )

    def _refresh_run_plan_after_period_update(self) -> None:
        if self.base_run_plan is not None:
            self.run_plan = self._filter_period_once_tasks(self.base_run_plan)

    def _load_period_task_records(self) -> dict[str, dict[str, str]]:
        raw_records = _load_json_dict(self.cur_user_config.get("Data", "PeriodTaskRecords"))
        records: dict[str, dict[str, str]] = {"daily": {}, "weekly": {}, "monthly": {}}
        for period in records:
            raw_period_records = raw_records.get(period, {})
            if isinstance(raw_period_records, dict):
                records[period] = {
                    str(task_name): str(period_key)
                    for task_name, period_key in raw_period_records.items()
                }
        return records

    async def _mark_period_tasks_completed(self, completed_tasks: list[str]) -> None:
        if not completed_tasks:
            return
        daily_tasks = set(_load_json_list(self.script_config.get("Run", "DailyOnceTasks")))
        weekly_tasks = set(_load_json_list(self.script_config.get("Run", "WeeklyOnceTasks")))
        monthly_tasks = set(_load_json_list(self.script_config.get("Run", "MonthlyOnceTasks")))
        if not daily_tasks and not weekly_tasks and not monthly_tasks:
            return

        daily_key, weekly_key, monthly_key = _current_period_keys()
        records = self._load_period_task_records()
        changed = False
        for task_name in set(completed_tasks).intersection(daily_tasks):
            if records["daily"].get(task_name) != daily_key:
                records["daily"][task_name] = daily_key
                changed = True
        for task_name in set(completed_tasks).intersection(weekly_tasks):
            if records["weekly"].get(task_name) != weekly_key:
                records["weekly"][task_name] = weekly_key
                changed = True
        for task_name in set(completed_tasks).intersection(monthly_tasks):
            if records["monthly"].get(task_name) != monthly_key:
                records["monthly"][task_name] = monthly_key
                changed = True
        if changed:
            await self.cur_user_config.set(
                "Data",
                "PeriodTaskRecords",
                json.dumps(records, ensure_ascii=False),
            )

    async def _mark_run_started(self) -> None:
        if self.cur_user_config.get("Data", "LastProxyDate") != self.curdate:
            await self.cur_user_config.set("Data", "LastProxyDate", self.curdate)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)
        await self.cur_user_config.set("Data", "LastProxyStatus", "运行中")

    async def _close_emulator(self) -> None:
        if not self.opened_emulator or self.emulator_manager is None:
            return
        try:
            await self.emulator_manager.close(self.script_config.get("Emulator", "Index"))
        except Exception as exc:
            logger.warning(f"MaaFW 插件清理模拟器失败: {exc}")
        finally:
            self.opened_emulator = False

    async def _try_enter_project_path(self) -> bool:
        project_lock_key = _normalize_project_path(self.project_path)
        async with _RUNNING_PROJECT_PATHS_LOCK:
            if project_lock_key in _RUNNING_PROJECT_PATHS:
                return False
            _RUNNING_PROJECT_PATHS.add(project_lock_key)
            self.project_lock_key = project_lock_key
            return True

    async def _release_project_path(self) -> None:
        if self.project_lock_key is None:
            return
        async with _RUNNING_PROJECT_PATHS_LOCK:
            _RUNNING_PROJECT_PATHS.discard(self.project_lock_key)
        self.project_lock_key = None

    async def _save_user_logs(self) -> None:
        for timestamp, log_item in self.cur_user_item.log_record.items():
            dt = timestamp.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = (
                Path.cwd()
                / f"history/{dt.strftime('%Y-%m-%d')}/{self.cur_user_item.name}/{dt.strftime('%H-%M-%S')}.log"
            )
            if not log_item.content:
                log_item.content = ["未捕获到任何 MaaFW 运行日志"]
            if log_item.status == "未开始监看日志":
                log_item.status = "MaaFW 任务被中止"
            await Config.save_general_log(log_path, log_item.content, log_item.status)

    async def _send_success_notify(self) -> None:
        try:
            await Notify.push_plyer(
                "MaaFW 自动代理任务完成",
                f"已完成用户 {self.cur_user_item.name} 的 MaaFW 自动代理任务",
                f"已完成 {self.cur_user_item.name} 的 MaaFW 自动代理任务",
                3,
            )
        except Exception as exc:
            logger.warning(f"MaaFW 插件用户通知发送失败: {exc}")

    def _append_log(self, message: str) -> None:
        logger.info(message)
        if self.cur_user_log is not None:
            self.cur_user_log.content.append(_format_user_log_line(message))
            self.script_info.log = "".join(self.cur_user_log.content[-80:])
        else:
            self.script_info.log = str(message)


def _find_controller(interface_model: MaaFWInterface, controller_name: str) -> MaaFWController:
    controller = next(
        (item for item in interface_model.controller if item.name == controller_name),
        None,
    )
    if controller is None:
        raise RuntimeError(f"未找到 controller: {controller_name}")
    return controller


def _match_controller_windows(controller: MaaFWController) -> list[Any]:
    try:
        from app.plugins import PluginManager

        service = PluginManager.service.get("maafw.controller.win32")
    except Exception:
        service = None
    if service is None:
        from automas_maafw_controller_win32.service import MaaFWWin32ControllerService

        service = MaaFWWin32ControllerService()
    return list(service.match_controller_windows(controller))


def _optional_int(value: Any) -> int | None:
    if value in (None, "", "-"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        with suppress(json.JSONDecodeError):
            data = json.loads(value)
            if isinstance(data, dict):
                return data
    return {}


def _load_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        with suppress(json.JSONDecodeError):
            data = json.loads(value)
            if isinstance(data, list):
                return [str(item) for item in data if str(item).strip()]
    return []


def _current_period_keys(now: datetime | None = None) -> tuple[str, str, str]:
    current = now or datetime.now(tz=UTC4)
    iso_year, iso_week, _ = current.isocalendar()
    return (
        current.strftime("%Y-%m-%d"),
        f"{iso_year}-W{iso_week:02d}",
        current.strftime("%Y-%m"),
    )


def _normalize_project_path(path: Path) -> str:
    return str(path.resolve()).casefold()


def _format_user_log_line(message: str) -> str:
    timestamp = datetime.now().astimezone().strftime("%H:%M:%S")
    lines = str(message).splitlines() or [""]
    return "".join(f"[{timestamp}] {line}\n" for line in lines)
