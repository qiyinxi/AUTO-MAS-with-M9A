#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""Emulator 2.0 的服务层：搜索、增删路径、合并设备列表、四项设置。

版本探测只在**添加路径时**做一次并持久化。``get_status()`` 每次轮询都会重建管理器，
把探测放进构造函数会变成每轮一次子进程。
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from app.utils import get_logger

from .detect import DetectResult, probe_install_path
from .facade import DeviceUnavailableError, Emulator2Manager, dump_paths
from .guard import capture, dump_baselines
from .phone import (
    PENDING_PREFIX,
    PHONE_SCRIPT_TYPES,
    PHONE_TYPE,
    PhoneManager,
    load_ignored,
    normalize_address,
    phone_unsupported_message,
)
from .settings import SettingsConflictError, validate_changes
from .slots import PathRecord, SlotTable, make_path_id

logger = get_logger("Emulator2 服务")


def readable_error(error: BaseException) -> str:
    """把异常翻译成能给用户看的一句话。

    界面上不该出现 ``ValueError: badly formed hexadecimal UUID string`` 这种东西。
    认得出的失败给中文原因；认不出的才退回类名加消息，好歹还能报 issue。
    """
    if isinstance(error, DeviceUnavailableError):
        return str(error)
    if isinstance(error, SettingsConflictError):
        return "配置在编辑期间被改动，请刷新后重试"
    if isinstance(error, ValueError):
        return str(error)
    if isinstance(error, KeyError):
        return f"找不到对象: {error.args[0] if error.args else error}"
    if type(error) is RuntimeError:
        # 我们自己抛的 RuntimeError 消息本来就是写给用户看的中文
        # （「实例未关闭，无法删除」之类），不该再被套上类名前缀
        return str(error)
    return f"{type(error).__name__}: {error}"


#: 脚本配置里两套模拟器绑定字段命名。
#: ``Config.del_emulator()`` 只处理了其中一部分, 反查受影响脚本时不能照抄它。
_BINDING_FIELDS = (
    ("Emulator", "Id", "Index"),
    ("Game", "EmulatorId", "EmulatorIndex"),
)


@dataclass
class SearchItem:
    """一条搜索结果。``reason`` 是枚举, 文案由前端按枚举取。"""

    type: str
    version: str
    install_path: str
    alias: str
    supported: bool
    reason: str
    instance_count: int | None = None

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "version": self.version,
            "installPath": self.install_path,
            "alias": self.alias,
            "supported": self.supported,
            "reason": self.reason,
            "instanceCount": self.instance_count,
        }


@dataclass
class AffectedScript:
    """一个绑定了某设备号的脚本。"""

    script_id: str
    name: str
    slot: str
    running: bool

    def to_dict(self) -> dict:
        return {
            "scriptId": self.script_id,
            "name": self.name,
            "slot": self.slot,
            "running": self.running,
        }


def _emulator_config(emulator_id: str):
    from app.core import Config

    return Config.EmulatorConfig[uuid.UUID(emulator_id)]


async def _save(emulator_id: str, paths: list[PathRecord], slots: SlotTable) -> None:
    from app.core import Config

    await Config.update_emulator(
        emulator_id,
        {"Info": {"Paths": dump_paths(paths), "Slots": slots.to_json()}},
    )


async def _save_baselines(
    emulator_id: str, baselines: dict[str, dict[str, int]]
) -> None:
    from app.core import Config

    await Config.update_emulator(
        emulator_id, {"Info": {"Baselines": dump_baselines(baselines)}}
    )


async def capture_baselines(emulator_id: str) -> dict:
    """把当前所有设备的设置记成守卫基准。开启守卫时调一次。

    只记用户显式设过的字段——见 :func:`.guard.capture`。
    """
    manager = await build_manager(emulator_id)

    baselines: dict[str, dict[str, int]] = {}
    for record in manager.slots.records:
        if record.state != "active" or _is_phone_slot(manager, record):
            continue
        try:
            settings = await manager.read_settings(record.slot)
        except Exception as e:  # noqa: BLE001 - 单台读不出不该拖垮整批
            logger.warning(f"读取设备 #{record.slot} 设置失败，跳过基准: {e}")
            continue
        fields = capture(settings)
        if fields:
            baselines[record.slot] = fields

    await _save_baselines(emulator_id, baselines)
    return {
        "slots": sorted(baselines, key=lambda x: int(x) if x.isdecimal() else 0),
        "count": len(baselines),
    }


async def _record_baseline(emulator_id: str, slot: str, applied: dict) -> None:
    """用户刚保存的设置就是新的基准——否则守卫会把他刚改的值又还原回去。"""
    manager = await build_manager(emulator_id)
    if not manager.config.get("Info", "ConfigGuard"):
        return
    baselines = dict(manager.baselines)
    merged = dict(baselines.get(str(slot), {}))
    merged.update({k: int(v) for k, v in applied.items()})
    baselines[str(slot)] = merged
    await _save_baselines(emulator_id, baselines)


async def build_manager(emulator_id: str) -> Emulator2Manager:
    """按配置 id 构造门面。"""
    from app.models.config import EmulatorConfig

    config = EmulatorConfig()
    await config.load(await _emulator_config(emulator_id).toDict())
    return Emulator2Manager(config)


def find_affected_scripts(emulator_id: str, slots: list[str]) -> list[AffectedScript]:
    """反查哪些脚本绑在这些设备号上。

    必须同时覆盖两套字段命名——``Emulator.Id/Index``（MAA、SRC、M9A、MaaFW）与
    ``Game.EmulatorId/EmulatorIndex``（MaaEnd、通用脚本）。运行中判据用 ``is_locked``。
    """
    from app.core import Config

    wanted = {str(slot) for slot in slots}
    affected: list[AffectedScript] = []
    for script_id, script in Config.ScriptConfig.items():
        for group, id_field, index_field in _BINDING_FIELDS:
            try:
                bound_id = script.get(group, id_field)
                bound_index = script.get(group, index_field)
            except Exception:  # noqa: BLE001 - 脚本类型没有这组字段就跳过
                continue
            if str(bound_id) != str(emulator_id):
                continue
            if str(bound_index) not in wanted:
                continue
            affected.append(
                AffectedScript(
                    script_id=str(script_id),
                    name=str(script.get("Info", "Name")),
                    slot=str(bound_index),
                    running=bool(getattr(script, "is_locked", False)),
                )
            )
            break
    return affected


def _is_phone_slot(manager: Emulator2Manager, record) -> bool:
    """这个设备号是不是一台真机。真机没有模拟器设置，批量设置、稳定模式、守卫一律跳过它。"""
    path = manager.path_of(record.path_id)
    return path is not None and path.type == PHONE_TYPE


def script_type_of(script: Any) -> str:
    """脚本配置对象 → 脚本类型（``CLASS_BOOK`` 的键）。认不出返回类名。"""
    from app.models.config import CLASS_BOOK

    class_name = type(script).__name__
    for key, cls in CLASS_BOOK.items():
        if cls.__name__ == class_name:
            return key
    return class_name


async def is_phone_device(emulator_id: Any, index: Any) -> bool:
    """这个设备号是不是真机。不是 Emulator 2.0 配置、设备号无效都返回 ``False``。"""
    if str(emulator_id) in ("", "-", "None") or str(index) in ("", "-", "None"):
        return False
    try:
        manager = await build_manager(str(emulator_id))
        path, _ = manager.resolve_slot(str(index))
    except Exception:  # noqa: BLE001 - 不是 Emulator 2.0 配置或设备号对不上
        return False
    return path.type == PHONE_TYPE


async def phone_binding_error(script_id: str, patch: dict) -> str | None:
    """脚本保存时：不支持真机的脚本要绑到真机，返回拒绝原因；否则 ``None``。

    两套绑定字段（``Emulator.Id/Index`` 与 ``Game.EmulatorId/EmulatorIndex``）都看，只在这次
    带了设备号时检查：脚本页换模拟器配置时先单独存 Id、再存 Index，单存 Id 那次拿旧设备号
    去新配置里查会误拦。没查到的由运行时门面 ``open`` 兜底拒绝。
    """
    from app.core import Config

    try:
        script = Config.ScriptConfig[uuid.UUID(str(script_id))]
    except Exception:  # noqa: BLE001 - 找不到脚本交给后面的保存逻辑报
        return None
    if script_type_of(script) in PHONE_SCRIPT_TYPES:
        return None
    for group, id_field, index_field in _BINDING_FIELDS:
        changes = patch.get(group) if isinstance(patch, dict) else None
        if not isinstance(changes, dict) or index_field not in changes:
            continue
        try:
            emulator_id = changes.get(id_field, script.get(group, id_field))
        except Exception:  # noqa: BLE001 - 脚本类型没有这组字段
            continue
        if await is_phone_device(emulator_id, changes[index_field]):
            return phone_unsupported_message()
    return None


async def search(emulator_id: str | None = None) -> list[SearchItem]:
    """自动搜索本机模拟器，并逐条判定能否加入 Emulator 2.0。

    不支持的**不隐藏**——用户装了雷电 9 却搜不到，会以为搜索坏了。
    """
    import asyncio

    from app.utils.emulator.tools import search_all_emulators

    found = await asyncio.to_thread(search_all_emulators)

    added: set[str] = set()
    if emulator_id is not None:
        try:
            manager = await build_manager(emulator_id)
            added = {record.path_id for record in manager.paths}
        except Exception as e:  # noqa: BLE001 - 拿不到已添加列表不该让搜索整个失败
            logger.warning(f"读取已添加的模拟器路径失败: {e}")

    items: list[SearchItem] = []
    for entry in found:
        manager_exe = str(entry.get("path", ""))
        emulator_type = str(entry.get("type", ""))
        result = await probe_install_path(manager_exe, emulator_type)
        install_path = result.install_path or manager_exe
        reason = result.reason
        supported = result.supported
        if supported and make_path_id(install_path) in added:
            supported, reason = False, "already_added"
        items.append(
            SearchItem(
                type=result.type or emulator_type,
                version=result.version,
                install_path=install_path,
                alias=_default_alias(install_path),
                supported=supported,
                reason=reason,
            )
        )
    return items


def _default_alias(install_path: str, emulator_type: str = "") -> str:
    path = Path(install_path)
    if emulator_type == PHONE_TYPE:
        # 真机的安装路径是 adb.exe 本身，取它所在的文件夹名（通常是 platform-tools）
        path = path.parent
    name = path.name
    return name or install_path


def _sync_phone_path(
    manager: Emulator2Manager,
    path: PathRecord,
    backend: PhoneManager,
    info: dict,
    *,
    slot_bound: Callable[[str], bool] = lambda slot: True,
) -> list:
    """把真机后端这一轮认出来的变化落到设备号表与路径记录上，返回新分配的设备号记录。

    四件事，顺序不能乱：

    1. 手动加的地址第一次连上读到序列号：设备号表里的占位名改成序列号（设备号不变），
       ``info`` 的键跟着改；
    2. 用户恢复（或亲手重新添加地址找回）的手机：复活它原来的设备号，而不是另分一个——
       原生索引就是手机自己的序列号，同一个号必然是同一台手机。移除过的手机在已忽略
       名单里，不会自己出现在 ``info`` 里，所以这一步只会复活用户要找回的；
    3. 其余新出现的手机分配新设备号；
    4. 手动加的地址认出是一台已经有设备号的手机：占位那个号没有脚本绑着就并掉（写墓碑），
       有绑定就保留，两个号指向同一台手机，日志里提示。``slot_bound`` 判断某个设备号
       有没有脚本绑着；拿不准时按「有」处理，宁可留着重复也不弄断绑定。

    登记表有变化时把它写回路径记录（``manager.paths``），由调用方落盘。
    """
    for old, new in list(backend.renames.items()):
        if manager.slots.rename_native(path.path_id, old, new):
            backend.rename_record(old, new)
            if old in info:
                info[new] = info.pop(old)
            logger.info(f"无线地址 {old} 已认出是真机 {new}，设备号不变")
        else:
            backend.renames.pop(old, None)

    for native_index in info:
        slot = manager.slots.revive_slot(path.path_id, native_index)
        if slot is not None:
            logger.info(f"真机 {native_index} 恢复纳管，沿用设备号 #{slot}")

    added = manager.slots.sync_path(path.path_id, list(info))

    for pending_id, serialno in list(backend.merges.items()):
        backend.merges.pop(pending_id, None)
        duplicate = manager.slots.find(path.path_id, pending_id)
        target = manager.slots.find(path.path_id, serialno)
        if duplicate is None or duplicate.state != "active" or target is None:
            continue
        if slot_bound(duplicate.slot):
            logger.warning(
                f"设备 #{duplicate.slot}（{pending_id.removeprefix('tcp:')}）和设备 "
                f"#{target.slot} 是同一台手机，#{duplicate.slot} 还有脚本绑着，两个设备号都保留"
            )
            continue
        backend.forget(pending_id, ignore=False)
        manager.slots.tombstone_slot(duplicate.slot)
        info.pop(pending_id, None)
        logger.info(
            f"设备 #{duplicate.slot}（{pending_id.removeprefix('tcp:')}）认出是设备 "
            f"#{target.slot} 那台手机，已归并到设备 #{target.slot}"
        )

    if backend.dirty:
        _write_phone_extra(manager, path, backend)
    return added


def _write_phone_extra(
    manager: Emulator2Manager, path: PathRecord, backend: PhoneManager
) -> None:
    """真机登记表写回路径记录的 ``extra``，由调用方落盘。"""
    manager.paths = [
        replace(item, extra={**item.extra, **backend.export_extra()})
        if item.path_id == path.path_id
        else item
        for item in manager.paths
    ]
    backend.dirty = False


def _bound_checker(emulator_id: str) -> Callable[[str], bool]:
    """某个设备号有没有脚本绑着。查不了按「有」处理。"""

    def check(slot: str) -> bool:
        try:
            return bool(find_affected_scripts(emulator_id, [slot]))
        except Exception as e:  # noqa: BLE001 - 见 docstring
            logger.warning(f"查询设备 #{slot} 的脚本绑定失败，按有绑定处理: {e}")
            return True

    return check


async def add_path(
    emulator_id: str,
    install_path: str,
    alias: str | None = None,
    emulator_type: str | None = None,
) -> dict:
    """添加一条模拟器路径：探测版本 → 落库 → 为它的实例分配设备号。

    ``emulator_type`` 为空时按目录猜是哪一家；真机（``phone``）必须显式指定——
    雷电、MuMu 的安装目录里也有 adb.exe，按文件猜分不出来。
    """
    result: DetectResult = await probe_install_path(install_path, emulator_type)
    if not result.supported:
        return {"ok": False, "reason": result.reason, "version": result.version}

    manager = await build_manager(emulator_id)
    resolved_path = result.install_path or install_path
    path_id = make_path_id(resolved_path)

    if manager.path_of(path_id) is not None:
        return {"ok": False, "reason": "already_added", "version": result.version}

    record = PathRecord(
        path_id=path_id,
        install_path=resolved_path,
        alias=alias or _default_alias(resolved_path, result.type),
        type=result.type,
        version=result.version,
    )
    paths = manager.paths + [record]

    # 重新添加同一条路径时复活原来的墓碑, 沿用原设备号
    revived = manager.slots.revive_path(path_id)
    manager.paths = paths

    added_slots: list[dict] = []
    if record.type == PHONE_TYPE:
        # 真机没有可枚举的实例：问一次 adb，把已经插着的手机收进来。问不动也不影响添加
        try:
            backend = await manager.manager_for(record)
            info = await backend.getInfo(None)
        except Exception as e:  # noqa: BLE001 - 路径已经加好，枚举失败只记下来
            logger.warning(f"添加真机路径后枚举设备失败: {e}")
        else:
            added = _sync_phone_path(
                manager, record, backend, info, slot_bound=_bound_checker(emulator_id)
            )
            added_slots = [
                {"slot": slot_record.slot, "nativeIndex": slot_record.native_index}
                for slot_record in added
            ]
            paths = manager.paths
    else:
        native_indexes = await manager.enumerate_native(record)
        if native_indexes is not None:
            for slot_record in manager.slots.sync_path(path_id, native_indexes):
                added_slots.append(
                    {"slot": slot_record.slot, "nativeIndex": slot_record.native_index}
                )

    await _save(emulator_id, paths, manager.slots)
    return {
        "ok": True,
        "reason": "ok",
        "pathId": path_id,
        "alias": record.alias,
        "type": record.type,
        "version": record.version,
        "assignedSlots": added_slots,
        "revivedSlots": revived,
    }


async def preview_remove_path(emulator_id: str, path_id: str) -> dict:
    """移除前的确认信息：会失效的设备号 + 受影响的脚本。"""
    manager = await build_manager(emulator_id)
    slots = manager.slots.slots_of(path_id)
    return {
        "slots": slots,
        "affectedScripts": [
            item.to_dict() for item in find_affected_scripts(emulator_id, slots)
        ],
    }


async def remove_path(emulator_id: str, path_id: str) -> dict:
    """移除一条模拟器路径。

    设备号**写墓碑而不是回收**——号码永不分配给其他设备，
    否则以后新加的模拟器会顶掉旧脚本的绑定。
    """
    manager = await build_manager(emulator_id)
    affected = find_affected_scripts(emulator_id, manager.slots.slots_of(path_id))
    tombstoned = manager.slots.tombstone_path(path_id)
    paths = [record for record in manager.paths if record.path_id != path_id]

    await _save(emulator_id, paths, manager.slots)
    return {
        "ok": True,
        "tombstonedSlots": tombstoned,
        "affectedScripts": [item.to_dict() for item in affected],
    }


async def create_instance(
    emulator_id: str, path_id: str, name: str | None = None
) -> dict:
    """在某条模拟器安装下新建一个实例，并给它分配设备号。"""
    manager = await build_manager(emulator_id)
    path = manager.path_of(path_id)
    if path is None:
        return {"ok": False, "reason": "path_not_found"}
    if path.type == PHONE_TYPE:
        return {"ok": False, "reason": "unsupported"}

    backend = await manager.manager_for(path)
    native_index = await backend.create_instance(name)

    added = manager.slots.sync_path(path_id, [native_index])
    await _save(emulator_id, manager.paths, manager.slots)
    slot = added[0].slot if added else (manager.slots.find(path_id, native_index).slot)
    return {"ok": True, "reason": "ok", "slot": slot, "nativeIndex": native_index}


async def preview_delete_instance(emulator_id: str, slot: str) -> dict:
    """删除实例前的确认信息。"""
    manager = await build_manager(emulator_id)
    record = manager.slots.resolve(str(slot))
    if record is None or record.state != "active":
        return {"ok": False, "reason": "slot_not_found", "affectedScripts": []}
    return {
        "ok": True,
        "reason": "ok",
        "affectedScripts": [
            item.to_dict() for item in find_affected_scripts(emulator_id, [str(slot)])
        ],
    }


#: 「打开游戏中心」各种结局对应的一句话，直接给界面用。键是 ``AppLaunchResult.reason``。
_STORE_OPEN_MESSAGES: dict[str, str] = {
    "launched": "游戏中心已打开",
    "already-running": "游戏中心已在前台",
    "no-store": "这个模拟器没有游戏中心",
    "not-installed": "这台模拟器里没有游戏中心",
    "no-adb": "设备没有可用的 ADB 地址，无法打开游戏中心",
    "boot-timeout": "系统还没启动完成，稍后再试",
    "launch-timeout": "游戏中心没有进入前台，可能已被禁用",
}


async def open_store(emulator_id: str, slot: str) -> dict:
    """打开某台设备所属模拟器的游戏中心。

    雷电开启「大雷主人模式」之后 launcher 会把游戏中心从桌面和应用列表里过滤掉，
    用户在模拟器里没有入口；这个接口就是给界面上那个按钮用的。

    拉不起来是「这次没成」，返回 ``ok=False`` 加一句能照做的话，不抛异常——
    和 :meth:`Emulator2Manager.launch_app` 的口径一致。
    """
    manager = await build_manager(emulator_id)
    result = await manager.open_store(str(slot))
    return {
        "ok": result.ok,
        "reason": result.reason,
        "message": _STORE_OPEN_MESSAGES.get(result.reason, result.reason),
    }


async def delete_instance(emulator_id: str, slot: str) -> dict:
    """删除一个实例，并把它的设备号退役。

    早先的做法是不写墓碑，理由是「以后在同一原生索引重建实例还能拿回同一个号」。
    实测下来那个好处远不如代价：删掉的实例会一直在设备表里占一行「未找到」，
    用户看到的是一台并不存在的模拟器。

    改成写墓碑：该行从设备表消失，但**号码仍然不回收**——回收了的话，
    以后新建的实例可能拿到同一个号，而某个脚本还绑着它，就会悄悄连到另一台设备上。
    绑定了该号的脚本下次执行直接失败，不会回退到别的设备。
    """
    manager = await build_manager(emulator_id)
    record = manager.slots.resolve(str(slot))
    if record is None or record.state != "active":
        return {"ok": False, "reason": "slot_not_found"}
    path = manager.path_of(record.path_id)
    if path is None:
        return {"ok": False, "reason": "path_not_found"}

    if path.type == PHONE_TYPE:
        return await _forget_phone(emulator_id, manager, path, record)

    backend = await manager.manager_for(path)
    try:
        await backend.delete_instance(record.native_index)
    except RuntimeError as e:
        logger.warning(f"删除实例失败: {e}")
        return {"ok": False, "reason": "delete_failed", "message": str(e)}

    manager.slots.tombstone_slot(str(slot))
    await _save(emulator_id, manager.paths, manager.slots)
    return {"ok": True, "reason": "ok"}


async def _forget_phone(
    emulator_id: str, manager: Emulator2Manager, path: PathRecord, record
) -> dict:
    """移除一台真机：从登记表删掉（连同记住的无线地址），身份记进已忽略名单，设备号写墓碑。

    不断开 adb 连接，也不碰手机。之后它插着 USB 也不会再被自动收进来；用户在「管理模拟器」
    里点「恢复」（:func:`restore_phone`），或亲手重新添加它的无线地址，才重新纳管，设备号不变。
    """
    backend = await manager.manager_for(path)
    backend.forget(record.native_index)
    manager.slots.tombstone_slot(record.slot)
    _write_phone_extra(manager, path, backend)
    await _save(emulator_id, manager.paths, manager.slots)
    return {"ok": True, "reason": "ok"}


async def restore_phone(emulator_id: str, path_id: str, serial: str) -> dict:
    """恢复纳管一台移除过的真机，沿用它原来的设备号。"""
    manager = await build_manager(emulator_id)
    path = manager.path_of(path_id)
    if path is None:
        return {"ok": False, "reason": "path_not_found"}
    if path.type != PHONE_TYPE:
        return {"ok": False, "reason": "not_phone"}

    backend = await manager.manager_for(path)
    if not backend.restore(serial):
        return {"ok": False, "reason": "not_ignored"}
    info = {record_id: None for record_id in backend.records}
    _sync_phone_path(
        manager, path, backend, info, slot_bound=_bound_checker(emulator_id)
    )
    slot_record = manager.slots.find(path_id, serial)
    await _save(emulator_id, manager.paths, manager.slots)
    return {"ok": True, "reason": "ok", "slot": slot_record.slot if slot_record else ""}


async def add_phone_address(emulator_id: str, path_id: str, address: str) -> dict:
    """给真机路径添加一个无线调试地址，返回它分到的设备号。

    地址当场连一次认认是哪台手机：认得出且这台手机已有设备号（插过 USB）就沿用；
    认不出（关机、不在同一网络、端口不对）也照样添加，显示为离线，启动时再连。
    手动添加的地址不做回环过滤——用户明确加的就收。
    """
    normalized = normalize_address(address)
    if normalized is None:
        return {"ok": False, "reason": "invalid_address"}

    manager = await build_manager(emulator_id)
    path = manager.path_of(path_id)
    if path is None:
        return {"ok": False, "reason": "path_not_found"}
    if path.type != PHONE_TYPE:
        return {"ok": False, "reason": "not_phone"}

    backend = await manager.manager_for(path)
    native_index = await backend.add_address(normalized)
    renamed_to = backend.renames.get(native_index)
    # 以前加过、一直没连上的地址这次认出来了：设备号表里的占位名一并改成序列号
    info = {record_id: None for record_id in backend.records}
    _sync_phone_path(
        manager, path, backend, info, slot_bound=_bound_checker(emulator_id)
    )
    if renamed_to is not None and native_index not in backend.records:
        native_index = renamed_to
    slot_record = manager.slots.find(path_id, native_index)

    await _save(emulator_id, manager.paths, manager.slots)
    return {
        "ok": True,
        "reason": "ok",
        "slot": slot_record.slot if slot_record else "",
        "address": normalized,
        "identified": not native_index.startswith(PENDING_PREFIX),
    }


#: 同一条安装下并发读设置的上限。雷电是读文件，MuMu 每台是一个子进程；
#: 全串行时十台设备就是十个来回，全放开又会同时拉起一堆 MuMuManager.exe。
_OVERVIEW_CONCURRENCY = 4


async def list_devices(emulator_id: str, *, with_settings: bool = True) -> dict:
    """合并设备列表。

    每条安装只问一次 ``getInfo``：它既是「这次枚举到了哪些实例」，也是每台的状态，
    没必要像早先那样先枚举一遍再取一遍状态。枚举失败的安装标 ``unavailable``——
    **一次枚举失败不等于实例被删除**，既不写墓碑，也不影响下次恢复。

    ``with_settings=False`` 只取状态，不读四项设置与稳定模式——状态轮询走这条，
    设置几秒变不了一次，没必要每轮把每台的配置都读一遍（MuMu 那边每台是一个子进程）。
    """
    manager = await build_manager(emulator_id)

    devices: list[dict] = []
    dirty = False
    for path in manager.paths:
        try:
            backend = await manager.manager_for(path)
            info = await backend.getInfo(None)
        except Exception as e:  # noqa: BLE001 - 一条安装枚举失败不影响其余
            logger.warning(f"枚举 {path.alias or path.install_path} 失败: {e}")
            for record in manager.slots.records:
                if record.path_id != path.path_id or record.state != "active":
                    continue
                devices.append(
                    _device_row(
                        path, record.slot, record.native_index, None, "unavailable"
                    )
                )
            continue

        phone = isinstance(backend, PhoneManager)
        if phone:
            before = (dump_paths(manager.paths), manager.slots.to_json())
            _sync_phone_path(
                manager, path, backend, info, slot_bound=_bound_checker(emulator_id)
            )
            if (dump_paths(manager.paths), manager.slots.to_json()) != before:
                dirty = True
        elif manager.slots.sync_path(path.path_id, list(info)):
            dirty = True

        # 枚举成功但没有这台 = 已经确认它不在了（多半是在模拟器自己的多开器里删掉的）。
        # 列一行「未找到」的空设备只是噪音，用户看到的是一台并不存在的模拟器。
        # 设备号仍留在槽位表里：以后同一个原生索引再出现，还是这个号。
        #
        # 与 unavailable 的区别在于「查证不存在」和「没查成」：整条安装不可达时我们
        # 并不知道实例还在不在，那种照常显示并标暂时不可用。
        records = [
            record
            for record in manager.slots.records
            if record.path_id == path.path_id
            and record.state == "active"
            and record.native_index in info
        ]

        overviews: dict[str, tuple] = {}
        if with_settings and not phone:
            # 真机没有模拟器设置可读
            overviews = await _read_overviews(backend, records)

        for record in records:
            settings, stable, unsafe = overviews.get(
                record.native_index, ({}, False, [])
            )
            row = _device_row(
                path,
                record.slot,
                record.native_index,
                info[record.native_index],
                "ok",
                settings,
                stable,
                unsafe,
            )
            if phone:
                row["phone"] = backend.describe(record.native_index)
            devices.append(row)

    if dirty:
        await _save(emulator_id, manager.paths, manager.slots)

    return {
        "paths": [
            {
                **path.to_dict(),
                "slots": manager.slots.slots_of(path.path_id),
                "ignoredPhones": [
                    {"serial": record.id, "model": record.model}
                    for record in load_ignored(path.extra).values()
                ],
            }
            for path in manager.paths
        ],
        "devices": devices,
        # 脚本页的实例下拉据此把真机置灰：放行名单只在后端维护一份
        "phoneScriptTypes": sorted(PHONE_SCRIPT_TYPES),
    }


async def _read_overviews(backend, records) -> dict[str, tuple[dict, bool, list]]:
    """并发读一条安装下各台的设置与稳定模式。读不出的那台不在结果里，整张表照常出。"""
    import asyncio

    gate = asyncio.Semaphore(_OVERVIEW_CONCURRENCY)

    async def read_one(record) -> tuple[str, tuple | None]:
        async with gate:
            try:
                settings, stable, unsafe = await backend.read_instance_overview(
                    record.native_index
                )
            except Exception as e:  # noqa: BLE001 - 读不出设置不该让整张表挂掉
                logger.warning(f"读取设备 #{record.slot} 设置失败: {e}")
                return record.native_index, None
            return record.native_index, (settings.to_dict(), stable, unsafe)

    results = await asyncio.gather(*(read_one(record) for record in records))
    return {index: overview for index, overview in results if overview is not None}


def _device_row(
    path: PathRecord,
    slot: str,
    native_index: str,
    info,
    availability: str,
    settings: dict | None = None,
    stable_mode: bool = False,
    stable_unsafe: list[str] | None = None,
) -> dict:
    return {
        "slot": slot,
        "pathId": path.path_id,
        "alias": path.alias,
        # realType 是设备的真实类型, 前端不必自己按配置类型拼表
        "realType": path.type,
        "nativeIndex": native_index,
        "availability": availability,
        "title": getattr(info, "title", ""),
        "status": int(getattr(info, "status", 5)),
        "adbAddress": getattr(info, "adb_address", ""),
        # 这里给的是「已保存设置，下次启动使用」，不是运行中实例的当前配置——
        # 运行中保存后这里立刻变，但那台实例还在用旧值。
        "settings": settings or {},
        "stableMode": stable_mode,
        # 还没进入安全状态的项，界面用它告诉用户点一下会改动什么
        "stableUnsafe": stable_unsafe or [],
    }


# ---- 四项设置 -------------------------------------------------------------


async def apply_settings(
    emulator_id: str, slot: str, changes: dict, expected: dict | None = None
) -> dict:
    """写一台设备的设置。冲突时不覆盖，交回被改动的字段名让界面提示刷新。"""
    manager = await build_manager(emulator_id)
    try:
        applied = await manager.write_settings(str(slot), changes, expected)
    except SettingsConflictError as e:
        return {
            "ok": False,
            "conflicts": e.fields,
            "message": "配置在编辑期间被改动，请刷新后重试",
        }
    await _record_baseline(emulator_id, str(slot), applied)
    return {"ok": True, "conflicts": [], "applied": applied, "message": ""}


async def apply_stable_mode(emulator_id: str, slots: list[str] | None = None) -> dict:
    """把一台或全部设备切进稳定模式。

    ``slots`` 为空表示全部。一台失败不拖垮整批，逐台交回结果。
    """
    manager = await build_manager(emulator_id)

    targets = (
        [str(slot) for slot in slots]
        if slots
        else [
            r.slot
            for r in manager.slots.records
            if r.state == "active" and not _is_phone_slot(manager, r)
        ]
    )

    results: list[dict] = []
    for slot in targets:
        try:
            changed = await manager.apply_stable_mode(slot)
        except Exception as e:  # noqa: BLE001 - 逐台上报
            logger.warning(f"设备 #{slot} 应用稳定模式失败: {e}")
            results.append({"slot": slot, "ok": False, "message": readable_error(e)})
            continue
        results.append(
            {
                "slot": slot,
                "ok": True,
                # 空列表表示这台本来就已经是安全状态，没有可改的
                "message": "、".join(changed),
            }
        )

    return {
        "results": results,
        "okCount": sum(1 for item in results if item["ok"]),
        "failCount": sum(1 for item in results if not item["ok"]),
    }


async def apply_settings_to_all(emulator_id: str, changes: dict) -> dict:
    """把同一组设置写到**全部**设备上。

    没有勾选、没有冲突比对：用户点这个按钮就是明确要求「所有实例都设成这组值」。
    一台失败不影响其余，逐台交回结果。
    """
    manager = await build_manager(emulator_id)

    # 先校验一次，参数不合法就整批拒绝，不要写到一半才报错
    cleaned = validate_changes(changes)

    results: list[dict] = []
    for record in manager.slots.records:
        if record.state != "active" or _is_phone_slot(manager, record):
            # 真机没有模拟器设置，「全部设备」不包括它
            continue
        try:
            await manager.write_settings(record.slot, cleaned, expected=None)
        except Exception as e:  # noqa: BLE001 - 逐台上报, 一台失败不拖垮整批
            logger.warning(f"设备 #{record.slot} 应用批量设置失败: {e}")
            results.append(
                {"slot": record.slot, "ok": False, "message": readable_error(e)}
            )
            continue
        await _record_baseline(emulator_id, record.slot, cleaned)
        results.append({"slot": record.slot, "ok": True, "message": ""})

    return {
        "results": results,
        "okCount": sum(1 for item in results if item["ok"]),
        "failCount": sum(1 for item in results if not item["ok"]),
    }
