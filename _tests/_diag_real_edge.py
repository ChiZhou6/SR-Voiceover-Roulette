"""诊断：真实鼠标移到窗口边缘时，光标到底变没变成双箭头。

为什么必须真机：上次就是用 SendMessage/直接调函数验证的，结果真实运行时
Windows 走的是"非客户区按下"，Qt 不产生普通鼠标事件，全都白测。
这次用 SetCursorPos 真的把鼠标挪过去，再读 GetCursorInfo 的光标句柄。

跑法：python _diag_real_edge.py
（会短暂移动鼠标，结束时复位）
"""

import ctypes
import ctypes.wintypes
import shutil
import time
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

tmp = Path(tempfile.mkdtemp(prefix="sr-real-edge-"))
shutil.copy2(ROOT / "sounds.json", tmp / "sounds.json")
shutil.copy2(ROOT / "config.json", tmp / "config.json")

import sr_roulette as sr  # noqa: E402

sr.SOUNDS_CONFIG_PATH = tmp / "sounds.json"
sr.CONFIG_PATH = tmp / "config.json"

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import settings_window as sw  # noqa: E402

user32 = ctypes.windll.user32
IDC = {
    32512: "箭头",
    32642: "斜向NWSE",
    32643: "斜向NESW",
    32644: "水平双箭头",
    32645: "垂直双箭头",
    32646: "四向移动",
}
STD = {name: user32.LoadCursorW(None, ctypes.c_void_p(code)) for code, name in [
    (32512, "ARROW"), (32644, "SIZEWE"), (32645, "SIZENS"),
    (32642, "SIZENWSE"), (32643, "SIZENESW"),
]}


class CURSORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("hCursor", ctypes.wintypes.HANDLE),
        ("ptScreenPos", ctypes.wintypes.POINT),
    ]


def current_cursor_name() -> str:
    ci = CURSORINFO()
    ci.cbSize = ctypes.sizeof(CURSORINFO)
    if not user32.GetCursorInfo(ctypes.byref(ci)):
        return "读取失败"
    h = ci.hCursor
    for name, handle in STD.items():
        if handle == h:
            return name
    return f"其它(0x{int(h or 0):X})"


app = QApplication(sys.argv)
cfg = sr.load_config()
scfg = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
scfg.load()
bank = sr.SoundBank(int(cfg["slots"]), scfg)
win = sw.SettingsWindow(cfg, scfg, bank)
win.resize(1120, 900)
win.move(200, 120)

moves = []
root_moves = []
_orig_move = win.mouseMoveEvent
_orig_root_move = win.root.mouseMoveEvent


def _spy(e):
    moves.append(e.position().toPoint())
    return _orig_move(e)


def _spy_root(e):
    root_moves.append(e.position().toPoint())
    return _orig_root_move(e)


win.mouseMoveEvent = _spy
win.root.mouseMoveEvent = _spy_root

win.show()
win.raise_()
win.activateWindow()
app.processEvents()
for _ in range(40):
    app.processEvents()

geo = win.geometry()
dpr = win.devicePixelRatioF() or 1.0
print(f"窗口 geometry={geo}  dpr={dpr}")
print(f"hwnd 可见={win.isVisible()}  前台={user32.GetForegroundWindow() == int(win.winId())}")
print()

old_pos = ctypes.wintypes.POINT()
user32.GetCursorPos(ctypes.byref(old_pos))
print(f"原鼠标位置 ({old_pos.x},{old_pos.y})")
print()


MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
SM_XV, SM_YV, SM_CXV, SM_CYV = 76, 77, 78, 79
VX = user32.GetSystemMetrics(SM_XV)
VY = user32.GetSystemMetrics(SM_YV)
VW = user32.GetSystemMetrics(SM_CXV)
VH = user32.GetSystemMetrics(SM_CYV)


def warp(sx, sy):
    """用真实输入注入移动鼠标 —— SetCursorPos 不产生 Qt 能处理的移动消息。"""
    # 绝对坐标是相对整个虚拟桌面的，多屏时按主屏算会整体偏掉
    nx = int((int(sx) - VX) * 65535 / max(1, VW - 1))
    ny = int((int(sy) - VY) * 65535 / max(1, VH - 1))
    user32.mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, nx, ny, 0, 0)


def probe(logical_x, logical_y, label):
    moves.clear()
    root_moves.clear()
    sx = int((geo.x() + logical_x) * dpr)
    sy = int((geo.y() + logical_y) * dpr)
    warp(sx, sy)
    # 轮询定时器 40ms 一次，循环里必须真让时间流逝，否则它一次都不触发
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)
    name = current_cursor_name()
    qt_shape = win.cursor().shape()
    from PySide6.QtGui import QCursor as _QC
    local = win.mapFromGlobal(_QC.pos())
    pt2 = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt2))
    under = user32.WindowFromPoint(pt2)
    print(f'   [调试] QCursor.pos={_QC.pos()} local={local} edges={win._edges_at(local)} '
          f'under=0x{int(under or 0):X} winId=0x{int(win.winId()):X} '
          f'timer={getattr(getattr(win, chr(95)+"edge_timer"), "isActive", lambda: None)()}')
    print(
        f"{label:<12} 屏幕({sx:>4},{sy:>4})  系统={name:<12} Qt={str(qt_shape):<28} "
        f"win移动={len(moves)} root移动={len(root_moves)}"
    )
    return name


W, H = win.width(), win.height()
r_left = probe(2, H // 2, "左边缘")
r_bottom = probe(W // 2, H - 2, "下边缘")
r_corner = probe(W - 3, H - 3, "右下角")
r_center = probe(W // 2, H // 2, "正中间")
r_title = probe(W // 2, 2, "标题栏顶边")

print()
print("判断：")
print(f"  左边缘为水平双箭头 : {'是' if r_left == 'SIZEWE' else '否 -> ' + r_left}")
print(f"  下边缘为垂直双箭头 : {'是' if r_bottom == 'SIZENS' else '否 -> ' + r_bottom}")
print(f"  右下角为斜向双箭头 : {'是' if r_corner == 'SIZENWSE' else '否 -> ' + r_corner}")
print(f"  正中间为普通箭头   : {'是' if r_center == 'ARROW' else '否 -> ' + r_center}")

warp(old_pos.x, old_pos.y)
win.hide()
win.deleteLater()
app.processEvents()
shutil.rmtree(tmp, ignore_errors=True)
print("\n鼠标已复位，诊断结束")
