"""切换轮盘：手感（每帧重绘）与"瞄准色 = 该轮盘自己的颜色"。

A 重绘时机：光标在同一个扇区里移动时也要重画（以前是跨扇区才画，看着一顿一顿）
B 静止时不重画（别空转烧 CPU）
C 瞄准色的取样验证：把轮盘画到图片上，直接读那个扇区的像素
D 没单独设颜色的轮盘：仍然跟随应用主题色
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFontDatabase, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402
import theme  # noqa: E402

app = QApplication.instance() or QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")

OK = 0
FAIL = 0


def check(cond, title, detail=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK]   {title}" + (f"  ({detail})" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {title}" + (f"  ({detail})" if detail else ""))


class FakeRaw:
    """每 tick 从队列里吐一个位移，模拟手在推鼠标。"""

    def __init__(self, moves=None):
        self.moves = list(moves or [])
        self.registered = True

    def take(self):
        return self.moves.pop(0) if self.moves else (0, 0)

    def drop(self):
        self.moves.clear()

    def button_down(self, name):
        return False


class FakeScfg:
    def __init__(self, wheels, current):
        class W:
            def __init__(self, wid, name, color):
                self.wid, self.name, self.color = wid, name, color

        self.wheels = [W(*w) for w in wheels]
        self.current = current


def make_widget(cfg, entries, current="w1"):
    w = sr.WheelSwitchWidget(cfg, embedded=True)
    w.resize(520, 520)
    w.set_entries(entries, current)
    return w


CFG = dict(sr.DEFAULT_CONFIG)
E4 = [("w1", "平时", "#ff3b30"), ("w2", "整活", "#3aa0ff"),
      ("w3", "安静", ""), ("w4", "深夜", "#8e44ad")]

print("== A 光标走一步就该重画一次 ==")
w = make_widget(CFG, E4)
ctrl = sr.WheelSwitchController.__new__(sr.WheelSwitchController)
sr.WheelSwitchController.__init__(ctrl, CFG, None, FakeRaw())
ctrl.widget = w
ctrl.active = True

paints = {"n": 0}
_orig_update = w.update


def count_update(*a, **k):
    paints["n"] += 1
    return _orig_update(*a, **k)


w.update = count_update

# 4 套轮盘 -> 每格 90°，正下方是 1 号扇区中线。
# 连续推 12 步、每步只有 6 像素：全都在同一个扇区里，以前一次都不会重画。
ctrl.raw.moves = [(6, 6)] * 12
for _ in range(12):
    ctrl.poll_selection()
check(paints["n"] >= 10, "同一扇区内移动也在重画（不再冻住）",
      f"12 步触发了 {paints['n']} 次重绘")

print("== B 一动不动时不该空转 ==")
paints["n"] = 0
ctrl.raw.moves = []
for _ in range(10):
    ctrl.poll_selection()
check(paints["n"] == 0, "手没动就不重画", f"10 帧画了 {paints['n']} 次")

print("== C 瞄准色 = 这套轮盘自己的颜色 ==")


def sample_sector(widget, k, n=None):
    """把轮盘画到图里，读第 k 个扇区靠外的位置（避开文字）。"""
    import math

    n = n or len(widget.entries)
    img = QImage(widget.width(), widget.height(), QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    widget.render(img)                     # 渲染到 QPaintDevice，不额外套 painter
    cx, cy = widget.width() / 2.0, widget.height() / 2.0
    r0, r1, start_deg, span = widget.slot_geom(k, n)
    tr = (r0 + r1) / 2.0
    ang = start_deg - span * 0.22          # 偏离中线，避开文字和颜色小圆点
    x = int(cx + tr * math.cos(math.radians(ang)))
    y = int(cy - tr * math.sin(math.radians(ang)))
    return img.pixelColor(x, y), (x, y)


want = {0: (255, 59, 48), 1: (58, 160, 255), 3: (142, 68, 173)}
for k, rgb in want.items():
    w2 = make_widget(CFG, E4)
    w2.selected = k
    col, pos = sample_sector(w2, k)
    got = (col.red(), col.green(), col.blue())
    near = all(abs(a - b) <= 6 for a, b in zip(got, rgb))
    check(near, f"第 {k + 1} 套（{E4[k][1]}）选中后填充是它自己的颜色",
          f"期望 {rgb} 实际 {got} @{pos}")

print("== D 没设颜色的轮盘跟随主题色 ==")
theme.set_accent((46, 211, 108))
w3 = make_widget(CFG, E4)
w3.selected = 2                              # "安静"那套 color 为空
col, pos = sample_sector(w3, 2)
got = (col.red(), col.green(), col.blue())
near = all(abs(a - b) <= 6 for a, b in zip(got, (46, 211, 108)))
check(near, "没设颜色的那套，选中时用应用主题色", f"期望 (46, 211, 108) 实际 {got}")

print("== E 深色轮盘要配白字（否则名字看不见） ==")
deep = sr.WheelSwitchWidget._entry_paint(None, "#101a2e")
check(deep["text"].red() > 200, "深色底用浅色字", f"text={deep['text'].getRgb()}")
light_c = sr.WheelSwitchWidget._entry_paint(None, "#ffe680")
check(light_c["text"].red() < 60, "亮色底用深色字", f"text={light_c['text'].getRgb()}")
empty = sr.WheelSwitchWidget._entry_paint(None, "")
check(empty == {}, "空颜色返回空表（调用方走主题色）", str(empty))

print("== F 路径缓存：几何不变时复用 ==")
w4 = make_widget(CFG, E4)
w4.selected = 0
sample_sector(w4, 0)
first = w4._paths
sample_sector(w4, 0)
check(w4._paths is first, "第二次绘制复用同一批路径对象（没有每帧重建）")
w4.set_entries(E4, "w1")
check(w4._paths_key == (), "换数据后缓存失效", str(w4._paths_key))

print()
print(f"通过 {OK} 项，失败 {FAIL} 项")
sys.exit(1 if FAIL else 0)
