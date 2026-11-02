"""探针：RAWMOUSE 结构体到底有几个字节对不上。

背景怀疑：ctypes 里 usFlags(USHORT) 后面紧跟 usButtonFlags(USHORT)，
但 C 定义里中间还有 ulButtons 这个 ULONG 联合体，需要 4 字节对齐，
所以真正的 usButtonFlags 在偏移 4，而不是 2。

验证办法：合成一次鼠标滚轮事件（无害，不点任何东西），
看"按钮标志位 0x0400 (RI_MOUSE_WHEEL)"落在哪个偏移上。
滚轮值也会一起核对（usButtonData 才是 ±120）。

跑完会把光标挪回原位。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer
from PySide6.QtWidgets import QApplication, QWidget

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]

WM_INPUT = 0x00FF
RID_INPUT = 0x10000003
RIM_TYPEMOUSE = 0
RIDEV_INPUTSINK = 0x00000100
RI_MOUSE_WHEEL = 0x0400


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


# ---- 布局 A：现在程序里用的（usButtonFlags 紧跟在 usFlags 后面）----
class RAWMOUSE_A(ctypes.Structure):
    _fields_ = [
        ("usFlags", wintypes.USHORT),
        ("usButtonFlags", wintypes.USHORT),
        ("usButtonData", wintypes.USHORT),
        ("ulRawButtons", wintypes.ULONG),
        ("lLastX", wintypes.LONG),
        ("lLastY", wintypes.LONG),
        ("ulExtraInformation", wintypes.ULONG),
    ]


# ---- 布局 B：程序里现在真正在用的结构体（从 sr_roulette 直接取）----
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from sr_roulette import RAWMOUSE as RAWMOUSE_B   # noqa: E402


MOUSE_OFF = ctypes.sizeof(RAWINPUTHEADER)
seen: list[str] = []
all_events: list[int] = []


class Filter(QAbstractNativeEventFilter):
    def nativeEventFilter(self, event_type, message):  # noqa: N802
        try:
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message != WM_INPUT:
                return False, 0
            size = wintypes.UINT(0)
            user32.GetRawInputData(msg.lParam, RID_INPUT, None,
                                   ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
            if size.value == 0:
                return False, 0
            buf = ctypes.create_string_buffer(size.value)
            user32.GetRawInputData(msg.lParam, RID_INPUT, buf,
                                   ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
            hdr = ctypes.cast(buf, ctypes.POINTER(RAWINPUTHEADER)).contents
            if hdr.dwType != RIM_TYPEMOUSE:
                return False, 0

            a = ctypes.cast(ctypes.byref(buf, MOUSE_OFF), ctypes.POINTER(RAWMOUSE_A)).contents
            b = ctypes.cast(ctypes.byref(buf, MOUSE_OFF), ctypes.POINTER(RAWMOUSE_B)).contents
            all_events.append(1)
            seen.append(
                "  A: flags@2=0x%04x data@4=%d   |   B: flags@4=0x%04x data@6=%d"
                % (a.usButtonFlags, a.usButtonData,
                   b.usButtonFlags, b.usButtonData)
            )
        except Exception as exc:
            print("filter 异常:", exc)
        return False, 0


class _MI(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("mi", _MI)]


def send_wheel(delta: int) -> None:
    inp = INPUT()
    inp.type = 0
    inp.mi.mouseData = delta & 0xFFFFFFFF
    inp.mi.dwFlags = 0x0800  # MOUSEEVENTF_WHEEL
    n = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    print(f"  SendInput(mouseData={delta}) -> {n} err={ctypes.get_last_error()}")


def send_move() -> None:
    inp = INPUT()
    inp.type = 0
    inp.mi.dx = 11
    inp.mi.dy = -7
    inp.mi.dwFlags = 0x0001  # MOUSEEVENTF_MOVE
    n = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    print(f"  SendInput(MOVE) -> {n} err={ctypes.get_last_error()}")


def main() -> int:
    app = QApplication(sys.argv[:1])
    w = QWidget(None)
    w.setGeometry(-30000, -30000, 1, 1)
    w.show()      # 不能 hide：隐藏窗口收不到 INPUTSINK 投递

    dev = RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK, int(w.winId()))
    ok = bool(user32.RegisterRawInputDevices(
        ctypes.byref(dev), 1, ctypes.sizeof(RAWINPUTDEVICE)))
    print("RegisterRawInputDevices ->", ok)
    if not ok:
        return 1

    filt = Filter()          # 必须留引用，否则会被 GC 掉、过滤器直接失效
    app.installNativeEventFilter(filt)

    print(f"sizeof(RAWINPUTHEADER) = {ctypes.sizeof(RAWINPUTHEADER)}")
    print(f"RAWMOUSE_A size={ctypes.sizeof(RAWMOUSE_A)} flags 偏移="
          f"{RAWMOUSE_A.usButtonFlags.offset}")
    print(f"RAWMOUSE_B size={ctypes.sizeof(RAWMOUSE_B)} flags 偏移="
          f"{RAWMOUSE_B.usButtonFlags.offset}")

    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    saved = (p.x, p.y)
    user32.SetCursorPos(8, 8)   # 挪到桌面角落，滚轮在这儿什么也不会触发

    QTimer.singleShot(200, lambda: send_move())
    QTimer.singleShot(300, lambda: send_wheel(120))
    QTimer.singleShot(400, lambda: send_wheel(-120))
    QTimer.singleShot(1200, app.quit)
    app.exec()

    user32.SetCursorPos(*saved)

    print(f"\n收到的 raw 鼠标事件总数: {len(all_events)}")
    print(f"其中带按钮/滚轮标志位的: {sum(1 for x in seen if '0x0000  data@4=0' not in x.split('|')[0])}")
    for line in seen[:10]:
        print(line)
    wheel_a = any("A: flags@2=0x0000" in s or "A: flags@2=0x" in s and "0x0400" in s.split("|")[0] for s in seen)
    hit_b = any("B: flags@4=0x0400" in s for s in seen)
    print("\n滚轮标志 0x0400 在 B 布局（偏移 4）:", "命中" if hit_b else "没命中")
    print("结论:", "偏移 4 才是对的，A 布局读到了对齐填充字节" if hit_b else "两个布局都没命中，需要再查")
    return 0 if hit_b else 2


if __name__ == "__main__":
    raise SystemExit(main())
