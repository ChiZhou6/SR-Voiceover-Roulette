"""把组合编辑器渲染成 PNG，用来肉眼查错位/挤字/白块。"""
import os
import sys
import tempfile
import wave
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


def write_wav(path: Path, seconds: float, freq: float = 440.0):
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    x = (0.4 * np.sin(2 * np.pi * freq * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(x.tobytes())


tmp = Path(tempfile.mkdtemp())
snd = tmp / "sounds"
snd.mkdir()
for name, sec, f in (("01 冰冰冰", 1.25, 440), ("02 哇哦", 2.0, 330),
                     ("03 好耶", 0.8, 550), ("04 叹息", 1.6, 220),
                     ("05 笑声", 2.4, 660)):
    write_wav(snd / f"{name}.wav", sec, f)
sr.SOUNDS_DIR = snd

cfg = sc.SoundsConfig(tmp / "sounds.json")
cfg.load()
cfg.sync([p.name for p in snd.iterdir()])
cdef = cfg.new_combo("三连升调")
cdef.items = [
    sc.ComboItem(sound="01 冰冰冰.wav", trig=sc.TRIG_COMBO, delay_ms=0),
    sc.ComboItem(sound="01 冰冰冰.wav", trig=sc.TRIG_PREV_START, delay_ms=200,
                 semitones=2, rate=1.1, rand_semi=0.5, rand_rate=0.05),
    sc.ComboItem(sound="01 冰冰冰.wav", trig=sc.TRIG_PREV_START, delay_ms=200,
                 semitones=4, rate=1.2, clip_start_ms=100, clip_len_ms=400),
    sc.ComboItem(sound="04 叹息.wav", trig=sc.TRIG_PREV_END, delay_ms=-150,
                 semitones=-3, gain=0.8),
    sc.ComboItem(sound="不存在.wav", trig=sc.TRIG_COMBO, delay_ms=900),
]
cdef.rate = 1.05
cdef.semitones = 1.0
cdef.rand_rate = 0.05
cdef.rand_semi = 0.5
cdef.cooldown_ms = 300
cdef.max_voices = 3
cfg.order.append(cfg.combo_key(cdef.cid))
cfg.save()

bank = sr.SoundBank(8, scfg=cfg)
engine = sr.AudioEngine(bank, dict(sr.DEFAULT_CONFIG))

import settings_window as sw

win = sw.SettingsWindow(dict(sr.DEFAULT_CONFIG), cfg, bank, engine)
win.resize(1180, 800)
win.show()
app.processEvents()

dlg = sw.ComboEditorDialog(cfg, cdef, engine, win)
dlg.show()
app.processEvents()
dlg.table.selectRow(2)
app.processEvents()
out = ROOT / "_tests" / "_shot_combo_v072.png"
dlg.grab().save(str(out))
print("saved", out, out.stat().st_size // 1024, "KB", dlg.size().toTuple())

# 布局体检：控件被压得比 sizeHint 窄 = 文字会被截掉
print("\n--- 控件宽度 vs 需要宽度 ---")
bad = []
names = ["spn_start", "spn_len", "spn_rsemi", "spn_rrate", "spn_orate",
         "spn_osemi", "spn_orrate", "spn_osemi_r", "spn_cool", "spn_voices"]
for n in names:
    w = getattr(dlg, n)
    need = w.sizeHint().width()
    if w.width() < need - 2:
        bad.append(f"{n}: {w.width()} < {need}")
print("被压缩的控件：", bad or "无")
print("对话框 sizeHint:", dlg.sizeHint().toTuple(), "实际:", dlg.size().toTuple())
print("最小可用:", dlg.minimumSizeHint().toTuple())

# 深浅色检查：QDoubleSpinBox 现在应该也是深底
from PySide6.QtGui import QColor
for n in ("spn_osemi", "spn_rsemi"):
    w = getattr(dlg, n)
    img = w.grab().toImage()
    c = img.pixelColor(3, 3)
    print(f"{n} 背景色 {c.name()}")
