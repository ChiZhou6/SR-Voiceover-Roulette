"""回归：组合条目 -> 普通音效 切换后，变调/速度两排必须完整回来。

v0.7.2 的 bug：组合模式把 pitch_mode / speed_mode / speed_step 藏了，
切回普通音效时没有显式放回来，Qt 的隐藏是粘性的，于是那一排永久消失。
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
from PySide6.QtWidgets import QApplication

import sounds_config as sc
import sr_roulette as sr

RATE = 48000
app = QApplication.instance() or QApplication([])

FAILS = []


def check(ok, what, detail=""):
    print(("PASS  " if ok else "FAIL  ") + what + (f"   [{detail}]" if detail and not ok else ""))
    if not ok:
        FAILS.append(what)


def write_wav(path, seconds, freq=440.0):
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
for name in ("01 冰冰冰", "02 哇哦"):
    write_wav(snd / f"{name}.wav", 1.0)
sr.SOUNDS_DIR = snd

cfg = sc.SoundsConfig(tmp / "sounds.json")
cfg.load()
cfg.sync([p.name for p in snd.iterdir()])
combo = cfg.new_combo("新组合")
combo.items = [sc.ComboItem(sound="01 冰冰冰.wav", trig=sc.TRIG_COMBO)]
cfg.save()

import settings_window as sw

d = sw.SlotDetail(cfg)
PITCH_ROW = ("lbl_pitch", "pitch_mode", "pitch_step", "pitch_fixed")
SPEED_ROW = ("lbl_speed", "speed_mode", "speed_step")


def vis(names):
    return {n: (not getattr(d, n).isHidden()) for n in names}


def pitch_ok():
    """变调排完整的定义：标签 + 模式下拉都在，且 ±N / 固定值两个里恰好露一个。"""
    v = vis(("lbl_pitch", "pitch_mode", "pitch_step", "pitch_fixed"))
    return (v["lbl_pitch"] and v["pitch_mode"]
            and (v["pitch_step"] ^ v["pitch_fixed"]))


# 初始：普通音效，两排都在
d.set_sound("01 冰冰冰.wav")
check(pitch_ok(), "普通音效：变调排齐全", str(vis(PITCH_ROW)))
check(all(vis(SPEED_ROW).values()), "普通音效：速度排齐全", str(vis(SPEED_ROW)))

# 切到组合：整排收起，只留组合说明
d.set_sound(cfg.combo_key(combo.cid))
check(not getattr(d, "pitch_mode").isVisibleTo(d), "组合：变调排藏起")
check(not getattr(d, "speed_mode").isVisibleTo(d), "组合：速度排藏起")
check(getattr(d, "lbl_combo_hint").isVisibleTo(d), "组合：显示组合说明")
check(getattr(d, "btn_combo").isVisibleTo(d), "组合：出现「编辑组合」按钮")

# 切回普通音效 —— 这就是用户报的 bug
d.set_sound("02 哇哦.wav")
check(pitch_ok(), "切回普通音效后变调排完整", str(vis(PITCH_ROW)))
check(all(vis(SPEED_ROW).values()), "切回普通音效后速度排完整", str(vis(SPEED_ROW)))
check(not getattr(d, "lbl_combo_hint").isVisibleTo(d), "切回后组合说明消失")

# 再切一轮，确认反复横跳也不会退化
for _ in range(3):
    d.set_sound(cfg.combo_key(combo.cid))
    d.set_sound("01 冰冰冰.wav")
check(pitch_ok(), "反复切换 3 轮后变调排仍完整", str(vis(PITCH_ROW)))
check(all(vis(SPEED_ROW).values()), "反复切换 3 轮后速度排仍完整", str(vis(SPEED_ROW)))

# 固定变调模式：pitch_step 让位给 pitch_fixed，但仍然必须有且只有一个
st = cfg.setting("01 冰冰冰.wav")
st.pitch_mode = sc.PITCH_FIXED
st.pitch_fixed = 3.0
d.set_sound("01 冰冰冰.wav")
check(getattr(d, "pitch_fixed").isVisibleTo(d), "固定变调：显示半音输入框")
check(not getattr(d, "pitch_step").isVisibleTo(d), "固定变调：隐藏 ±N 下拉")
check(getattr(d, "pitch_mode").isVisibleTo(d), "固定变调：模式下拉仍在")
st.pitch_mode = sc.PITCH_NONE
st.pitch_fixed = 0.0

# 面板里不能出现被压扁/重叠：每排控件高度都得 > 0
d.set_sound("01 冰冰冰.wav")
app.processEvents()
zero = [n for n in PITCH_ROW + SPEED_ROW
        if not getattr(d, n).isHidden() and getattr(d, n).height() <= 0]
check(not zero, "没有高度为 0 的控件（会被压成一条线）", str(zero))

print()
if FAILS:
    print(f"失败 {len(FAILS)} 项：")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("全部通过")
