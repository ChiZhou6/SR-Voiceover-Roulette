"""渲染轮盘预览图（不弹窗），用于确认视觉效果。

生成三张图：
  preview_wheel.png      选中第 3 个槽位、虚拟光标偏向右下
  preview_center.png     刚打开轮盘、光标还在正中（未选中）
  preview_idle.png       静止提示态
"""

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402


def render_wheel(cfg, bank, selected: int | None, vx: float, vy: float, size: int) -> QPixmap:
    w = sr.WheelWidget(cfg)
    w.bank = bank
    w.resize(size, size)
    w.selected = selected
    w.vx, w.vy = vx, vy
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    w.render(pm)
    return pm


def backdrop(size: int) -> QPixmap:
    """深色底 + 网格 + 几块方形，模拟游戏画面被盖住时的观感。"""
    canvas = QPixmap(size, size)
    canvas.fill(QColor(26, 31, 27))
    p = QPainter(canvas)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(QPen(QColor(58, 66, 58), 2))
    for i in range(-size, size, 46):
        p.drawLine(0, i, size, i + size)
    p.setBrush(QColor(96, 88, 64, 90))
    p.setPen(Qt.NoPen)
    p.drawRect(QRectF(24, size - 132, 118, 96))
    p.setBrush(QColor(70, 84, 96, 80))
    p.drawRect(QRectF(size - 150, 28, 122, 84))
    p.end()
    return canvas


def compose(cfg, bank, selected, vx, vy, size, caption, out_name) -> Path:
    canvas = backdrop(size)
    wheel_pm = render_wheel(cfg, bank, selected, vx, vy, size)
    p = QPainter(canvas)
    p.drawPixmap(0, 0, wheel_pm)
    p.setPen(QPen(QColor(190, 196, 205, 170)))
    f = QFont()
    f.setPointSize(8)
    p.setFont(f)
    p.drawText(QRectF(0, size - 20, size, 16), Qt.AlignCenter, caption)
    p.end()
    out = ROOT / out_name
    canvas.save(str(out))
    print(f"已生成 {out.name}  ({size}x{size})")
    return out


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841
    cfg = dict(sr.DEFAULT_CONFIG)
    bank = sr.SoundBank(8)
    if len(bank) == 0:
        print("sounds 目录为空，先跑 gen_test_sounds.sh")
        return 1

    size = int(cfg["wheel_radius"] * 2 + 48)
    if size % 2:
        size += 1
    n = max(1, len(bank))

    # 选中态：挑中间那个扇区（音效数量不固定，不能写死编号）
    selected = min(1, n - 1)
    step = 360.0 / n
    mid = math.radians(90.0 - (selected + 0.5) * step)
    reach = float(cfg["wheel_radius"]) * float(cfg["max_offset_ratio"]) * 0.92
    vx = reach * math.cos(mid)
    vy = -reach * math.sin(mid)
    compose(cfg, bank, selected, vx, vy, size,
            f"选中态：{len(bank)} 个槽位，虚拟光标指向第 {selected + 1} 个", "preview_wheel.png")

    # 刚打开：光标在正中，还没选中
    compose(cfg, bank, None, 0.0, 0.0, size,
            "刚打开：虚拟光标在正中，此时松开即取消", "preview_center.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
