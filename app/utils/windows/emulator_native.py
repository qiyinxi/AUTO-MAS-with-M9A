"""模拟器的 Windows 宿主能力。"""

import ctypes
from pathlib import Path

from ..contracts.emulator_native import WindowVisibility

_EMULATOR_TOOLBAR_TITLE = "Emulator"


def is_emulator_window(class_name: str, title: str, owned: bool) -> bool:
    """模拟器进程里这个类名、标题、有没有属主的顶层窗口，是不是它的主窗口或侧边工具栏。

    Qt 给 QWindow 起的窗口类名是 ``Qt<版本>QWindow<类型>``（模拟器主窗口实测 ``Qt653QWindowIcon``），
    工具窗口、弹出窗口的类型以 ``Tool`` / ``Popup`` 开头；Qt 自己的辅助窗口（屏幕变化监听）不叫这个名字。
    主窗口是既不是工具窗口也不是弹出窗口、没有属主、标题不为空的那个 QWindow，标题写什么都认：上游的
    ``Android Emulator - <avd>:<控制台端口>`` 会带上鼠标捕获的前缀或安全关机的后缀，以后还会改成实例名。
    调用方已经按进程号选好了这台实例的 qemu，它只有一个主窗口。上游另有两种同样形状的窗口，按写死的标题
    排除：扩展控制（Extended Controls）和多屏的 ``Display <n>``。侧边工具栏（完整工具栏模式）是标题为
    ``Emulator`` 的工具窗口。
    """
    _, found, kind = class_name.partition("QWindow")
    if not found or not class_name.startswith("Qt") or not title:
        return False
    if title == _EMULATOR_TOOLBAR_TITLE:
        return True
    if owned or kind.startswith(("Tool", "Popup")):
        return False
    return "Extended Controls" not in title and not _display_title(title)


def _display_title(title: str) -> bool:
    """``Display <n>``：多屏时额外那块屏的窗口标题。"""
    number = title.removeprefix("Display ")
    return number != title and number.isdigit()


def shm_exists(port: int) -> bool:
    """截图共享内存 ``SHM_videmulator<控制台端口>`` 在不在（MaaFW AVDExtras 读它）。"""
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (AttributeError, OSError):
        return False
    open_mapping = kernel32.OpenFileMappingW
    open_mapping.restype = ctypes.c_void_p
    open_mapping.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p)
    handle = open_mapping(0x0004, 0, f"SHM_videmulator{port}")  # FILE_MAP_READ
    if not handle:
        return False
    kernel32.CloseHandle(ctypes.c_void_p(handle))
    return True


def prepare_window_visibility() -> WindowVisibility:
    """在事件循环线程解析桌面依赖，返回同步窗口操作。"""
    from ctypes import wintypes

    import win32con
    import win32gui
    import win32process

    def set_emulator_windows_visible(pid: int, visible: bool) -> int:
        """对 qemu 进程 ``pid`` 的主窗口与侧边工具栏发 ``SW_SHOW`` / ``SW_HIDE``，返回处理的窗口数。

        窗口按进程号和窗口类认（:func:`is_emulator_window`），不看主窗口的标题；同一进程里一大堆
        OpenGL / 输入法 / Qt 自己的隐藏窗口、扩展控制和对话框都不碰。无头开机的进程没有这两个窗口，
        返回 0。用 ``ShowWindowAsync`` 只投递消息，不等模拟器界面线程。"""
        targets: list[int] = []

        def collect(hwnd: int, _: object) -> bool:
            try:
                _, process_id = win32process.GetWindowThreadProcessId(hwnd)
                if process_id != pid:
                    return True
                class_name = win32gui.GetClassName(hwnd)
                title = win32gui.GetWindowText(hwnd)
                owned = bool(win32gui.GetWindow(hwnd, win32con.GW_OWNER))
            except Exception:  # noqa: BLE001 - 枚举途中窗口被销毁
                return True
            if is_emulator_window(class_name, title, owned):
                targets.append(hwnd)
            return True

        win32gui.EnumWindows(collect, None)

        # 私有一份 user32 声明原型，不影响进程里其它走 ctypes.windll.user32 的代码
        show = ctypes.WinDLL("user32").ShowWindowAsync
        show.argtypes = [wintypes.HWND, ctypes.c_int]
        show.restype = wintypes.BOOL
        for hwnd in targets:
            show(hwnd, win32con.SW_SHOW if visible else win32con.SW_HIDE)
        return len(targets)

    return set_emulator_windows_visible


def cpu_cache_topology() -> bytes:
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (AttributeError, OSError):
        return b""
    get_info = kernel32.GetLogicalProcessorInformationEx
    get_info.restype = ctypes.c_int
    get_info.argtypes = (ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32))
    relation_cache = 2
    length = ctypes.c_uint32(0)
    get_info(relation_cache, None, ctypes.byref(length))
    if not length.value:
        return b""
    buffer = ctypes.create_string_buffer(length.value)
    if not get_info(relation_cache, buffer, ctypes.byref(length)):
        return b""
    return buffer.raw[: length.value]


def vulkan_probe_path() -> Path | None:
    from pathlib import Path

    return Path(__file__).with_name("vulkan_probe.py")
