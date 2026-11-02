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
def write_wav(path, seconds, freq=440.0):
    n = int(seconds * RATE); t = np.arange(n) / RATE
    x = (0.4 * np.sin(2*np.pi*freq*t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(x.tobytes())

tmp = Path(tempfile.mkdtemp()); snd = tmp/"sounds"; snd.mkdir()
for name, sec, f in (("01 冰冰冰", 1.25, 440), ("02 哇哦", 2.0, 330), ("03 好耶", 0.8, 550),
                     ("04 叹息", 1.6, 220), ("05 笑声", 2.4, 660)):
    write_wav(snd/f"{name}.wav", sec, f)
sr.SOUNDS_DIR = snd
cfg = sc.SoundsConfig(tmp/"sounds.json"); cfg.load(); cfg.sync([p.name for p in snd.iterdir()])
cdef = cfg.new_combo("体检")
cdef.items = [
    sc.ComboItem(sound="01 冰冰冰.wav", trig=sc.TRIG_COMBO, delay_ms=0),
    sc.ComboItem(sound="01 冰冰冰.wav", trig=sc.TRIG_PREV_START, delay_ms=200, semitones=2, rate=1.1),
    sc.ComboItem(sound="01 冰冰冰.wav", trig=sc.TRIG_PREV_START, delay_ms=200, semitones=4, rate=1.2,
                 clip_start_ms=100, clip_len_ms=400),
    sc.ComboItem(sound="04 叹息.wav", trig=sc.TRIG_PREV_END, delay_ms=-150, semitones=-3, gain=0.8),
    sc.ComboItem(sound="不存在.wav", trig=sc.TRIG_COMBO, delay_ms=900),
]
cdef.rate = 1.05
cfg.order.append(cfg.combo_key(cdef.cid)); cfg.save()
bank = sr.SoundBank(8, scfg=cfg)
engine = sr.AudioEngine(bank, dict(sr.DEFAULT_CONFIG))
import settings_window as sw
dlg = sw.ComboEditorDialog(cfg, cdef, engine, None)
for i, it in enumerate(cdef.items):
    print(i + 1, "trig", it.trig, "delay", it.delay_ms,
          "dur %.2f" % dlg._member_duration(it), "src %.2f" % sr.item_src_duration(it))
print("plan:", [(i + 1, round(s, 2)) for i, s in dlg._preview_plan()])
print("spans:", dlg.timeline.spans)
print("total: %.2f" % dlg.timeline.total)
