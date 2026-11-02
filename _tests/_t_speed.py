"""变速（保持音调）测试。

重点不是"能不能变长变短"，而是：
1. 变快变慢之后**音高必须还是原来那个音高**（这正是它和"变调"的区别）
2. 连击累计、上限、归零这些逻辑跟变调完全一致（共用 combo_value）
3. 老配置没有 speed_* 字段时行为跟以前一模一样
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    """取中间一段做 FFT，返回主频。躲开首尾，免得淡入淡出干扰。"""
    mono = x[:, 0]
    a, b = len(mono) // 4, len(mono) * 3 // 4
    seg = mono[a:b] * np.hanning(b - a)
    spec = np.abs(np.fft.rfft(seg))
    freqs = np.fft.rfftfreq(len(seg), 1.0 / rate)
    return float(freqs[int(np.argmax(spec))])


print("=== 1. 变快：更短，音高不变 ===")
src = tone(440.0, 1.0)
fast = sr.time_stretch(src, 1.5)
ratio = len(src) / len(fast)
check(abs(ratio - 1.5) < 0.08, "1.5 倍速 -> 时长缩到 1/1.5", f"实测 {ratio:.3f}")
f_fast = dominant(fast)
check(abs(f_fast - 440.0) < 6.0, "变快后主频仍是 440Hz", f"{f_fast:.1f}Hz")
check(fast.dtype == np.float32 and fast.shape[1] == 2, "输出仍是立体声 float32", str(fast.shape))

print("\n=== 2. 变慢：更长，音高不变 ===")
slow = sr.time_stretch(src, 0.7)
ratio = len(src) / len(slow)
check(abs(ratio - 0.7) < 0.06, "0.7 倍速 -> 时长拉到 1/0.7", f"实测 {ratio:.3f}")
f_slow = dominant(slow)
check(abs(f_slow - 440.0) < 6.0, "变慢后主频仍是 440Hz", f"{f_slow:.1f}Hz")

print("\n=== 3. 对照：重采样（pitch_shift）会改音高，两者必须不一样 ===")
tape = sr.pitch_shift(src, 7.0)   # 升 7 个半音
check(abs(dominant(tape) - 440.0) > 100, "重采样确实改变了音高（本该如此）",
      f"{dominant(tape):.0f}Hz")
check(abs(dominant(fast) - 440.0) < 6.0, "变速不改变音高（这才是新功能）")

print("\n=== 4. 边界 ===")
check(sr.time_stretch(src, 1.0) is src, "rate=1.0 直接返回原对象，不做无谓计算")
tiny = tone(440.0, 0.02)
check(sr.time_stretch(tiny, 1.5) is tiny, "太短的音效（<4 帧）原样返回")
huge = sr.time_stretch(src, 5.0)
r = len(src) / len(huge)
check(abs(r - 2.0) < 0.15, "rate 被夹到 2.0（防止拉成一声爆响）", f"实测 {r:.2f}")
tiny2 = sr.time_stretch(src, 0.1)
r2 = len(src) / len(tiny2)
check(abs(r2 - 0.5) < 0.05, "rate 被夹到 0.5（防止拖成糊音）", f"实测 {r2:.2f}")
check(np.abs(fast).max() <= 1.0, "不会因叠加而削波", f"peak={np.abs(fast).max():.3f}")

print("\n=== 5. 正弦波拉伸后不该有断裂（相邻样本差不超过原始最大差） ===")
d_src = np.abs(np.diff(src[:, 0])).max()
d_out = np.abs(np.diff(fast[:, 0])).max()
check(d_out <= d_src * 3.0, "拼接处没有爆点", f"原始 {d_src:.4f} / 输出 {d_out:.4f}")

print("\n=== 6. 连击累计（和变调共用同一套） ===")
check(sr.combo_value(0.0, 0.1, 0.6, True) == 0.1, "窗口内加一档")
check(abs(sr.combo_value(0.5, 0.1, 0.6, True) - 0.6) < 1e-9, "到上限就停住")
check(abs(sr.combo_value(-0.5, -0.1, 0.6, True) + 0.6) < 1e-9, "变慢方向同样到上限")
check(sr.combo_value(0.3, 0.1, 0.6, False) == 0.0, "超时归零")
check(sr.combo_value(0.3, 0.0, 0.6, True) == 0.0, "档位为 0 时不动")

print("\n=== 7. 配置默认值 / 越界收敛 ===")
st = sc.SoundSetting()
check(st.speed_mode == sc.SPEED_NONE, "默认不改速度（老配置行为不变）")
check(abs(st.speed_step - 0.10) < 1e-9 and abs(st.speed_limit - 0.60) < 1e-9,
      "默认每次 10%、上限 60%")
bad = sc.SoundSetting(speed_mode="warp", speed_step=9.0, speed_limit=-3.0).clamped()
check(bad.speed_mode == sc.SPEED_NONE, "非法模式收敛成 none")
check(abs(bad.speed_step - 0.40) < 1e-9, "单次幅度夹到 40%", f"{bad.speed_step}")
check(bad.speed_limit == 0.0, "上限夹到 0", f"{bad.speed_limit}")
check(set(sc.SPEED_MODES) == {"none", "up", "down"}, "只有三种速度模式")
check(all(m in sc.SPEED_MODE_LABEL for m in sc.SPEED_MODES), "每种模式都有中文说明")

print("\n=== 8. 变速和变调叠加：各自独立 ===")
mix = sr.pitch_shift(sr.time_stretch(src, 1.3), 0.0)
check(abs(dominant(mix) - 440.0) < 6.0, "只变速：音高不动、时长短了",
      f"{len(src) / len(mix):.2f}x, {dominant(mix):.0f}Hz")
both = sr.pitch_shift(sr.time_stretch(src, 0.8), 12.0)
check(dominant(both) > 800, "变速+升调叠加后音高明显变高", f"{dominant(both):.0f}Hz")

print("\n=== 9. 拉伸缓存：同一档速度不重复算 ===")
class _FakeEngine:
    """只借 _stretched 这个方法用，不真的建音频链路。"""
    _stretched = sr.AudioEngine._stretched

    def __init__(self):
        self._stretch_cache = {}


eng = _FakeEngine()
half = tone(440.0, 0.5)
a = eng._stretched(0, half, 1.3)
b = eng._stretched(0, half, 1.3)
check(a is b, "同样的（槽位, 速度）第二次直接取缓存")
check(len(a) < len(half), "缓存里存的是拉伸后的波形", f"{len(half)} -> {len(a)}")
c = eng._stretched(0, half, 0.8)
check(c is not a, "换了速度重新算")
for i in range(40):                      # 塞爆缓存看有没有上限
    eng._stretched(i, half, 1.1)
check(len(eng._stretch_cache) <= 24, "缓存有上限，不会无限涨",
      f"{len(eng._stretch_cache)}")

print()
if FAILS:
    print(f"FAILED: {len(FAILS)} 项 -> {FAILS}")
    sys.exit(1)
print("全部通过")
