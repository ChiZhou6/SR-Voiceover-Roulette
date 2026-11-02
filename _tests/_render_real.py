import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont
app = QApplication.instance() or QApplication([])
for f in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc"):
    QFontDatabase.addApplicationFont(f)
app.setFont(QFont("Microsoft YaHei", 9))
import sounds_config as sc
import sr_roulette as sr
import settings_window as sw
sr.SOUNDS_DIR = Path("SR Voiceover Roulette_发布版/sounds")
cfg = sc.SoundsConfig(Path("SR Voiceover Roulette_发布版/sounds.json"))
cfg.load()
bank = sr.SoundBank(8, scfg=cfg)
win = sw.SettingsWindow(dict(sr.DEFAULT_CONFIG), cfg, bank, None)
win.resize(1180, 800)
win.show()
app.processEvents()
win.grab().save(str(ROOT / "_tests" / "_real_lib.png"))
win.tabs.setCurrentIndex(1); app.processEvents()
win.grab().save(str(ROOT / "_tests" / "_real_key.png"))
print("ok")
