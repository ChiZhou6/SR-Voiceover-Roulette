"""独立验证：合成 (0,-40) x10 时，Raw Input 报回的位移是否就是 0 / -400。

用来区分两种可能：
  - 有系统性偏差  -> 我们的解析或结构体有问题
  - 只有随机噪声  -> 环境里真鼠标在动，属于测试环境问题
"""

from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer
from PySide6.QtWidgets import QApplication, QWidget
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

WM_INPUT = 0x00FF
RID_INPUT = 0x10000003
RIDEV_INPUTSINK = 0x00000100


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", ctypes.c_ushort),
        ("usUsage", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("hwndTarget", ctypes.c_void_p),
    ]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", ctypes.c_ulong),
        ("dwSize", ctypes.c_ulong),
        ("hDevice", ctypes.c_void_p),
        ("wParam", ctypes.c_void_p),
    ]


class RAWMOUSE(ctypes.Structure):
    _fields_ = [
        ("usFlags", ctypes.c_ushort),
        ("usButtonFlags", ctypes.c_ushort),
        ("usButtonData", ctypes.c_ushort),
        ("ulRawButtons", ctypes.c_ulong),
        ("lLastX", ctypes.c_long),
        ("lLastY", ctypes.c_long),
        ("ulExtraInformation", ctypes.c_ulong),
    ]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("mouse", RAWMOUSE)]


class INPUT(ctypes.Structure):
    class _MI(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    _fields_ = [("type", ctypes.c_ulong), ("mi", _MI)]


user32.GetRawInputData.argtypes = [
    ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint), ctypes.c_uint,
]
user32.GetRawInputData.restype = ctypes.c_uint
user32.RegisterRawInputDevices.argtypes = [
    ctypes.POINTER(RAWINPUTDEVICE), ctypes.c_uint, ctypes.c_uint,
]

acc = {"dx": 0, "dy": 0, "n": 0, "abs": 0}
sent = 0


class Filter(QAbstractNativeEventFilter):
    def nativeEventFilter(self, event_type, message):  # noqa: N802
        try:
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message != WM_INPUT:
                return False, 0
            lparam = msg.lParam

            size = ctypes.c_uint(0)
            user32.GetRawInputData(ctypes.c_void_p(lparam), RID_INPUT, None,
                                   ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
            if size.value == 0:
                return False, 0
            buf = ctypes.create_string_buffer(size.value)
            got = user32.GetRawInputData(ctypes.c_void_p(lparam), RID_INPUT, buf,
                                         ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
            if got == 0:
                return False, 0
            ri = ctypes.cast(buf, ctypes.POINTER(RAWINPUT)).contents
            if ri.header.dwType == 0:
                acc["n"] += 1
                if ri.mouse.usFlags & 0x01:
                    acc["abs"] += 1
                else:
                    acc["dx"] += ri.mouse.lLastX
                    acc["dy"] += ri.mouse.lLastY
        except Exception as exc:
            print("filter err:", exc)
        return False, 0


def send(dx: int, dy: int) -> None:
    inp = INPUT()
    inp.type = 0
    inp.mi.dx = dx
    inp.mi.dy = dy
    inp.mi.dwFlags = 0x0001
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def main() -> int:
    global sent
    app = QApplication(sys.argv)
    w = QWidget(None)
    w.setGeometry(-30000, -30000, 1, 1)
    w.show()
    # w.hide()   # 先不隐藏，验证可见性是否是收到的前提

    dev = RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK, int(w.winId()))
    ok = user32.RegisterRawInputDevices(ctypes.byref(dev), 1, ctypes.sizeof(RAWINPUTDEVICE))
    print("注册:", bool(ok), "err =", ctypes.get_last_error())
    app.installNativeEventFilter(Filter())

    def burst() -> None:
        global sent
        for _ in range(10):
            send(0, -40)
            sent += 1

    QTimer.singleShot(120, burst)
    QTimer.singleShot(1400, app.quit)
    app.exec()

    print(f"发送 {sent} 次 (0,-40)，期望 dx=0 dy={-40 * sent}")
    print(f"收到事件 {acc['n']} 个（绝对模式 {acc['abs']}）")
    print(f"累计 dx={acc['dx']}  dy={acc['dy']}")
    print("其中属于我们发送的部分：dy 至少应接近", -40 * sent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
