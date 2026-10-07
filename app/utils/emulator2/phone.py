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

"""Emulator 2.0 的「真机」后端：经 USB 或局域网 adb 纳管的安卓手机 / 平板。

和雷电 14、MuMu 6 并列，是 Emulator 2.0 的一种「安装」，几条口径：

- **安装路径就是用户自己选的 ``adb.exe``**（platform-tools 里那个）。MAS 不从模拟器目录推、
  不自动下载；这台机器上对真机的所有 adb 调用（连接、亮屏、带包启动、游戏更新、MAA）都用它。
- **启动 = 连上并准备好，关闭 = 熄屏。** 手机不是 MAS 开的：MAS 只负责连上、亮屏、解开无密码
  锁屏，收尾时熄屏；绝不关机，也绝不断开连接。
- **设备号跟着手机走。** 原生索引就是手机自己的序列号（``ro.serialno``，取不到时退回 adb 序列号），
  同一台手机先 USB 后无线（或反过来）设备号不变。手动添加、还没连上过的无线地址先用
  ``tcp:<地址>`` 占位，第一次连上读到序列号后由服务层改名，设备号不变。
- **自动发现只收真机。** ``adb devices`` 里的 ``emulator-*`` 与回环地址一律不自动收，免得把
  本机模拟器认成手机；用户明确添加的地址不做这层过滤。
- **第一期只有 MAA 能用真机**（:data:`PHONE_SCRIPT_TYPES`），以后放行别的脚本只改那一处。

凡是按 adb 输出判事实的地方都分三态：在、确认不在、查不动。查不动的不缓存，也不改持久化记录。
"""

import asyncio
import re
import time
from dataclasses import dataclass, replace
from pathlib import Path

from app.models.config import EmulatorConfig
from app.models.emulator import DeviceBase, DeviceInfo, DeviceStatus
from app.utils import ProcessRunner, get_logger

from .applaunch import AppLaunchMixin

logger = get_logger("Emulator2 真机")

#: Emulator 2.0 路径记录里的类型键
PHONE_TYPE = "phone"

#: 能用真机的脚本类型（``CLASS_BOOK`` 的键）。保存时、运行时、脚本页的下拉都按它放行，
#: 以后放行 MaaFW / MaaEnd 只改这里（运行时那条还要该脚本像 MAA 一样拿到管理器后
#: 声明自己的类型，见 :func:`bind_device_client`）。
PHONE_SCRIPT_TYPES: frozenset[str] = frozenset({"MAA"})

#: 用户在模拟器页手动启动 / 关闭：不是哪个脚本在用，任何真机都放行。
MANUAL_CLIENT = "manual"

#: 手动添加、还没连上过的无线地址的占位原生索引前缀
PENDING_PREFIX = "tcp:"

#: 无线地址没写端口时用的默认端口（``adb tcpip 5555`` 的约定）
DEFAULT_TCP_PORT = 5555

#: 单条 adb 命令的超时。设备本地查询，卡住基本只会是 adb 服务自己没起来。
_ADB_TIMEOUT = 20.0

#: ``adb connect`` 一次的超时。实测不可达地址要 21 秒才回（Windows 的 TCP 重传上限）。
_CONNECT_TIMEOUT = 25.0

#: 启动时连无线的总预算上限。``MaxWaitTime`` 默认 300 秒，是留给「模拟器开机」的；手机本来
#: 就开着，连不上多半是不在同一网络或端口变了，按 300 秒死等只会白白拖住整条代理流程。
_CONNECT_BUDGET_CAP = 30.0

#: 两次 ``adb connect`` 之间的间隔
_CONNECT_RETRY_SECONDS = 2.0

#: ``adb connect`` 报成功之后，等它在 ``adb devices`` 里变成 ``device`` 的最短时长
_CONNECT_SETTLE_SECONDS = 5.0

#: 添加无线地址时顺手连一次、认一下是哪台手机的时长。认不出也照样添加。
_ADD_CONNECT_TIMEOUT = 6.0

#: 亮屏、收起锁屏之后等界面反应的时间
_UI_SETTLE_SECONDS = 1.0

#: 轮询 ``adb devices`` 的间隔
_POLL_SECONDS = 1.0

#: 回环地址：本机模拟器（MuMu 的 ``127.0.0.1:16384``、BlueStacks、WSA）都在这上面
_LOOPBACK_HOSTS = {"localhost", "::1", "[::1]", "0.0.0.0"}

#: ``host:port``。主机名不许带空白和斜杠；IPv6 要加方括号。
_HOST_PORT = re.compile(
    r"^(?P<host>\[[0-9a-fA-F:.]+\]|[^\s:/\\\[\]]+):(?P<port>\d{1,5})$"
)
_HOST_ONLY = re.compile(r"^(?:\[[0-9a-fA-F:.]+\]|[^\s:/\\\[\]]+)$")

#: 状态 → 不在线的原因码（前端按原因码取文案）
_STATE_REASONS = {
    "unauthorized": "unauthorized",
    "offline": "offline",
    "no permissions": "no_permissions",
}

#: 连接还在建立中的几种状态，不算出错
_TRANSIENT_STATES = {"authorizing", "connecting"}


def bind_device_client(manager: object, client: str) -> None:
    """声明谁在用这个设备管理器：脚本类型（``CLASS_BOOK`` 的键）或 :data:`MANUAL_CLIENT`。

    只有 Emulator 2.0 的门面认这个声明（真机按它放行）；旧的雷电 / MuMu / 通用管理器
    没有这个概念，什么都不做。没声明的使用方一律当作不支持真机。
    """
    binder = getattr(manager, "bind_client", None)
    if callable(binder):
        binder(client)


def phone_allowed(client: str | None) -> bool:
    """这个使用方能不能用真机。``None`` 表示没声明身份，按不能用处理。"""
    return client == MANUAL_CLIENT or client in PHONE_SCRIPT_TYPES


def phone_unsupported_message() -> str:
    """不支持真机的脚本被拦下时给用户看的一句话。"""
    return (
        f"真机目前只支持 {'、'.join(sorted(PHONE_SCRIPT_TYPES))}，请为该脚本改选模拟器"
    )


# ---- 纯解析 ---------------------------------------------------------------


@dataclass(frozen=True)
class AdbDevice:
    """``adb devices -l`` 的一行。"""

    serial: str
    state: str
    model: str = ""

    @property
    def online(self) -> bool:
        return self.state == "device"

    @property
    def is_tcp(self) -> bool:
        """网络连接（``host:port``，或 Android 11 无线调试自动连上的 mDNS 名字）。"""
        return (
            bool(_HOST_PORT.match(self.serial)) or "._adb-tls-connect." in self.serial
        )


def parse_adb_devices_long(output: str) -> list[AdbDevice]:
    """解析 ``adb devices -l``，各种状态都收。

    形如（adb 37）::

        List of devices attached
        R58M123ABC             device usb:1-1 product:beyond1 model:SM_G973F device:beyond1 transport_id:1
        192.168.1.5:5555       unauthorized transport_id:3

    表头之前可能夹着 ``* daemon started successfully`` 之类的服务启动提示，只认表头之后的行。
    """
    devices: list[AdbDevice] = []
    started = False
    for raw in (output or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith("list of devices"):
            started = True
            continue
        if not started or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial = parts[0]
        if parts[1:3] == ["no", "permissions"]:
            state = "no permissions"
        else:
            state = parts[1]
        model = ""
        for token in parts[2:]:
            if token.startswith("model:"):
                model = token[len("model:") :].replace("_", " ")
                break
        devices.append(AdbDevice(serial=serial, state=state, model=model))
    return devices


def is_emulator_serial(serial: str) -> bool:
    """看起来是不是本机模拟器：``emulator-*`` 或回环地址上的 ``host:port``。"""
    if serial.startswith("emulator-"):
        return True
    match = _HOST_PORT.match(serial)
    if not match:
        return False
    host = match.group("host").lower()
    return host in _LOOPBACK_HOSTS or host.startswith("127.")


def normalize_address(text: str) -> str | None:
    """用户填的无线地址 → ``host:port``。认不出返回 ``None``。

    只写了 IP 时补 :data:`DEFAULT_TCP_PORT`，和 ``adb connect`` 自己的默认一致。
    """
    value = (text or "").strip()
    if not value:
        return None
    match = _HOST_PORT.match(value)
    if match:
        port = int(match.group("port"))
        return value if 0 < port < 65536 else None
    if _HOST_ONLY.match(value):
        return f"{value}:{DEFAULT_TCP_PORT}"
    return None


def parse_adb_version(output: str) -> str | None:
    """从 ``adb version`` 的输出里取 platform-tools 版本。

    实测（platform-tools 37）::

        Android Debug Bridge version 1.0.41
        Version 37.0.1-15733141
        Installed as ...\\platform-tools\\adb.exe

    老版本没有 ``Version`` 那一行，退回协议版本 ``1.0.41``。
    """
    text = output or ""
    match = re.search(r"^\s*Version\s+(\d+(?:\.\d+)+)", text, re.MULTILINE)
    if match:
        return match.group(1)
    match = re.search(r"Android Debug Bridge version\s+(\d+(?:\.\d+)+)", text)
    return match.group(1) if match else None


#: ``adb connect`` 的几种结局
CONNECT_CONNECTED = "connected"
CONNECT_REFUSED = "refused"
CONNECT_UNREACHABLE = "unreachable"
CONNECT_UNRESOLVED = "unresolved"
CONNECT_AUTH = "auth"
CONNECT_FAILED = "failed"


def classify_connect(output: str) -> str:
    """``adb connect`` 的输出 → 结局。**不能看返回码**：实测失败时返回码也是 0。

    实测（platform-tools 37，Windows）::

        connected to 192.168.1.5:5555
        already connected to 192.168.1.5:5555
        cannot connect to 127.0.0.1:1: No connection could be made because the target machine actively refused it. (10061)
        cannot connect to 192.0.2.1:5555: A connection attempt failed because ... (10060)
        cannot resolve host 'x.invalid' and port 5555: No such host is known. (11001)

    Windows 的套接字错误码与系统语言无关，优先认它。
    """
    text = (output or "").strip().lower()
    if text.startswith(("connected to", "already connected to")):
        return CONNECT_CONNECTED
    if "(10061)" in text or "refused" in text:
        return CONNECT_REFUSED
    if "(11001)" in text or "cannot resolve host" in text:
        return CONNECT_UNRESOLVED
    if any(
        marker in text
        for marker in ("(10060)", "(10065)", "(10051)", "timed out", "unreachable")
    ):
        return CONNECT_UNREACHABLE
    if "authenticate" in text:
        return CONNECT_AUTH
    return CONNECT_FAILED


@dataclass(frozen=True)
class KeyguardState:
    """锁屏状态。每一项都可能是 ``None``：这台手机的 dumpsys 里没有这一项，**不是**「没有」。"""

    showing: bool | None
    secure: bool | None
    trusted: bool | None


def _flag(lines: list[str], *keys: str) -> bool | None:
    for line in lines:
        for key in keys:
            if line.startswith(f"{key}="):
                value = line[len(key) + 1 :].split(maxsplit=1)
                if value and value[0].lower() in ("true", "false"):
                    return value[0].lower() == "true"
    return None


def parse_keyguard(dumpsys_output: str) -> KeyguardState:
    """从 ``dumpsys window policy`` 里读锁屏状态。

    认 AOSP 两段 dump（``KeyguardServiceDelegate`` 的 ``showing=`` / ``secure=``，
    ``KeyguardStateMonitor`` 的 ``mIsShowing=`` / ``mTrusted=``），外加老版本的
    ``mShowingLockscreen=``。各家 ROM 改过的写法认不出时返回 ``None``，调用方不得当成「没锁」。
    """
    lines = [line.strip() for line in (dumpsys_output or "").splitlines()]
    return KeyguardState(
        showing=_flag(lines, "showing", "mIsShowing", "mShowingLockscreen"),
        secure=_flag(lines, "secure", "mSecure"),
        trusted=_flag(lines, "trusted", "mTrusted"),
    )


def parse_wm_size(output: str) -> tuple[int, int] | None:
    """``wm size`` → (宽, 高)。改过分辨率时 ``Override size`` 才是实际值。"""
    found: dict[str, tuple[int, int]] = {}
    for line in (output or "").splitlines():
        match = re.search(r"(Physical|Override) size:\s*(\d+)x(\d+)", line)
        if match:
            found[match.group(1)] = (int(match.group(2)), int(match.group(3)))
    return found.get("Override") or found.get("Physical")


# ---- 持久化记录 -------------------------------------------------------------


@dataclass(frozen=True)
class PhoneRecord:
    """一台认识的手机。存在路径记录的 ``extra.phones`` 里。"""

    id: str
    """原生索引：``ro.serialno``；取不到时是 adb 序列号；还没连上过的无线地址是 ``tcp:<地址>``。"""

    model: str = ""
    usb_serial: str = ""
    """最近一次在 USB 上看到它时的 adb 序列号。"""

    wifi: str = ""
    """最近可用的无线地址（``host:port``）。离线时就靠它 ``adb connect`` 回来。"""

    @property
    def pending(self) -> bool:
        return self.id.startswith(PENDING_PREFIX)

    @property
    def title(self) -> str:
        if self.pending:
            return self.model or self.wifi
        return f"{self.model} ({self.id})" if self.model else self.id

    @classmethod
    def from_dict(cls, data: dict) -> "PhoneRecord":
        return cls(
            id=str(data.get("id", "")),
            model=str(data.get("model", "")),
            usb_serial=str(data.get("usbSerial", "")),
            wifi=str(data.get("wifi", "")),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "model": self.model,
            "usbSerial": self.usb_serial,
            "wifi": self.wifi,
        }


def load_phones(extra: dict | None) -> list[PhoneRecord]:
    phones = (extra or {}).get("phones")
    if not isinstance(phones, list):
        return []
    records = [PhoneRecord.from_dict(item) for item in phones if isinstance(item, dict)]
    return [record for record in records if record.id]


def dump_phones(records: list[PhoneRecord]) -> dict:
    return {"phones": [record.to_dict() for record in records]}


@dataclass(frozen=True)
class PhonePresence:
    """一台手机这一刻的样子。"""

    status: DeviceStatus
    device: AdbDevice | None = None
    """最合适的那条连接：在线的优先，USB 优先。``None`` 表示 adb 里没有它。"""

    reason: str = ""
    """不在线的原因码：``unauthorized`` / ``offline`` / ``no_permissions`` / ``mode``。"""

    @property
    def connection(self) -> str:
        if self.device is None:
            return ""
        return "wifi" if self.device.is_tcp else "usb"


def presence_of(devices: list[AdbDevice]) -> PhonePresence:
    """同一台手机在 adb 里的几条连接 → 它现在的状态。"""
    if not devices:
        return PhonePresence(DeviceStatus.OFFLINE)
    ordered = sorted(devices, key=lambda device: (not device.online, device.is_tcp))
    best = ordered[0]
    if best.online:
        return PhonePresence(DeviceStatus.ONLINE, best)
    if best.state in _TRANSIENT_STATES:
        return PhonePresence(DeviceStatus.STARTING, best)
    reason = _STATE_REASONS.get(best.state, "mode")
    status = DeviceStatus.OFFLINE if reason == "offline" else DeviceStatus.ERROR
    return PhonePresence(status, best, reason)


#: (adb 路径, adb 序列号) → (身份, 型号)。只要这条连接一直在 adb 里，它背后就还是同一台手机；
#: 每次 ``adb devices`` 之后把不在场的条目清掉。查失败的不进缓存。
_IDENTITY_CACHE: dict[tuple[str, str], tuple[str, str]] = {}


def _cache_key(adb_path: Path, serial: str) -> tuple[str, str]:
    return str(adb_path).casefold(), serial


def _prune_identity_cache(adb_path: Path, devices: list[AdbDevice]) -> None:
    prefix = str(adb_path).casefold()
    present = {device.serial for device in devices}
    for key in [key for key in _IDENTITY_CACHE if key[0] == prefix]:
        if key[1] not in present:
            _IDENTITY_CACHE.pop(key, None)


def _reason_message(reason: str, title: str, device: AdbDevice | None) -> str:
    """不在线的原因 → 一句能照做的话。"""
    if reason == "unauthorized":
        if device is not None and device.is_tcp:
            return f"真机 {title} 还没允许这台电脑调试：请在手机上点「允许」后重试"
        return f"真机 {title} 还没允许 USB 调试：请在手机弹出的提示里点「允许」后重试"
    if reason == "offline":
        return f"真机 {title} 已连接但没有响应：请重新插拔数据线，或在手机上关掉再打开调试后重试"
    if reason == "no_permissions":
        return f"真机 {title} 没有访问权限：请检查手机的 USB 连接方式与电脑驱动"
    state = device.state if device is not None else ""
    return f"真机 {title} 当前处于 {state} 状态，不能运行任务"


def _connect_message(outcome: str, title: str, address: str, output: str) -> str:
    """连不上无线地址 → 一句能照做的话。"""
    # 还没认出是哪台手机时名字就是地址本身，别说成「真机 A 的无线地址 A」
    target = (
        f"真机无线地址 {address}"
        if title == address
        else f"真机 {title} 的无线地址 {address}"
    )
    if outcome == CONNECT_REFUSED:
        return (
            f"{target} 拒绝连接：手机可能没开无线调试，或端口已经变了"
            "（Android 11 及以上每次打开无线调试端口都会变，请重新添加地址）"
        )
    if outcome == CONNECT_UNREACHABLE:
        return f"连不上{target}：请确认手机已开机、连着网络，并且和电脑在同一局域网"
    if outcome == CONNECT_UNRESOLVED:
        return f"{target} 无法解析，请检查地址是否写错"
    if outcome == CONNECT_AUTH:
        return f"{target} 需要先在手机上完成配对"
    if outcome == "offline":
        return f"已连上{target}，但设备没有响应，请在手机上重新打开无线调试"
    detail = output.strip().splitlines()[-1] if output.strip() else ""
    return f"连不上{target}" + (f"：{detail}" if detail else "")


# ---- 后端 -----------------------------------------------------------------


class _PhoneCore(DeviceBase):
    """真机后端的设备语义。带包启动由前面的 :class:`~.applaunch.AppLaunchMixin` 负责。"""

    #: 真机没有自带的游戏中心
    store_package: str | None = None

    def __init__(
        self, config: EmulatorConfig, adb_path: Path, records: list[PhoneRecord]
    ) -> None:
        self.config = config
        self.adb_path = adb_path
        self.records: dict[str, PhoneRecord] = {record.id: record for record in records}
        #: 登记表有没有变过（新发现的手机、新地址、型号）。服务层据此决定要不要落盘。
        self.dirty = False
        #: 占位原生索引 → 读到的序列号。只提议、不生效：设备号表由服务层改，改成了再
        #: 调 :meth:`rename_record`。在那之前照旧用占位那个名字，和设备号表保持一致。
        self.renames: dict[str, str] = {}
        self.presence: dict[str, PhonePresence] = {}

    # ---- adb ------------------------------------------------------------

    def get_adb_path(self) -> Path | None:
        return self.adb_path

    async def _adb(self, *args: str, timeout: float = _ADB_TIMEOUT) -> tuple[int, str]:
        """跑一条 adb 命令。**不抛异常**：执行不了返回 ``(-1, 错误文本)``。"""
        try:
            result = await ProcessRunner.run_process(
                self.adb_path, *args, timeout=timeout, if_merge_std=True
            )
        except Exception as e:  # noqa: BLE001 - 见 docstring
            return -1, f"{type(e).__name__}: {e}"
        return result.returncode, str(result.stdout or "")

    async def _shell(self, serial: str, *args: str) -> tuple[int, str]:
        return await self._adb("-s", serial, "shell", *args)

    async def scan(self) -> list[AdbDevice]:
        """问一次 ``adb devices -l``。adb 本身用不了时抛 ``RuntimeError``——那是「查不动」，
        不能当成「一台都不在」。"""
        code, output = await self._adb("devices", "-l")
        if code != 0 or "list of devices" not in output.lower():
            detail = output.strip().splitlines()[-1] if output.strip() else ""
            raise RuntimeError(f"adb 查询设备失败: {detail or f'返回码 {code}'}")
        devices = parse_adb_devices_long(output)
        _prune_identity_cache(self.adb_path, devices)
        return devices

    async def identify(self, device: AdbDevice) -> tuple[str, str] | None:
        """在线设备 → (身份, 型号)。查不动返回 ``None`` 且不缓存。"""
        key = _cache_key(self.adb_path, device.serial)
        cached = _IDENTITY_CACHE.get(key)
        if cached is not None:
            return cached
        if not device.online:
            return None
        code, serialno = await self._shell(device.serial, "getprop", "ro.serialno")
        if code != 0:
            return None
        identity = serialno.strip()
        if not identity or any(char.isspace() for char in identity):
            # 有的机器 ro.serialno 是空的：按约定退回 adb 序列号
            identity = device.serial
        code, model = await self._shell(device.serial, "getprop", "ro.product.model")
        result = (identity, model.strip() if code == 0 else device.model)
        _IDENTITY_CACHE[key] = result
        return result

    # ---- 登记表 ---------------------------------------------------------

    def export_records(self) -> list[PhoneRecord]:
        return list(self.records.values())

    def _update(self, record_id: str, **changes: str) -> None:
        record = self.records[record_id]
        updated = replace(record, **changes)
        if updated != record:
            self.records[record_id] = updated
            self.dirty = True

    def _owner_of_address(self, serial: str) -> str | None:
        for record in self.records.values():
            if record.wifi and record.wifi == serial:
                return record.id
        return None

    def _owner_of_usb(self, serial: str) -> str | None:
        for record in self.records.values():
            if record.usb_serial == serial or (
                not record.pending and record.id == serial
            ):
                return record.id
        return None

    async def _match(self, device: AdbDevice) -> str | None:
        """一条 adb 连接 → 它属于哪条记录。必要时登记新手机。"""
        address_owner = self._owner_of_address(device.serial)
        if address_owner is None and is_emulator_serial(device.serial):
            # 本机模拟器不自动收，也不去问它的序列号；用户明确添加的地址不在此列
            return None
        identity = await self.identify(device)

        if identity is None:
            # 认不出是哪台（未授权、离线、查不动）：只能按连接名对回已知记录
            if address_owner is not None:
                return address_owner
            owner = self._owner_of_usb(device.serial)
            if owner is not None:
                return owner
            if device.is_tcp:
                return None
            if device.state in ("unauthorized", "no permissions"):
                # 新插上、还没点「允许」的手机也要列出来，用户才知道该去手机上点一下。
                # 拿不到序列号，按约定先用 adb 序列号；USB 上它通常就是 ro.serialno
                self.records[device.serial] = PhoneRecord(
                    id=device.serial, model=device.model, usb_serial=device.serial
                )
                self.dirty = True
                return device.serial
            return None

        serialno, model = identity
        if address_owner is not None and address_owner != serialno:
            if self.records[address_owner].pending:
                # 手动加的地址第一次连上：这台就是它。设备号表还没改名之前照旧用占位名
                if serialno not in self.records:
                    self.renames[address_owner] = serialno
                    self._update(address_owner, model=model)
                return address_owner
            # 这个地址现在是另一台手机了（路由器把 IP 分给了别人）：旧记录的地址作废
            self._update(address_owner, wifi="")

        if serialno in self.records:
            if device.is_tcp:
                if _HOST_PORT.match(device.serial):
                    self._update(serialno, wifi=device.serial, model=model)
                else:
                    self._update(serialno, model=model)
            else:
                self._update(serialno, usb_serial=device.serial, model=model)
            return serialno

        self.records[serialno] = PhoneRecord(
            id=serialno,
            model=model,
            usb_serial="" if device.is_tcp else device.serial,
            wifi=device.serial
            if device.is_tcp and _HOST_PORT.match(device.serial)
            else "",
        )
        self.dirty = True
        logger.info(f"发现新的真机: {self.records[serialno].title}（{device.serial}）")
        return serialno

    async def refresh(self) -> dict[str, PhonePresence]:
        """问一次 adb，把在场的连接对到记录上，算出每台手机现在的状态。"""
        devices = await self.scan()
        grouped: dict[str, list[AdbDevice]] = {}
        for device in devices:
            record_id = await self._match(device)
            if record_id is not None:
                grouped.setdefault(record_id, []).append(device)
        self.presence = {
            record_id: presence_of(grouped.get(record_id, []))
            for record_id in self.records
        }
        return self.presence

    def rename_record(self, old: str, new: str) -> None:
        """设备号表已经把占位名改成序列号之后，登记表跟着改。"""
        record = self.records.pop(old, None)
        if record is None:
            return
        self.records[new] = replace(record, id=new)
        if old in self.presence:
            self.presence[new] = self.presence.pop(old)
        self.renames.pop(old, None)
        self.dirty = True

    def forget(self, record_id: str) -> bool:
        """不再纳管这台手机。不断开连接：连接是用户的，不是 MAS 的。"""
        if self.records.pop(record_id, None) is None:
            return False
        self.presence.pop(record_id, None)
        self.dirty = True
        return True

    async def add_address(self, address: str) -> str:
        """登记一个无线地址，返回它对应的原生索引。

        顺手 ``adb connect`` 一次（最多 :data:`_ADD_CONNECT_TIMEOUT` 秒）认一下是哪台手机：
        认得出就把地址记到那台手机上（同一台手机插过 USB 的话设备号不变）；认不出
        （关机、不在同一网络、端口不对）也照样添加，先用 ``tcp:<地址>`` 占位。
        """
        _, output = await self._adb("connect", address, timeout=_ADD_CONNECT_TIMEOUT)
        identity = None
        if classify_connect(output) == CONNECT_CONNECTED:
            device = await self._wait_device(
                address, time.monotonic() + _CONNECT_SETTLE_SECONDS
            )
            if device is not None and device.online:
                identity = await self.identify(device)

        owner = self._owner_of_address(address)
        if owner is not None:
            owner_record = self.records[owner]
            if identity is None or owner == identity[0]:
                # 已经记着这个地址（离线也无妨）：不重复登记
                if identity is not None:
                    self._update(owner, model=identity[1])
                return owner
            if owner_record.pending:
                # 以前加过、一直没连上的地址这次认出来了：和刷新时一样，提议改名、设备号不变
                if identity[0] not in self.records:
                    self.renames[owner] = identity[0]
                    self._update(owner, model=identity[1])
                return owner
            # 这个地址现在是另一台手机了：旧记录的地址作废，以这次为准
            self._update(owner, wifi="")

        if identity is None:
            record_id = f"{PENDING_PREFIX}{address}"
            self.records[record_id] = PhoneRecord(id=record_id, wifi=address)
            self.dirty = True
            return record_id

        serialno, model = identity
        if serialno in self.records:
            self._update(serialno, wifi=address, model=model)
        else:
            self.records[serialno] = PhoneRecord(id=serialno, model=model, wifi=address)
            self.dirty = True
        return serialno

    def describe(self, record_id: str) -> dict:
        """设备表里一台真机的附加信息。"""
        record = self.records.get(record_id)
        presence = self.presence.get(record_id) or PhonePresence(DeviceStatus.OFFLINE)
        if record is None:
            return {}
        return {
            "serial": "" if record.pending else record.id,
            "model": record.model,
            "connection": presence.connection,
            "adbState": presence.device.state if presence.device else "",
            "reason": presence.reason,
            "wifiAddress": record.wifi,
        }

    # ---- DeviceBase ------------------------------------------------------

    def _record(self, idx: str) -> PhoneRecord:
        record = self.records.get(str(idx))
        if record is None:
            raise RuntimeError(f"找不到真机 {idx}，它可能已被移除")
        return record

    def _info(self, record: PhoneRecord) -> DeviceInfo:
        presence = self.presence.get(record.id) or PhonePresence(DeviceStatus.OFFLINE)
        address = presence.device.serial if presence.device else record.wifi
        return DeviceInfo(
            title=record.title, status=presence.status, adb_address=address
        )

    async def getInfo(self, idx: str | None) -> dict[str, DeviceInfo]:
        await self.refresh()
        if idx is None:
            return {
                record_id: self._info(record)
                for record_id, record in self.records.items()
            }
        record = self.records.get(str(idx))
        if record is None:
            return {str(idx): DeviceInfo(str(idx), DeviceStatus.NOT_FOUND, "")}
        return {str(idx): self._info(record)}

    async def getStatus(self, idx: str) -> DeviceStatus:
        return (await self.getInfo(idx))[str(idx)].status

    async def list_devices(self) -> dict[str, str]:
        """只读登记表、不碰 adb：脚本页的下拉框等不起，离线的手机也要能选。"""
        return {record_id: record.title for record_id, record in self.records.items()}

    async def setVisible(self, idx: str, is_visible: bool) -> DeviceStatus:
        """真机没有窗口可藏。什么都不做，也不报错——「静默模式」会对每台设备调它。"""
        return DeviceStatus.UNKNOWN

    async def open(self, idx: str, package_name: str = "") -> DeviceInfo:
        """连上手机并准备好：在线就直接用（USB 优先），否则按记住的无线地址连回来；
        然后亮屏、解开无密码锁屏。**不开机**——手机关着的话 MAS 无能为力。

        带包启动由 :class:`~.applaunch.AppLaunchMixin` 在这之后做，这里不收包名。
        """
        record = self._record(idx)
        presence = (await self.refresh()).get(record.id) or PhonePresence(
            DeviceStatus.OFFLINE
        )
        device = presence.device
        if device is None or not device.online:
            if device is not None and presence.reason == "unauthorized":
                raise RuntimeError(
                    _reason_message("unauthorized", record.title, device)
                )
            if not record.wifi:
                if device is not None and presence.reason:
                    raise RuntimeError(
                        _reason_message(presence.reason, record.title, device)
                    )
                raise RuntimeError(
                    f"真机 {record.title} 没有连接：请用数据线连上电脑，"
                    "或在模拟器管理里添加它的无线调试地址"
                )
            device = await self._connect_wireless(record)

        await self._wake_and_unlock(device.serial, record.title)
        return DeviceInfo(
            title=record.title, status=DeviceStatus.ONLINE, adb_address=device.serial
        )

    async def close(self, idx: str) -> DeviceStatus:
        """熄屏。**绝不关机、不断开**；手机不在线时什么都不做。"""
        record = self.records.get(str(idx))
        if record is None:
            return DeviceStatus.NOT_FOUND
        try:
            presence = (await self.refresh()).get(record.id)
        except RuntimeError as e:
            logger.warning(f"真机 {record.title} 熄屏前查询状态失败，跳过: {e}")
            return DeviceStatus.UNKNOWN
        if presence is None or presence.device is None or not presence.device.online:
            return DeviceStatus.OFFLINE
        await self._shell(presence.device.serial, "input", "keyevent", "KEYCODE_SLEEP")
        logger.info(f"真机 {record.title} 已熄屏")
        return presence.status

    async def _wait_device(self, address: str, deadline: float) -> AdbDevice | None:
        """``adb connect`` 之后等它在 ``adb devices`` 里稳定下来（离开过渡状态）。"""
        last: AdbDevice | None = None
        while True:
            try:
                devices = await self.scan()
            except RuntimeError:
                devices = []
            last = next((d for d in devices if d.serial == address), None)
            if last is not None and last.state not in _TRANSIENT_STATES:
                return last
            if time.monotonic() >= deadline:
                return last
            await asyncio.sleep(_POLL_SECONDS)

    async def _connect_wireless(self, record: PhoneRecord) -> AdbDevice:
        """按记住的无线地址连回来，连上即返回。

        预算取 ``MaxWaitTime``，但不超过 :data:`_CONNECT_BUDGET_CAP`；地址解析不了这种
        不会自己好的情况立刻放弃。连不上时抛 ``RuntimeError``，消息说清是哪种连不上。
        """
        address = record.wifi
        max_wait = float(self.config.get("Info", "MaxWaitTime"))
        budget_end = time.monotonic() + min(max_wait, _CONNECT_BUDGET_CAP)
        outcome, output = CONNECT_FAILED, ""
        logger.info(f"真机 {record.title} 不在线，尝试连接无线地址 {address}")
        while True:
            code, output = await self._adb("connect", address, timeout=_CONNECT_TIMEOUT)
            outcome = classify_connect(output) if code != -1 else CONNECT_FAILED
            if outcome == CONNECT_CONNECTED:
                device = await self._wait_device(
                    address,
                    max(budget_end, time.monotonic() + _CONNECT_SETTLE_SECONDS),
                )
                if device is not None and device.online:
                    logger.info(f"真机 {record.title} 已通过无线连接（{address}）")
                    return device
                if device is not None and device.state == "unauthorized":
                    raise RuntimeError(
                        _reason_message("unauthorized", record.title, device)
                    )
                outcome = "offline"
            if outcome == CONNECT_UNRESOLVED:
                break
            if time.monotonic() + _CONNECT_RETRY_SECONDS >= budget_end:
                break
            await asyncio.sleep(_CONNECT_RETRY_SECONDS)
        message = _connect_message(outcome, record.title, address, output)
        logger.warning(f"{message}（adb: {output.strip()}）")
        raise RuntimeError(message)

    async def _keyguard(self, serial: str) -> KeyguardState:
        code, output = await self._shell(serial, "dumpsys", "window", "policy")
        if code != 0:
            return KeyguardState(None, None, None)
        return parse_keyguard(output)

    async def _wake_and_unlock(self, serial: str, title: str) -> None:
        """亮屏，解开无密码锁屏。有密码锁直接报错——MAS 解不开，空等没有意义。"""
        await self._shell(serial, "input", "keyevent", "KEYCODE_WAKEUP")
        await asyncio.sleep(_UI_SETTLE_SECONDS)

        state = await self._keyguard(serial)
        if state.showing is False:
            return
        if state.showing and state.secure and not state.trusted:
            raise RuntimeError(
                f"真机 {title} 设有锁屏密码，MAS 无法解锁：请把手机的屏幕锁定方式改为"
                "「无」或「滑动」，或在任务开始前保持手机解锁"
            )

        # 无密码锁屏（或这台手机读不出锁屏状态）：先请系统收起锁屏，对已解锁的手机无害
        await self._shell(serial, "wm", "dismiss-keyguard")
        await asyncio.sleep(_UI_SETTLE_SECONDS)
        if state.showing is None:
            # 读不出状态时不上滑：手机其实已解锁的话，上滑会划到游戏界面里
            logger.warning(f"读不出真机 {title} 的锁屏状态，按已解锁继续")
            return

        state = await self._keyguard(serial)
        if state.showing:
            code, size_output = await self._shell(serial, "wm", "size")
            size = parse_wm_size(size_output) if code == 0 else None
            if size is not None:
                width, height = size
                await self._shell(
                    serial,
                    "input",
                    "swipe",
                    str(width // 2),
                    str(height * 85 // 100),
                    str(width // 2),
                    str(height * 25 // 100),
                    "300",
                )
                await asyncio.sleep(_UI_SETTLE_SECONDS)
                state = await self._keyguard(serial)
        if state.showing:
            raise RuntimeError(f"真机 {title} 的锁屏没能自动解开，请手动解锁后重试")

    # ---- 模拟器专属能力：真机一律没有 ------------------------------------

    async def read_instance_settings(self, idx: str):
        raise RuntimeError("真机没有可修改的模拟器设置")

    async def write_instance_settings(self, idx: str, changes: dict, expected=None):
        raise RuntimeError("真机没有可修改的模拟器设置")

    async def read_instance_overview(self, idx: str):
        raise RuntimeError("真机没有可修改的模拟器设置")

    async def read_stable_mode(self, idx: str):
        raise RuntimeError("真机没有稳定模式")

    async def apply_stable_mode(self, idx: str) -> list[str]:
        raise RuntimeError("真机没有稳定模式")

    async def create_instance(self, name: str | None = None) -> str:
        raise RuntimeError("真机不能新建实例")

    async def delete_instance(self, idx: str) -> None:
        raise RuntimeError("真机不能删除实例")


class PhoneManager(AppLaunchMixin, _PhoneCore):
    """真机后端：设备语义 + 带包启动。"""


def resolve_phone_adb(install_path: str) -> Path | None:
    """真机的「安装路径」→ ``adb.exe``。用户可以选文件本身，也可以选它所在的文件夹。"""
    if not install_path:
        return None
    path = Path(str(install_path).strip().strip('"'))
    try:
        if path.is_dir():
            path = path / "adb.exe"
        if path.is_file() and path.name.lower() in ("adb.exe", "adb"):
            return path
    except OSError:
        return None
    return None


async def read_adb_version(adb_path: Path) -> str | None:
    """``adb version``：只打印版本，不会起 adb 服务。认不出返回 ``None``。"""
    try:
        result = await ProcessRunner.run_process(
            adb_path, "version", timeout=_ADB_TIMEOUT, if_merge_std=True
        )
    except Exception as e:  # noqa: BLE001 - 探测失败不该让调用方炸
        logger.warning(f"探测 {adb_path} 版本失败: {e}")
        return None
    return parse_adb_version(str(result.stdout or ""))


def build_manager(
    config: EmulatorConfig, adb_path: Path, extra: dict | None
) -> PhoneManager:
    return PhoneManager(config, adb_path, load_phones(extra))


__all__ = [
    "AdbDevice",
    "DEFAULT_TCP_PORT",
    "KeyguardState",
    "MANUAL_CLIENT",
    "PENDING_PREFIX",
    "PHONE_SCRIPT_TYPES",
    "PHONE_TYPE",
    "PhoneManager",
    "PhonePresence",
    "PhoneRecord",
    "bind_device_client",
    "build_manager",
    "classify_connect",
    "dump_phones",
    "is_emulator_serial",
    "load_phones",
    "normalize_address",
    "parse_adb_devices_long",
    "parse_adb_version",
    "parse_keyguard",
    "parse_wm_size",
    "phone_allowed",
    "phone_unsupported_message",
    "presence_of",
    "read_adb_version",
    "resolve_phone_adb",
]
