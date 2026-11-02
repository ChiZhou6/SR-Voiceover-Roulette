"""探针：验证 Raw Input 能否在后台读到鼠标相对位移。

背景：游戏里光标被 ClipCursor + 每帧归位钉在屏幕中心，
GetCursorPos 读到的几乎是个常量，所以现有的"读光标绝对位置"判定彻底失效。
Raw Input（WM_INPUT）走的是驱动层，拿到的是硬件相对位移，不受光标锁定影响。

本探针只用 SendInput 合成移动来自测管线是否打通，
真实物理鼠标的可靠性只会更高。
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer
from PySide6.QtWidgets import QApplication, QWidget

user32 = ctypes.WinDLL("user32", use_last_error=True)

WM_INPUT = 0x00FF
RID_INPUT = 0x10000003
RIM_TYPEMOUSE = 0
RIDEV_INPUTSINK = 0x00000100
MOUSE_MOVE_RELATIVE = 0x00


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
        ("dwFlags", wintypes.DWORD),
        ("hwndTarget", wintypes.HWND),
    ]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", wintypes.DWORD),
        ("dwSize", wintypes.DWORD),
        ("hDevice", wintypes.HANDLE),
        ("wParam", wintypes.WPARAM),
    ]


class RAWMOUSE(ctypes.Structure):
    _fields_ = [
        ("usFlags", wintypes.USHORT),
        ("usButtonFlags", wintypes.USHORT),
        ("usButtonData", wintypes.USHORT),
        ("ulRawButtons", wintypes.ULONG),
        ("lLastX", wintypes.LONG),
        ("lLastY", wintypes.LONG),
        ("ulExtraInformation", wintypes.ULONG),
    ]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("mouse", RAWMOUSE)]


class INPUT(ctypes.Structure):
    class _MI(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    _fields_ = [("type", wintypes.DWORD), ("mi", _MI)]


accum = {"x": 0, "y": 0, "events": 0, "abs": 0}


class Filter(QAbstractNativeEventFilter):
    def nativeEventFilter(self, event_type, message):  # noqa: N802
        try:
            if bytes(event_type) != b"windows_generic_MSG":
                return False, 0
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message != WM_INPUT:
                return False, 0

            size = wintypes.UINT(0)
            user32.GetRawInputData(msg.lParam, RID_INPUT, None,
                                   ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
            if size.value == 0:
                return False, 0
            buf = ctypes.create_string_buffer(size.value)
            got = user32.GetRawInputData(msg.lParam, RID_INPUT, buf,
                                         ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
            if got == 0:
                return False, 0
            ri = ctypes.cast(buf, ctypes.POINTER(RAWINPUT)).contents
            if ri.header.dwType == RIM_TYPEMOUSE:
                accum["events"] += 1
                if ri.mouse.usFlags & 0x01:  # MOUSE_MOVE_ABSOLUTE
                    accum["abs"] += 1
                else:
                    accum["x"] += ri.mouse.lLastX
                    accum["y"] += ri.mouse.lLastY
        except Exception as exc:  # 探针里宁可吞掉也不能崩
            print("filter 异常:", exc)
        return False, 0


def main() -> int:
    app = QApplication(sys.argv)
    w = QWidget()
    w.setWindowTitle("rawinput-probe")
    w.resize(200, 120)
    w.show()

    dev = RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK, int(w.winId()))
    ok = user32.RegisterRawInputDevices(
        ctypes.byref(dev), 1, ctypes.sizeof(RAWINPUTDEVICE)
    )
    print("RegisterRawInputDevices ->", bool(ok), "err =", ctypes.get_last_error())
    if not ok:
        print("结论：Raw Input 注册失败，方案不可行")
        return 1

    filt = Filter()
    app.installNativeEventFilter(filt)

    def synth() -> None:
        """合成相对鼠标移动，用来证明 WM_INPUT 确实被回收到了。"""
        inp = INPUT()
        inp.type = 0  # INPUT_MOUSE
        inp.mi.dx = 37
        inp.mi.dy = -21
        inp.mi.dwFlags = 0x0001  # MOUSEEVENTF_MOVE
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    for _ in range(5):
        synth()

    QTimer.singleShot(900, app.quit)
    app.exec()

    print(f"收到 WM_INPUT 事件数: {accum['events']}")
    print(f"累计相对位移: dx={accum['x']} dy={accum['y']}")
    print(f"绝对模式事件数: {accum['abs']}")
    print("结论:", "Raw Input 管线可用" if accum["events"] > 0 else "未收到任何 raw 事件")
    return 0 if accum["events"] > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
