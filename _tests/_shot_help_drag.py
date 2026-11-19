"""截图：说明页里「拖上轮盘」与「窗口大小」两节，确认文案没挤坏。

跑法：python _shot_help_drag.py
产出：_shot_help_drag.png
"""

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="sr_shot_help_"))
shutil.copy2(ROOT / "config.json", TMP / "config.json")
sr.SOUNDS_CONFIG_PATH = TMP / "sounds.json"
sr.CONFIG_PATH = TMP / "config.json"

from settings_window import SettingsWindow, build_qss  # noqa: E402

app = QApplication.instance() or QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")

cfg = sr.load_config()
scfg = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
scfg.load()
bank = sr.SoundBank(int(cfg["slots"]), scfg)

win = SettingsWindow(cfg, scfg, bank)
win.setAttribute(Qt.WA_DontShowOnScreen, True)
win.resize(1400, 940)
win.setStyleSheet(build_qss())
win.show()
for _ in range(30):
    app.processEvents()

win.tabs.setCurrentWidget(win.page_help)
for _ in range(20):
    app.processEvents()

page = win.page_help
from settings_window import _FoldSection  # noqa: E402
for fold in page.findChildren(_FoldSection):
    fold.set_expanded(True)
for _ in range(20):
    app.processEvents()
# 找到滚动区，往下滚到「3｜拖上轮盘」附近
from PySide6.QtWidgets import QScrollArea  # noqa: E402

areas = page.findChildren(QScrollArea)
print(f"滚动区数量 = {len(areas)}")
if areas:
    a = areas[0]
    bar = a.verticalScrollBar()
    bar.setValue(int(bar.maximum() * 0.10))
    for _ in range(20):
        app.processEvents()
    print(f"滚动范围 0~{bar.maximum()}  当前 {bar.value()}")

pm = page.grab()
out = ROOT / "_tests" / "_shot_help_drag.png"
pm.save(str(out))
print(f"已存 {out}  {pm.width()}x{pm.height()}")

win.hide()
shutil.rmtree(TMP, ignore_errors=True)
