"""v0.6.2 新增功能测试：固定变调 + 开机自启动（源码模式下的安全部分）。

固定变调重点：
1. 配置往返不丢 pitch_fixed 字段、越界值被收回来
2. 引擎 play() 在 fixed 模式下每次都变同样的半音（不累计、不看窗口）
3. 老配置（没有 pitch_fixed 字段）读进来默认 0 = 行为不变

自启动重点（源码模式不支持写注册表，只测安全面）：
4. autostart_supported() 在源码模式返回 False
5. sync_autostart 在源码模式下什么都不做、不炸
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

import sr_roulette as sr
import sounds_config as sc

FAILS = []


def check(ok, name, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(name)


def tone(freq: float, seconds: float, rate: int = 48000) -> np.ndarray:
    n = int(seconds * rate)
    t = np.arange(n) / rate
    x = (0.4 * np.sin(2 * math.pi * freq * t)).astype(np.float32)
    return np.stack([x, x], axis=1)


def dominant(x: np.ndarray, rate: int = 48000) -> float:
    mono = x[:, 0]
    a, b = len(mono) // 4, len(mono) * 3 // 4
    seg = mono[a:b] * np.hanning(b - a)
    spec = np.abs(np.fft.rfft(seg))
    freqs = np.fft.rfftfreq(len(seg), 1.0 / rate)
    return float(freqs[int(np.argmax(spec))])


# ================ 1. 配置层 ================
print("=== 1. 固定变调配置 ===")
tmp = Path(tempfile.mkdtemp())
p = tmp / "sounds.json"
cfg = sc.SoundsConfig(p)
cfg.load()
cfg.order = ["a.wav"]
cfg.items["a.wav"] = sc.SoundSetting(pitch_mode=sc.PITCH_FIXED, pitch_fixed=-5.5)
cfg.save()
cfg2 = sc.SoundsConfig(p)
cfg2.load()
st = cfg2.setting("a.wav")
check(st.pitch_mode == sc.PITCH_FIXED, "fixed 模式往返保存", st.pitch_mode)
check(abs(st.pitch_fixed - (-5.5)) < 1e-6, "pitch_fixed 往返保存", str(st.pitch_fixed))

# 越界收回
s_big = sc.SoundSetting(pitch_mode=sc.PITCH_FIXED, pitch_fixed=99.0).clamped()
check(s_big.pitch_fixed == 24.0, "越界正数收到 +24", str(s_big.pitch_fixed))
s_small = sc.SoundSetting(pitch_fixed=-99.0).clamped()
check(s_small.pitch_fixed == -24.0, "越界负数收到 -24", str(s_small.pitch_fixed))

# 老配置没有 pitch_fixed 字段
old = {"version": 1, "order": ["a.wav"], "outer_slots": [None] * sc.OUTER_MAX,
       "items": {"a.wav": {"volume": 1.0, "pitch_mode": "up", "pitch_step": 2.0}}}
p2 = tmp / "old.json"
p2.write_text(json.dumps(old), encoding="utf-8")
cfg3 = sc.SoundsConfig(p2)
cfg3.load()
check(cfg3.setting("a.wav").pitch_fixed == 0.0, "老配置缺字段 -> 默认 0（行为不变）")
check(cfg3.setting("a.wav").pitch_step == 2.0, "老配置其他字段照常读取")

# ================ 2. 引擎层 ================
print("\n=== 2. 固定变调播放 ===")
snd = tmp / "sounds"
snd.mkdir(exist_ok=True)
import wave

def write_wav(path: Path, freq: float, seconds: float = 0.6):
    rate = 48000
    x = tone(freq, seconds, rate)
    pcm = (np.clip(x[:, 0], -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())

write_wav(snd / "a.wav", 440.0)

from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)

scfg_t = sc.SoundsConfig(tmp / "engine.json")
scfg_t.load()
scfg_t.sync([p.name for p in snd.iterdir()])
scfg_t.items["a.wav"] = sc.SoundSetting(pitch_mode=sc.PITCH_FIXED, pitch_fixed=5.0)
scfg_t.save()

sr.SOUNDS_DIR = snd   # SoundBank 读的是模块级 SOUNDS_DIR，指到临时目录
bank = sr.SoundBank(8, scfg=scfg_t)
bank.reload()
n = len(bank)
check(n == 1, "假音效已进库", str(n))

engine = sr.AudioEngine(bank, dict(sr.DEFAULT_CONFIG))
mix = engine._mixers_all()[0]
mix.voices.clear()

# 连按 3 次：每次都应该是同样的 440 -> 587.33Hz（A4 -> D5，升 5 半音）
expect = 440.0 * (2 ** (5.0 / 12.0))
ok_all = True
freqs = []
for i in range(3):
    check(engine.play(0) is True, f"第 {i+1} 次播放成功")
    a = np.frombuffer(mix.readData(48000 * 2 * 4), dtype=np.float32).reshape(-1, 2)
    f = dominant(a)
    freqs.append(round(f, 1))
    if abs(f - expect) > 8.0:
        ok_all = False
check(ok_all, "连按 3 次每次都是 440->%.1fHz（不累计不漂移）" % expect, str(freqs))

# 对照：固定变调不应受连击窗口影响（隔很久按也一样——用时间戳伪造）
engine._last_at[0] = 0.0   # 伪造"上次播放是很久以前"
check(engine.play(0) is True, "超窗后播放成功")
a = np.frombuffer(mix.readData(48000 * 2 * 4), dtype=np.float32).reshape(-1, 2)
f = dominant(a)
check(abs(f - expect) <= 8.0, "超窗后仍是同一音高", f"{f:.1f}Hz vs {expect:.1f}Hz")
engine.stop_all()

# 固定负半音
scfg_t.items["a.wav"] = sc.SoundSetting(pitch_mode=sc.PITCH_FIXED, pitch_fixed=-12.0)
mix.voices.clear()
check(engine.play(0) is True, "降 12 半音播放成功")
a = np.frombuffer(mix.readData(48000 * 2 * 4), dtype=np.float32).reshape(-1, 2)
f = dominant(a)
check(abs(f - 220.0) <= 5.0, "降 12 半音 -> 220Hz", f"{f:.1f}Hz")
engine.stop_all()

# ================ 3. 自启动（安全面） ================
print("\n=== 3. 开机自启动 ===")
check(sr.autostart_supported() in (True, False), "autostart_supported 返回布尔")
if not getattr(sys, "frozen", False):
    check(sr.autostart_supported() is False, "源码模式不支持自启")
    try:
        sr.sync_autostart(dict(sr.DEFAULT_CONFIG))   # 不应抛异常、不应写注册表
        check(True, "源码模式 sync_autostart 无副作用不炸")
    except Exception as exc:
        check(False, "源码模式 sync_autostart 无副作用不炸", repr(exc))

print()
if FAILS:
    print(f"结果：{len(FAILS)} 项失败")
    for f_ in FAILS:
        print("  -", f_)
    sys.exit(1)
print("结果：全部通过")
