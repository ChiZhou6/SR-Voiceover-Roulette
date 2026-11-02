"""展开「三、详细使用教程」和「四、常见问题」，看新增段落排版是否正常。"""
import os
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyhbd.ttc")

import sounds_config as sc
import sr_roulette as sr
import settings_window as sw

RATE = 48000


def wav(path, sec):
    n = int(sec * RATE)
    t = np.arange(n) / RATE
    x = (0.4 * np.sin(2 * np.pi * 220 * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(x.tobytes())


tmp = Path(tempfile.mkdtemp())
snd = tmp / "sounds"
snd.mkdir()
for n in ("01 冰冰冰", "02 哇哦", "03 好耶"):
    wav(snd / f"{n}.wav", 1.0)
sr.SOUNDS_DIR = snd
cfg = sc.SoundsConfig(tmp / "sounds.json")
cfg.load()
cfg.sync([p.name for p in snd.iterdir()])
bank = sr.SoundBank(8, scfg=cfg)

win = sw.SettingsWindow(dict(sr.DEFAULT_CONFIG), cfg, bank, None)
win.resize(1120, 1400)
win.show()
app.processEvents()

win.tabs.setCurrentIndex(4)
app.processEvents()

page = win.page_help
for sec in page.sections:
    if sec.title.startswith(("三、", "四、")):
        sec.set_expanded(True)
        app.processEvents()

for _ in range(4):
    app.processEvents()

out = Path(__file__).parent / "_shot_help_steps.png"
win.grab().save(str(out))
print("saved", out)

sa = None
for c in page.findChildren(object):
    if c.__class__.__name__ == "QScrollArea":
        sa = c
        break
if sa:
    hb = sa.horizontalScrollBar()
    print("横向滚动条可见:", bool(hb and hb.isVisible()))
    vb = sa.verticalScrollBar()
    print("内容高度:", sa.widget().sizeHint().height(), "视口:", sa.viewport().height())
    vb.setValue(vb.maximum())
    for _ in range(3):
        app.processEvents()
    out2 = Path(__file__).parent / "_shot_help_faq.png"
    win.grab().save(str(out2))
    print("saved", out2)

