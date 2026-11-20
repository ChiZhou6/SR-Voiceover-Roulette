"""回归：停止 / 暂停时的淡出（v0.9.3）。

跑法：python _t_stop_fade.py
"""

import sys
from pathlib import Path

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
    """只记下 stop_all 收到的淡出时长。"""

    def __init__(self):
        self.calls = []

    def stop_all(self, fade_ms: float = 12.0) -> None:
        self.calls.append(float(fade_ms))


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
