import os, sys, tempfile, wave
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from PySide6.QtWidgets import QApplication
import sounds_config as sc
import sr_roulette as sr

RATE = 48000
app = QApplication.instance() or QApplication([])

def wav(path, sec):
    n = int(sec * RATE); t = np.arange(n) / RATE
    x = (0.4 * np.sin(2 * np.pi * 220 * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(x.tobytes())

tmp = Path(tempfile.mkdtemp()); snd = tmp / "sounds"; snd.mkdir()
for n in ("01 冰冰冰", "02 哇哦", "03 好耶"):
    wav(snd / f"{n}.wav", 1.0)
sr.SOUNDS_DIR = snd
cfg = sc.SoundsConfig(tmp / "sounds.json"); cfg.load(); cfg.sync([p.name for p in snd.iterdir()])
bank = sr.SoundBank(8, scfg=cfg)
import settings_window as sw
win = sw.SettingsWindow(dict(sr.DEFAULT_CONFIG), cfg, bank, None)
win.resize(1120, 780)
win.show()
app.processEvents()
win.tabs.setCurrentIndex(4)
app.processEvents()
win.page_help.sections[0].set_expanded(True)   # 展开第一节看排版
app.processEvents()
win.grab().save(str(ROOT / "_tests" / "_shot_help.png"))
print("saved")
