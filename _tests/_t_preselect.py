"""回归：预选模式 + 轻按动作归一（v0.9.3）。

跑法：python _t_preselect.py
"""

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402
from sounds_config import SoundsConfig, WheelDef  # noqa: E402

app = QApplication.instance() or QApplication([])

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


class _Clock:
    t = 1000.0

    def __call__(self):
        return _Clock.t

    @staticmethod
    def add(sec):
        _Clock.t += sec


_TIME = _Clock()
time.monotonic = _TIME


class FakeWheel:
    def __init__(self):
        self.active = False
        self.raw = None
        self.want = 1

    def show_wheel(self):
        self.active = True

    def hide_wheel(self):
        self.active = False

    def commit(self):
        self.active = False
        return self.want

    def poll_selection(self):
        pass


class FakeBank:
    def __init__(self, scfg, keys):
        self.scfg = scfg
        self.keys = keys

    def __len__(self):
        return len(self.keys)

    def full_at(self, idx):
        return self.keys[idx] if 0 <= idx < len(self.keys) else ""

    def name_at(self, idx):
        return "名字"


class FakeAudio:
    def __init__(self, scfg):
        self.bank = FakeBank(scfg, ["AAA.wav", "BBB.wav"])
        self.played = []
        self.named = []
        self.repeated = 0
        self.nexted = 0

    def play(self, idx, token=0):
        self.played.append(idx)
        return True

    def play_named(self, name, token=0):
        self.named.append(name)
        return True

    def play_repeat_last(self, token=0):
        self.repeated += 1
        return True

    def play_next(self, token=0):
        self.nexted += 1
        return True

    def new_token(self):
        return 1

    def stop_token(self, token):
        pass

    def stop_all(self):
        pass

    def reset_pitch(self):
        pass


def build(preselect=False, tap="auto"):
    scfg = SoundsConfig(Path(os.devnull))
    scfg.wheels = [
        WheelDef(wid="w1", name="轮盘 1", order=["AAA.wav", "BBB.wav"]),
        # 第二套留着给「选中之后又切了盘」那组用
        WheelDef(wid="w2", name="轮盘 2", order=["CCC.wav"]),
    ]
    scfg._cur = "w1"
    cfg = dict(sr.DEFAULT_CONFIG)
    cfg["hotkey"] = "y"
    cfg["hold_ms"] = 60
    cfg["switch_key"] = ""
    cfg["repeat_last_key"] = ""
    cfg["cycle_key"] = ""
    cfg["tap_action"] = tap
    cfg["preselect_mode"] = preselect
    state = {}
    wheel = FakeWheel()
    audio = FakeAudio(scfg)
    p = sr.InputPoller(cfg, wheel, audio, None)
    p._down = lambda name: bool(state.get(name, False))
    p.rebuild_bindings()
    noted = []
    p.on_pending_changed = lambda pending, idx: noted.append((pending, idx))
    return p, wheel, audio, state, noted


def press(p, state, key, on):
    state[key] = on
    p.tick()


print("=== A 预选关着：松手就播（老行为不变）===")
p, wheel, audio, state, noted = build(preselect=False)
press(p, state, "y", True)
_Clock.add(0.10)
p.tick()
press(p, state, "y", False)
check(audio.played == [1], "松手放了选中的那格", str(audio.played))
check(p._pending is None, "不会留下待播的东西", str(p._pending))
check(not noted, "不弹「已选中」提示", str(noted))

print()
print("=== B 预选开着：松手只选中 ===")
p, wheel, audio, state, noted = build(preselect=True)
press(p, state, "y", True)
_Clock.add(0.10)
p.tick()
press(p, state, "y", False)
check(audio.played == [], "松手不出声", str(audio.played))
check(p._pending == ("w1", "BBB.wav"), "记下了选中的那一格", str(p._pending))
check(bool(noted) and noted[0][1] == 1, "弹了「已选中」提示（带槽位号）", str(noted))

print()
print("=== C 再单击一次：播放刚才选中的 ===")
press(p, state, "y", True)
press(p, state, "y", False)      # 没到 hold_ms
check(audio.named == ["BBB.wav"], "放的是刚才选中的那个，不是第一个", str(audio.named))
check(p._pending is None, "待播的清空了", str(p._pending))
check(audio.repeated == 0, "没有再走「播放上次那个」", str(audio.repeated))

print()
print("=== D 选中之后切了盘：那一格不作数 ===")
p, wheel, audio, state, noted = build(preselect=True)
press(p, state, "y", True)
_Clock.add(0.10)
p.tick()
press(p, state, "y", False)
check(p._pending == ("w1", "BBB.wav"), "先选中", str(p._pending))
p.audio.bank.scfg._cur = "w2"        # 模拟切到另一套盘
press(p, state, "y", True)
press(p, state, "y", False)
check(audio.named == [], "别的盘上的待播不放", str(audio.named))
check(audio.repeated == 1, "退回普通的「播放上次那个」", str(audio.repeated))

print()
print("=== E 老配置的 repeat_last 并进 auto ===")
p, wheel, audio, state, noted = build(preselect=False, tap="repeat_last")
press(p, state, "y", True)
press(p, state, "y", False)
check(audio.repeated == 1, "老配置照样能「重复上一个」", str(audio.repeated))

print()
print("=== F 轻按选「什么都不做」：那就不出声 ===")
p, wheel, audio, state, noted = build(preselect=False, tap="none")
press(p, state, "y", True)
press(p, state, "y", False)
check(audio.repeated == 0 and audio.nexted == 0 and audio.played == [],
      "什么都不做", f"{audio.repeated} {audio.nexted} {audio.played}")

print()
print("=== G 默认值 ===")
check(sr.DEFAULT_CONFIG.get("tap_action") == "auto",
      "轻按默认是「播放选中 / 上次那个」", str(sr.DEFAULT_CONFIG.get("tap_action")))
check(sr.DEFAULT_CONFIG.get("preselect_mode") is False,
      "预选模式默认关（升级后手感不变）", str(sr.DEFAULT_CONFIG.get("preselect_mode")))

print()
print("=" * 56)
if BAD:
    print(f"结果：{len(BAD)} 项失败 / 共 {len(OK) + len(BAD)} 项")
    for n in BAD:
        print("  FAIL", n)
    raise SystemExit(1)
print(f"结果：全部通过（{len(OK)} 项）")
