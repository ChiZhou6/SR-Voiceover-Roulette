"""诊断：给窗口投递真实的 WM_LBUTTONDOWN/MOUSEMOVE/LBUTTONUP，看窗口会不会被拖大。

mouse_event 注入在这台机器上按键不生效（移动能生效，按键被拦），所以改用
PostMessage 直接把系统消息投到窗口过程 —— 这跟真实点击走的是同一条 Qt 路径
（WM_LBUTTONDOWN -> QMouseEvent -> widget），只是绕开了输入队列。

跑法：python _diag_post_drag.py
"""

import ctypes
import ctypes.wintypes
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

tmp = Path(tempfile.mkdtemp(prefix="sr-post-drag-"))
shutil.copy2(ROOT / "sounds.json", tmp / "sounds.json")
shutil.copy2(ROOT / "config.json", tmp / "config.json")

import sr_roulette as sr  # noqa: E402

sr.SOUNDS_CONFIG_PATH = tmp / "sounds.json"
sr.CONFIG_PATH = tmp / "config.json"

from PySide6.QtWidgets import QApplication  # noqa: E402

import settings_window as sw  # noqa: E402

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001

user32 = ctypes.windll.user32
user32.PostMessageW.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
]


def pump(ms=80):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


app = QApplication(sys.argv)
cfg = sr.load_config()
scfg = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
scfg.load()
bank = sr.SoundBank(int(cfg["slots"]), scfg)
win = sw.SettingsWindow(cfg, scfg, bank)
win.resize(1120, 900)
win.move(240, 140)
win.setAttribute(sr.Qt.WA_DontShowOnScreen, True)
win.show()
pump(400)

# 首次运行引导卡是个浮层，会盖住左侧边缘把鼠标事件吃掉；关掉它再测
if getattr(win, "_tip", None) is not None:
    win._close_help_tip()
    pump(200)

# 强制走手动兜底：系统缩放会进模态循环把脚本卡死，这里只验证几何计算那条路
win.start_resize = lambda edges: False

hwnd = ctypes.wintypes.HWND(int(win.winId()))
dpr = win.devicePixelRatioF() or 1.0
presses = []
moves = []
_orig_press = win.mousePressEvent
_orig_move = win.mouseMoveEvent


def _spy_press(e):
    presses.append(e.position().toPoint())
    return _orig_press(e)


def _spy_move(e):
    if e.buttons() & sr.Qt.LeftButton:
        moves.append(e.position().toPoint())
    return _orig_move(e)


win.mousePressEvent = _spy_press
win.mouseMoveEvent = _spy_move


def post(msg, x_logical, y_logical, wparam):
    px = int(x_logical * dpr)
    py = int(y_logical * dpr)
    lp = (py << 16) | (px & 0xFFFF)
    user32.PostMessageW(hwnd, msg, wparam, lp)


def drag(from_logical, delta_logical, label):
    g0 = win.geometry()
    from PySide6.QtCore import QPoint as _QP
    lp = _QP(int(from_logical[0]), int(from_logical[1]))
    hit = win.childAt(lp)
    rhit = win.root.childAt(lp)
    print(f"    [命中] 点{lp} childAt={type(hit).__name__ if hit else None}"
          f"({hit.objectName() if hit else ''})  root.childAt={type(rhit).__name__ if rhit else None}"
          f"({rhit.objectName() if rhit else ''})  edges={win._edges_at(lp)}")
    presses.clear()
    moves.clear()
    post(WM_LBUTTONDOWN, from_logical[0], from_logical[1], MK_LBUTTON)
    pump(120)
    steps = 10
    for i in range(1, steps + 1):
        post(
            WM_MOUSEMOVE,
            from_logical[0] + delta_logical[0] * i / steps,
            from_logical[1] + delta_logical[1] * i / steps,
            MK_LBUTTON,
        )
        pump(45)
    g1 = win.geometry()
    post(WM_LBUTTONUP, from_logical[0] + delta_logical[0],
         from_logical[1] + delta_logical[1], 0)
    pump(120)
    dw, dh = g1.width() - g0.width(), g1.height() - g0.height()
    dx, dy = g1.x() - g0.x(), g1.y() - g0.y()
    print(f"{label:<10} {g0.width()}x{g0.height()}@{g0.x()},{g0.y()}"
          f" -> {g1.width()}x{g1.height()}@{g1.x()},{g1.y()}"
          f"  Δ宽={dw:+d} Δ高={dh:+d} Δ位={dx:+d},{dy:+d}"
          f"  按下={len(presses)} 拖动={len(moves)}")
    return dw, dh, dx, dy


res = {}
print(f"窗口 {win.width()}x{win.height()}  dpr={dpr}")
print()
# 窗口第一次收到的点击会被拿去激活窗口，先空点一下把这一步消耗掉
post(WM_LBUTTONDOWN, 560, 450, MK_LBUTTON)
pump(100)
post(WM_LBUTTONUP, 560, 450, 0)
pump(100)
win.setGeometry(240, 140, 1120, 900)
pump(100)
res["左"] = drag((2, 450), (-120, 0), "拖左边")
win.setGeometry(240, 140, 1120, 900)
pump(120)
res["右"] = drag((1118, 450), (120, 0), "拖右边")
win.setGeometry(240, 140, 1120, 900)
pump(120)
res["下"] = drag((560, 898), (0, 80), "拖下边")
win.setGeometry(240, 140, 1120, 900)
pump(120)
res["中"] = drag((560, 450), (110, 70), "拖中间")

print()
print("判断：")
print(f"  往左拖 -> 变宽且左移     : {'是' if res['左'][0] > 60 and res['左'][2] < -60 else '否'}")
print(f"  往右拖 -> 变宽、位置不变 : {'是' if res['右'][0] > 60 and res['右'][2] == 0 else '否'}")
print(f"  往下拖 -> 变高           : {'是' if res['下'][1] > 40 else '否'}")
print(f"  拖中间 -> 尺寸不变       : {'是' if res['中'][0] == 0 and res['中'][1] == 0 else '否'}")

win.hide()
win.deleteLater()
app.processEvents()
shutil.rmtree(tmp, ignore_errors=True)
print("\n诊断结束")
