"""回归：停止 / 暂停时的淡出（v0.9.3）。

跑法：python _t_stop_fade.py
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sr_roulette as sr  # noqa: E402

OK = []
BAD = []


def check(cond, name, detail=""):
    if cond:
        OK.append(name)
        print(f"  PASS  {name}")
    else:
        BAD.append(name)
        print(f"  FAIL  {name}   {detail}")
    return bool(cond)


class FakeMix:
    """只记下各路停止收到的淡出时长。"""

    def __init__(self):
        self.calls = []
        self.tokens = []
        self.slots = []

    def stop_all(self, fade_ms: float = 12.0) -> None:
        self.calls.append(float(fade_ms))

    def stop_token(self, token: int, fade_ms: float = 12.0) -> int:
        self.tokens.append(float(fade_ms))
        return 1

    def stop_slot(self, idx: int, fade_ms: float = 12.0) -> int:
        self.slots.append(float(fade_ms))
        return 1


def make_engine(**cfg):
    """跳过 __init__，只留 stop_all 需要的那几样。"""
    eng = sr.AudioEngine.__new__(sr.AudioEngine)
    eng.cfg = dict(cfg)
    m1, m2 = FakeMix(), FakeMix()
    eng._mixers_all = lambda: [m1, m2]
    return eng, (m1, m2)


print("=== A. 开关关着：还是原来的 12ms ===")
eng, (m1, m2) = make_engine(stop_fade_enabled=False, stop_fade_ms=800)
eng.stop_all()
check(m1.calls == [12.0] and m2.calls == [12.0],
      "两个出口都用 12ms", f"{m1.calls} {m2.calls}")

print()
print("=== B. 开关开着：按配置的时长 ===")
eng, (m1, m2) = make_engine(stop_fade_enabled=True, stop_fade_ms=800)
eng.stop_all()
check(m1.calls == [800.0], "耳机那一路按 800ms 淡出", str(m1.calls))
check(m2.calls == [800.0], "虚拟声卡那一路也按 800ms 淡出", str(m2.calls))

print()
print("=== C. 边界 ===")
eng, (m1, _m2) = make_engine(stop_fade_enabled=True, stop_fade_ms=0)
eng.stop_all()
check(m1.calls == [0.0], "设成 0 就是立刻切断（Mixer 那边会直接清空）", str(m1.calls))

eng, (m1, _m2) = make_engine(stop_fade_enabled=True, stop_fade_ms=99999)
eng.stop_all()
check(m1.calls == [5000.0], "超大值夹到 5 秒，别让一声停不下来", str(m1.calls))

eng, (m1, _m2) = make_engine(stop_fade_enabled=True, stop_fade_ms="坏值")
eng.stop_all()
check(m1.calls and m1.calls[0] == 400.0, "配置坏了退回 400ms，不崩", str(m1.calls))

eng, (m1, _m2) = make_engine(stop_fade_enabled=True)
eng.stop_all()
check(m1.calls and m1.calls[0] == 400.0, "没写时长时用默认 400ms", str(m1.calls))

print()
print("=== E. 停止键 / 长按松手 / 连击打断 ===")
eng, (m1, _m2) = make_engine(stop_fade_enabled=True, stop_fade_ms=800)
eng.bank = SimpleNamespace(index_of_name=lambda name: 3)
eng.stop_token(7)
check(m1.tokens == [800.0], "长按松手（stop_token）也按 800ms", str(m1.tokens))
eng.stop_slot(3)
check(m1.slots == [800.0], "条件停止键（stop_slot）也按 800ms", str(m1.slots))
m1.slots.clear()
check(eng.stop_named("x") >= 1, "stop_named 找得到槽位就停")
check(m1.slots == [800.0], "stop_named 走同一套淡出", str(m1.slots))

m1.slots.clear()
eng.stop_slot(3, 12.0)
check(m1.slots == [12.0], "连击打断能显式压回 12ms，不被淡出设置拖长", str(m1.slots))

eng, (m1, _m2) = make_engine(stop_fade_enabled=False, stop_fade_ms=800)
eng.bank = SimpleNamespace(index_of_name=lambda name: 3)
eng.stop_token(7)
eng.stop_slot(3)
check(m1.tokens == [12.0] and m1.slots == [12.0],
      "开关关着时，各路都退回 12ms 防爆音", f"{m1.tokens} {m1.slots}")

print()
print("=== F. 长淡出的波形：单调下降，不是一块一块往回弹 ===")
fmt = sr.QAudioFormat()
fmt.setSampleRate(48000)
fmt.setChannelCount(1)
fmt.setSampleFormat(sr.QAudioFormat.SampleFormat.Float)
mix = sr.Mixer(fmt)
mix.trigger(np.ones((48000, 1), dtype=np.float32))     # 1 秒的满幅波形
mix.stop_all(400)                                       # 400ms 淡出 = 19200 帧
peaks = []
for _ in range(120):                                    # 每块 512 帧 ≈ 10.7ms
    data = mix.readData(512 * 4)
    arr = np.frombuffer(data, dtype=np.float32)
    peaks.append(float(np.abs(arr).max()) if arr.size else 0.0)
loud = peaks[:40]                                       # 前 400ms 还在淡出
check(loud[1] <= loud[0] + 1e-6, "第二块没比第一块响", f"{loud[0]:.4f} -> {loud[1]:.4f}")
back = [(i, loud[i - 1], loud[i]) for i in range(1, len(loud)) if loud[i] > loud[i - 1] + 1e-6]
check(not back, "淡出全程没有回升（旧实现每块都从 1.0 重来，会出现锯齿）",
      str(back[:3]))
check(abs(loud[0] - loud[-1]) > 0.3, "确实一路降下来了",
      f"{loud[0]:.3f} -> {loud[-1]:.3f}")
check(peaks[-1] < 1e-3, "400ms 之后彻底静音", str(peaks[-1]))
check(not mix.playing, "淡完的声部已经摘掉，不会一直占着")

print()
print("=== D. 默认配置是关的（升级后不会突然变味）===")
check(sr.DEFAULT_CONFIG.get("stop_fade_enabled") is False,
      "默认不开启", str(sr.DEFAULT_CONFIG.get("stop_fade_enabled")))
check(int(sr.DEFAULT_CONFIG.get("stop_fade_ms", 0)) == 400,
      "默认时长 400ms", str(sr.DEFAULT_CONFIG.get("stop_fade_ms")))

print()
print("=" * 56)
if BAD:
    print(f"结果：{len(BAD)} 项失败 / 共 {len(OK) + len(BAD)} 项")
    for n in BAD:
        print("  FAIL", n)
    raise SystemExit(1)
print(f"结果：全部通过（{len(OK)} 项）")
