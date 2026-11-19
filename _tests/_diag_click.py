"""诊断：边缘的鼠标点击能不能冒泡到 SettingsWindow.mousePressEvent。

真实链路上，Windows 发 WM_NCLBUTTONDOWN，Qt 会把它合成成客户区点击投递给
命中的控件。这里用 WM_LBUTTONDOWN 走同一段 Qt 投递代码，看事件最终落到谁手上。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

tmp = Path(tempfile.mkdtemp(prefix="sr-diag-click-"))
shutil.copy2(ROOT / "sounds.json", tmp / "sounds.json")
shutil.copy2(ROOT / "config.json", tmp / "config.json")

import sr_roulette as sr  # noqa: E402

sr.SOUNDS_CONFIG_PATH = tmp / "sounds.json"
sr.CONFIG_PATH = tmp / "config.json"

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import settings_window as sw  # noqa: E402

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001

app = QApplication(sys.argv)
cfg = sr.load_config()
scfg = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
scfg.load()
bank = sr.SoundBank(int(cfg["slots"]), scfg)
win = sw.SettingsWindow(cfg, scfg, bank)
win.resize(1120, 900)
win.move(120, 80)
win.setAttribute(Qt.WA_DontShowOnScreen, True)
win.show()
app.processEvents()
for _ in range(20):
    app.processEvents()

# 记录每一层谁拿到了按下事件
seen = []


def wrap(widget, tag):
    orig = widget.mousePressEvent

    def spy(e):
        seen.append(tag)
        return orig(e)

    widget.mousePressEvent = spy


wrap(win, "SettingsWindow")
wrap(win.root, "root")
wrap(win.titlebar, "TitleBar")
wrap(win.left_panel, "left_panel")

calls = []
real = win.start_resize


def fake(edges):
    calls.append(edges)
    return False        # 返回 False 免得真进系统模态循环把测试卡住


win.start_resize = fake

hwnd = ctypes.wintypes.HWND(int(win.winId()))
dpr = win.devicePixelRatioF() or 1.0
user32 = ctypes.windll.user32
user32.PostMessageW.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
]
W, H = win.width(), win.height()
print(f"窗口 {W}x{H}  dpr={dpr}  hwnd=0x{int(win.winId()):X}")
print()


def click(logical_x, logical_y, label):
    seen.clear()
    calls.clear()
    px = int(logical_x * dpr)
    py = int(logical_y * dpr)
    lp = (py << 16) | (px & 0xFFFF)
    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp)
    for _ in range(30):
        app.processEvents()
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)
    for _ in range(10):
        app.processEvents()
    print(f"{label:<14} 逻辑({logical_x:>4},{logical_y:>4}) -> 事件路径 {seen}  缩放请求 {calls}")


click(2, H // 2, "左边缘")
click(W // 2, H - 2, "下边缘")
click(W // 2, 2, "上边缘（标题栏）")
click(W // 2, H // 2, "正中间")
click(300, 23, "标题栏中间")

win.start_resize = real
win.hide()
win.deleteLater()
app.processEvents()
shutil.rmtree(tmp, ignore_errors=True)
print("\n诊断结束")
