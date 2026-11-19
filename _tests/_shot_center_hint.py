"""截图：拖着音效停在轮盘中心 / 停在某个扇区。

跑法：python _shot_center_hint.py
产出：_shot_center_big.png（大窗口）/ _shot_center_small.png（小窗口）
"""

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="sr_shot_center_"))
(TMP / "sounds").mkdir()
for src in sorted((ROOT / "sounds").glob("*.wav")):
    shutil.copy2(src, TMP / "sounds" / src.name)
sr.SOUNDS_DIR = TMP / "sounds"
sr.SOUNDS_CONFIG_PATH = TMP / "sounds.json"
sr.CONFIG_PATH = TMP / "config.json"
shutil.copy2(ROOT / "config.json", sr.CONFIG_PATH)

from settings_window import ADD_TO_END, SettingsWindow  # noqa: E402

app = QApplication.instance() or QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyhbd.ttc")

OUT = ROOT / "_tests"


def shot(size, path, from_lib=True, target=ADD_TO_END, dragging=True, whole=None):
    cfg = sr.load_config()
    scfg = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
    scfg.load()
    bank = sr.SoundBank(int(cfg["slots"]), scfg)
    win = SettingsWindow(cfg, scfg, bank)
    win.setAttribute(sr.Qt.WA_DontShowOnScreen, True)
    win.resize(*size)
    win.show()
    app.processEvents()
    for _ in range(6):
        app.processEvents()

    pv = win.preview
    if dragging:
        pv.begin_lib_drag()
    else:
        pv.end_lib_drag()
    pv.drop_target = target
    pv._drag_from_lib = from_lib
    pv.update()
    app.processEvents()
    for _ in range(4):
        app.processEvents()

    pm = pv.grab()
    pm.save(str(OUT / path))
    print(f"{path}  轮盘 {pm.width()}x{pm.height()}  文案={pv.center_hint!r}")
    if whole:
        wp = win.grab()
        wp.save(str(OUT / whole))
        print(f"{whole}  整窗 {wp.width()}x{wp.height()}")
    win.hide()
    win.deleteLater()
    app.processEvents()


# 刚抓起音效、鼠标还在左边的库上：中心就该亮着
shot((1400, 900), "_shot_center_drag_start.png", target=None,
     whole="_shot_center_drag_start_win.png")
shot((1400, 900), "_shot_center_big.png", from_lib=True)
shot((1120, 900), "_shot_center_small.png", from_lib=True)
shot((1400, 900), "_shot_center_on_sector.png", target=0)
shot((1400, 900), "_shot_center_idle.png", dragging=False,
     whole="_shot_center_idle_win.png")

shutil.rmtree(TMP, ignore_errors=True)
print("done")
