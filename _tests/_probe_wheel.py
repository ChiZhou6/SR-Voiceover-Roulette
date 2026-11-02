import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont, QImage, QPainter, QColor
app = QApplication.instance() or QApplication([])
for f in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc"):
    QFontDatabase.addApplicationFont(f)
app.setFont(QFont("Microsoft YaHei", 9))
import sounds_config as sc, sr_roulette as sr
sr.SOUNDS_DIR = Path("SR Voiceover Roulette_发布版/sounds")
cfg = sc.SoundsConfig(Path("SR Voiceover Roulette_发布版/sounds.json")); cfg.load()
bank = sr.SoundBank(8, scfg=cfg)
uicfg = dict(sr.DEFAULT_CONFIG)

w = sr.WheelWidget(uicfg, embedded=False)
w.bank = bank
w.resize(1000, 1000)
w.selected = 2
w.vx, w.vy = 0.0, -180.0
w.playing = False
img = QImage(1000, 1000, QImage.Format_ARGB32_Premultiplied)
img.fill(QColor(0, 0, 0, 0))
w.render(img)
print("图尺寸:", img.width(), img.height(), "| alpha 通道非零像素:",
      sum(1 for y in range(0, 1000, 7) for x in range(0, 1000, 7)
          if img.pixelColor(x, y).alpha() > 0))
img.save(str(ROOT / "_tests" / "_wheel_probe.png"))
