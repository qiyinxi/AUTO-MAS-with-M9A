"""魔改 AVD 没有 modavd 命令行时显示 / 隐藏窗口：按 qemu 进程和 Qt 窗口类认主窗口与侧边工具栏，不看主窗口标题。"""

from __future__ import annotations

import os
import sys
import time

import pytest

from app.utils.windows.emulator_native import is_emulator_window

#: 模拟器实测的窗口类（Qt 6.5.3）
MAIN, MAIN_GL = "Qt653QWindowIcon", "Qt653QWindowOwnDCIcon"
TOOL, POPUP = "Qt653QWindowToolSaveBits", "Qt653QWindowPopupDropShadowSaveBits"


def test_emulator_window_found_by_class_whatever_the_title() -> None:
    found = [
        (MAIN, "Android Emulator - mas_7:20070", False),  # 现在上游的标题
        (MAIN, "Android Emulator - mas_7:20070（正在关机…）", False),
        (
            MAIN,
            "[Mouse captured, press Ctrl+G to release] Android Emulator - mas_7:20070",
            False,
        ),
        (MAIN, "方舟", False),  # 以后的标题：只有实例名
        (MAIN_GL, "方舟", False),
        ("Qt5QWindowIcon", "Android Emulator - mas_1:20010", False),
        (TOOL, "Emulator", True),  # 完整工具栏模式的侧边工具栏，属主是主窗口
    ]
    not_found = [
        (MAIN, "", False),
        (MAIN, "APK Installer", True),  # 主窗口的对话框
        (MAIN, "Extended Controls - mas_7:20070", False),
        (MAIN, "方舟 - Extended Controls", False),
        (MAIN_GL, "Display 2", False),  # 多屏时额外那块屏
        (TOOL, "方舟", False),  # 浮层、触摸板这类工具窗口
        (POPUP, "方舟", False),
        ("Qt653ScreenChangeObserverWindow", "方舟", False),  # Qt 自己的辅助窗口
        ("NVOpenGLPbuffer", "NVOGLDC invisible", False),
        ("IME", "Default IME", True),
        ("OtherAppQWindowIcon", "方舟", False),
    ]
    assert [c for c in found if not is_emulator_window(*c)] == []
    assert [c for c in not_found if is_emulator_window(*c)] == []


@pytest.mark.skipif(
    sys.platform != "win32", reason="窗口枚举和 ShowWindowAsync 只有 Windows 有"
)
def test_set_visible_touches_only_main_window_and_toolbar() -> None:
    import win32api
    import win32con
    import win32gui

    from app.utils.windows.emulator_native import prepare_window_visibility

    # 在测试进程里造几个类名照 Qt 格式起的窗口：1×1、放在屏幕外、不抢焦点、没有任务栏按钮
    suffix = f"MasTest{os.getpid()}"
    instance = win32api.GetModuleHandle(None)
    classes: dict[str, int] = {}
    windows: list[int] = []

    def create(class_name: str, title: str, owner: int = 0) -> int:
        name = class_name + suffix
        if name not in classes:
            wc = win32gui.WNDCLASS()
            wc.lpszClassName = name
            wc.lpfnWndProc = {}
            wc.hInstance = instance
            classes[name] = win32gui.RegisterClass(wc)
        hwnd = win32gui.CreateWindowEx(
            win32con.WS_EX_TOOLWINDOW | 0x08000000,  # WS_EX_NOACTIVATE
            classes[name],
            title,
            win32con.WS_POPUP | win32con.WS_VISIBLE,
            -32000,
            -32000,
            1,
            1,
            owner,  # 弹出窗口的「父窗口」就是属主
            0,
            instance,
            None,
        )
        windows.append(hwnd)
        return hwnd

    def settled(check: object) -> bool:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            win32gui.PumpWaitingMessages()
            if check():  # type: ignore[operator]
                return True
            time.sleep(0.02)
        return False

    try:
        main = create("Qt5QWindowIcon", "方舟")
        toolbar = create("Qt5QWindowToolSaveBits", "Emulator", owner=main)
        untouched = [
            create("Qt5QWindowIcon", "APK Installer", owner=main),
            create("Qt5QWindowIcon", "Extended Controls - mas_7:20070"),
            create("Qt5QWindowToolSaveBits", "方舟"),
            create("Qt5ScreenChangeObserverWindow", "方舟"),
            create("MasTestWindow", "Emulator"),
        ]
        targets = [main, toolbar]
        set_visible = prepare_window_visibility()

        assert set_visible(os.getpid(), False) == 2
        assert settled(lambda: not any(map(win32gui.IsWindowVisible, targets)))
        assert all(map(win32gui.IsWindowVisible, untouched))

        assert set_visible(os.getpid(), True) == 2
        assert settled(lambda: all(map(win32gui.IsWindowVisible, targets)))
        assert all(map(win32gui.IsWindowVisible, untouched))
    finally:
        for hwnd in reversed(windows):
            win32gui.DestroyWindow(hwnd)
        for atom in classes.values():
            win32gui.UnregisterClass(atom, instance)
