"""轮盘页：造满 8 套轮盘（含深色），看轮盘库能不能全显示、外层能不能滚。

判据：
1. 列表高度 >= 8 行，最后一行的底部落在列表范围内（没有内部滚动条）
2. 每套都看得见（深色轮盘的名字要提亮到能读）
3. 窗口矮的时候，外层滚动区能滚到底（手感卡片可达）
"""
import os
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QScrollArea

import sounds_config as sc  # noqa: E402
import sr_roulette as sr  # noqa: E402
import settings_window as sw  # noqa: E402

app = QApplication.instance() or QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyhbd.ttc")

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


RATE = 48000
tmp = Path(tempfile.mkdtemp())
snd = tmp / "sounds"
snd.mkdir()
for i in range(8):
    n = int(0.3 * RATE)
    t = np.arange(n) / RATE
    x = (0.4 * np.sin(2 * np.pi * (200 + 40 * i) * t) * 32767).astype("<i2")
    with wave.open(str(snd / f"{i:02d}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(x.tobytes())

sr.SOUNDS_DIR = snd
scfg = sc.SoundsConfig(tmp / "sounds.json")
scfg.load()
scfg.sync([k for k, _p in sr.scan_sound_files()])
bank = sr.SoundBank(8, scfg=scfg)

# 造到 8 套，颜色故意混入深色（深色在原来的实现里会让名字看不见）
COLORS = ["#ff3b30", "#1a1a2e", "#3aa0ff", "#0b3d0b", "", "#ffcc33", "#8e44ad", "#2ed36c"]
while len(scfg.wheels) < 8:
    scfg.new_wheel(f"轮盘 {len(scfg.wheels) + 1}", copy_current=True)
for w, c in zip(scfg.wheels, COLORS):
    w.color = c
scfg.switch_wheel(scfg.wheels[2].wid)

page = sw.WheelPage(dict(sr.DEFAULT_CONFIG), scfg)
page.setStyleSheet(sw.build_qss())     # 不套样式表的话抓到的是白底，跟真实观感完全两样
page.resize(520, 620)
page.show()
app.processEvents()

print("== A 列表高度够不够 ==")
lst = page.wheel_list
row_h = lst.sizeHintForRow(0)
need = lst.count() * row_h + lst.frameWidth() * 2
check(lst.count() == 8, "8 套都在列表里", f"count={lst.count()}")
check(lst.height() >= need, "列表高度能装下全部 8 行", f"高 {lst.height()}px，8 行约 {need}px")
check(not lst.verticalScrollBar().isVisible(), "列表内部没有多余的滚动条")

print("== B 最后一套是否落在可见范围内 ==")
last = lst.visualItemRect(lst.item(7))
check(last.bottom() <= lst.viewport().height(), "第 8 套完整露在外面",
      f"item8 底边 {last.bottom()} / 视口高 {lst.viewport().height()}")

print("== C 深色轮盘的名字要看得到 ==")
for i, c in enumerate(COLORS):
    if not c:
        continue
    rgb = sr.theme.parse_rgb(c)
    fg = lst.item(i).foreground().color()
    lum = 0.299 * fg.red() + 0.587 * fg.green() + 0.114 * fg.blue()
    src = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    check(lum >= 110 or src >= 110, f"第 {i + 1} 套（{c}）文字亮度 {lum:.0f} 够看",
          f"原色亮度 {src:.0f} -> 前景 {lum:.0f}")

print("== D 外层滚动：窗口矮的时候能滚到底 ==")
page.resize(520, 380)          # 故意弄矮，模拟小屏幕/大缩放
app.processEvents()
areas = page.findChildren(QScrollArea)
check(len(areas) >= 1, "轮盘页套了滚动区", f"找到 {len(areas)} 个")
sa = areas[0]
bar = sa.verticalScrollBar()
check(bar.maximum() > 0, "窗口矮时出现滚动条", f"可滚 {bar.maximum()}px")
bar.setValue(bar.maximum())
app.processEvents()
check(bar.value() == bar.maximum(), "能滚到底部（手感卡片可达）")

page.resize(520, 620)
app.processEvents()
img = page.grab()
out = Path(__file__).parent / "_shot_wheelpage_8.png"
img.save(str(out))
print("saved", out.name)

print()
print(f"通过 {OK} 项，失败 {FAIL} 项")
sys.exit(1 if FAIL else 0)
