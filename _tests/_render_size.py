"""临时视觉验证：整体大小 70/100/140% 的实时轮盘、设置页预览、暂停提示。

跑法：python _render_size.py

产出 5 张图放在 _tests/ 下，逐张看：
  _shot_size_70.png / _shot_size_100.png / _shot_size_140.png   实时轮盘（带外圈）
  _shot_size_preview.png                    设置页里的预览（120%）
  _shot_pause_toast.png                     暂停提示（40% 不透明度）
（都写在 _tests/ 下，已被 .gitignore 忽略）
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent   # 截图落在 _tests/ 下，别污染仓库根目录
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402

app = QApplication.instance() or QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")

NAMES = ["前方有敌", "撤退撤退", "跟我来", "干得漂亮", "小心地雷", "集火集火",
         "掩护我", "上上上", "别送了", "牛哇", "好耶", "稳住", "冲啊", "在这里"]


class FakeBank:
    def __init__(self, names):
        self.names = list(names)

    def __len__(self):
        return len(self.names)

    def name_at(self, i):
        return self.names[i] if 0 <= i < len(self.names) else ""

    def outer_index_map(self):
        extra = max(0, len(self.names) - 8)
        return [8 + p if p < extra else None for p in range(12)]


def backdrop(w: int, h: int) -> QPixmap:
    pm = QPixmap(w, h)
    pm.fill(QColor(26, 31, 27))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(QPen(QColor(58, 66, 58), 2))
    for i in range(-h, w, 46):
        p.drawLine(0, i, w, i + w)
    p.setBrush(QColor(96, 88, 64, 90))
    p.setPen(Qt.NoPen)
    p.drawRect(QRectF(24, h - 132, 118, 96))
    p.setBrush(QColor(70, 84, 96, 80))
    p.drawRect(QRectF(w - 150, 28, 122, 84))
    p.end()
    return pm


def render_realtime(scale: float) -> None:
    cfg = dict(sr.DEFAULT_CONFIG)
    cfg["wheel_scale"] = scale
    cfg["opacity"] = 0.94
    bank = FakeBank(NAMES[:14])

    extent = sr.ring_layout(cfg, len(bank), sr.wheel_scale_of(cfg))["extent"]
    size = int(extent * 2 + 48)
    size += size % 2

    w = sr.WheelWidget(cfg)
    w.bank = bank
    w.resize(size, size)
    w.selected = 1
    # 虚拟光标推到外圈第 1 格附近
    w.vx, w.vy = 40.0 * scale, -float(extent) * 0.72

    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    w.render(pm)

    canvas = backdrop(size, size)
    p = QPainter(canvas)
    p.drawPixmap(0, 0, pm)
    f = QFont("Microsoft YaHei")
    f.setPointSize(9)
    p.setFont(f)
    p.setPen(QPen(QColor(210, 216, 224, 200)))
    p.drawText(QRectF(0, size - 22, size, 18), Qt.AlignCenter,
               f"整体大小 {int(scale * 100)}%   窗口 {size}px")
    p.end()
    out = OUT / f"_shot_size_{int(scale * 100)}.png"
    canvas.save(str(out))
    print("已生成", out.name)
    w.hide()


def render_preview() -> None:
    """设置页里的预览控件（embedded），120%，4 个音效。"""
    import settings_window as sw

    cfg = dict(sr.DEFAULT_CONFIG)
    cfg["wheel_radius"] = 172
    cfg["wheel_scale"] = 1.2
    bank = FakeBank(NAMES[:4])

    w = sw.WheelPreview(cfg, bank)
    side = int(cfg["wheel_radius"] * 2 + 48)
    w.setFixedSize(side, side)
    w.selected = 0

    canvas = backdrop(side, side)
    p = QPainter(canvas)
    p.drawPixmap(0, 0, w.grab())
    f = QFont("Microsoft YaHei")
    f.setPointSize(9)
    p.setFont(f)
    p.setPen(QPen(QColor(210, 216, 224, 200)))
    p.drawText(QRectF(0, side - 22, side, 18), Qt.AlignCenter, "设置页预览 120%")
    p.end()
    out = OUT / "_shot_size_preview.png"
    canvas.save(str(out))
    print("已生成", out.name)
    w.hide()


def render_toast() -> None:
    cfg = dict(sr.DEFAULT_CONFIG)
    cfg["opacity"] = 0.40
    cfg["animations"] = True
    t = sr.PauseToast(cfg)
    t.paused = True
    t.t = 0.5

    W, H = 640, 360          # 模拟一块屏幕
    canvas = backdrop(W, H)
    pm = QPixmap(t.size())
    pm.fill(Qt.transparent)
    t.render(pm)
    p = QPainter(canvas)
    # 按屏幕 3/4 的位置贴到模拟画面上
    p.drawPixmap((W - t.width()) // 2, int(H * 0.75) - t.height() // 2, pm)
    p.setPen(QPen(QColor(255, 110, 110, 200)))
    p.drawLine(0, int(H * 0.5), W, int(H * 0.5))
    f = QFont("Microsoft YaHei")
    f.setPointSize(8)
    p.setFont(f)
    p.setPen(QPen(QColor(220, 150, 150, 220)))
    p.drawText(QRectF(6, int(H * 0.5) + 4, 200, 16), Qt.AlignLeft, "屏幕正中（红线）")
    p.end()
    out = OUT / "_shot_pause_toast.png"
    canvas.save(str(out))
    print("已生成", out.name)
    t.hide()


render_realtime(0.7)
render_realtime(1.0)
render_realtime(1.4)
render_preview()
render_toast()
