"""回归：四种触发方式 + 条件解锁。

覆盖用户 2026-11-06 提的那套规则（AAA 组合 / B 音效共用一个键）：
    按 G 之前点左键 → 什么都不该发生
    按 G 之后长按左键 → AAA 起播（带 token）
    松手 → AAA 按 token 停掉，同时 B 响一次
    4.9 秒才按下也照样能用（解锁时间只管"能不能触发"，不管"能不能播完"）
    解锁时间过了、次数用完 → 重新锁上
    长按连续触发整段按住只扣 1 次解锁

跑法：python _t_triggers.py
"""
import os
import sys
import time as _time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402
from sounds_config import (  # noqa: E402
    REPEAT_MS_MAX,
    TRIGGER_HOLD,
    TRIGGER_RELEASE,
    TRIGGER_REPEAT,
    TRIGGER_TAP,
    UNLOCK_KEY,
    SoundsConfig,
)

app = QApplication.instance() or QApplication([])

OK = []
BAD = []


def check(cond, name, detail=""):
    if cond:
        OK.append(name)
        print(f"PASS  {name}")
    else:
        BAD.append(name)
        print(f"FAIL  {name}   {detail}")


# ---------------------------------------------------------------- 假时钟
class _Clock:
    t = 1000.0

    def __call__(self):
        return _Clock.t

    @staticmethod
    def add(sec: float):
        _Clock.t += sec


_TIME = _Clock()
_time.monotonic = _TIME      # 整个进程都走这个假时钟，测试不用真的 sleep


# ---------------------------------------------------------------- 假对象
class FakeWheel:
    def __init__(self):
        self.active = False
        self.raw = None

    def show_wheel(self):
        self.active = True

    def hide_wheel(self):
        self.active = False

    def commit(self):
        self.active = False
        return None

    def poll_selection(self):
        pass


class FakeAudio:
    def __init__(self, scfg):
        self.bank = SimpleNamespace(scfg=scfg)
        self.calls = []       # [(音效键, token)]
        self.stopped = []     # [token]
        self._tok = 0

    def play_named(self, name, token=0):
        self.calls.append((name, token))
        return True

    def play_repeat_last(self, token=0):
        return False

    def play_next(self, token=0):
        return False

    def new_token(self):
        self._tok += 1
        return self._tok

    def stop_token(self, token):
        self.stopped.append(token)

    def stop_all(self):
        pass

    def reset_pitch(self):
        pass


def build():
    scfg = SoundsConfig(Path(os.devnull))       # 不落盘，纯内存
    scfg.order = ["AAA.wav", "B.wav"]
    scfg.items = {}
    return scfg


cfg = dict(sr.DEFAULT_CONFIG)
cfg["hotkey"] = "y"
cfg["hold_ms"] = 60
cfg["switch_key"] = ""
cfg["repeat_last_key"] = ""
cfg["cycle_key"] = ""

state = {}
wheel = FakeWheel()

print("=== A 数据层默认值与取值 ===")

scfg = build()
st = scfg.setting("AAA.wav")
check(st.trigger_mode == TRIGGER_TAP, "默认是点击触发")
check(st.unlock_mode == "none", "默认无条件")
check(st.repeat_ms == 200, "默认连发间隔 200ms")

st.trigger_mode = "瞎写"
st.unlock_ms = -5
st.repeat_ms = 99999
st2 = st.clamped()
check(st2.trigger_mode == TRIGGER_TAP, "非法触发方式回收成点击触发")
check(st2.unlock_ms == 0, "解锁时间不为负")
check(st2.repeat_ms == REPEAT_MS_MAX, "连发间隔夹在上限")


print()
print("=== B 一键多音效 / 解锁分组 ===")

scfg = build()
a = scfg.setting("AAA.wav")
a.hotkey = "mouse_left"
a.trigger_mode = TRIGGER_HOLD
a.unlock_mode = UNLOCK_KEY
a.unlock_key = "g"
a.unlock_ms = 5000
a.unlock_count = 0

b = scfg.setting("B.wav")
b.hotkey = "mouse_left"
b.trigger_mode = TRIGGER_RELEASE
b.unlock_mode = UNLOCK_KEY
b.unlock_key = "g"
b.unlock_ms = 0
b.unlock_count = 1

groups = scfg.hotkey_groups()
check(groups.get("mouse_left") == ["AAA.wav", "B.wav"],
      "左键同时挂住 AAA 和 B（以前只能挂一个）", str(groups))
unl = scfg.unlock_groups()
check(unl.get("g") == ["AAA.wav", "B.wav"], "G 一次解锁两个音效", str(unl))

audio = FakeAudio(scfg)
poller = sr.InputPoller(cfg, wheel, audio, None)
poller._down = lambda name: bool(state.get(name, False))


def press(key, on=True, p=None):
    state[key] = on
    (p or poller).tick()


def last():
    return audio.calls[-1] if audio.calls else (None, None)


def reset_calls():
    audio.calls.clear()
    audio.stopped.clear()


print()
print("=== C 用户案例：没按 G 直接点左键 ===")

reset_calls()
press("mouse_left", True)
press("mouse_left", False)
check(not audio.calls, "未解锁时按下+松手都无反应", str(audio.calls))


print()
print("=== D 按 G 之后长按左键 ===")

reset_calls()
press("g", True)
press("g", False)
press("mouse_left", True)
names = [c[0] for c in audio.calls]
check(names == ["AAA.wav"], "长按左键只响 AAA（B 是松手才响）", str(names))
tok = audio.calls[0][1] if audio.calls else 0
check(tok > 0, "长按触发带上了按次停止的编号", f"token={tok}")

press("mouse_left", False)
names = [c[0] for c in audio.calls]
check(names == ["AAA.wav", "B.wav"], "松手后 B 响了一次", str(names))
check(audio.stopped == [tok], "松手把 AAA 这次的声音整批停掉", str(audio.stopped))


print()
print("=== E 解锁时间 5 秒：4.9 秒时按下照样能用 ===")

reset_calls()
press("g", True)
press("g", False)
_Clock.add(4.9)
press("mouse_left", True)
names = [c[0] for c in audio.calls]
check(names == ["AAA.wav"], "解锁后 4.9 秒按下仍然能触发 AAA", str(names))
press("mouse_left", False)

reset_calls()
_Clock.add(0.5)          # 现在离上次按 G 已经 5.4 秒
press("mouse_left", True)
press("mouse_left", False)
check(not audio.calls, "过了 5 秒解锁时间就重新锁上", str(audio.calls))


print()
print("=== F 解锁次数：B 只能用 1 次 ===")

reset_calls()
press("g", True)
press("g", False)        # 重新解锁：B 有 1 次，AAA 5 秒内不限次
press("mouse_left", True)
press("mouse_left", False)   # 这一次用掉 B 的唯一一次
reset_calls()
_Clock.add(0.1)
press("mouse_left", True)    # 还在 AAA 的 5 秒窗口里
press("mouse_left", False)
names = [c[0] for c in audio.calls]
check("B.wav" not in names, "B 的次数用完就不再响", str(names))
check(names.count("AAA.wav") >= 1, "AAA 次数不限，窗口内还能响", str(names))


print()
print("=== G 重复按解锁键不叠加次数 ===")

reset_calls()
press("g", True)
press("g", False)
press("g", True)
press("g", False)
press("mouse_left", True)
press("mouse_left", False)   # 用掉 B 的 1 次
reset_calls()
press("mouse_left", True)
press("mouse_left", False)
names = [c[0] for c in audio.calls]
check("B.wav" not in names, "连按两次 G 也还是只有 1 次（不叠加）", str(names))


print()
print("=== H 长按连续触发 ===")

scfg2 = build()
scfg2.order = ["C.wav"]
c = scfg2.setting("C.wav")
c.hotkey = "f1"
c.trigger_mode = TRIGGER_REPEAT
c.repeat_ms = 100
c.unlock_mode = UNLOCK_KEY
c.unlock_key = "g"
c.unlock_count = 2          # 两次机会：整段按住只该扣 1 次

audio2 = FakeAudio(scfg2)
p2 = sr.InputPoller(cfg, FakeWheel(), audio2, None)
p2._down = lambda name: bool(state.get(name, False))
state.clear()

press("g", True, p2)
press("g", False, p2)
state["f1"] = True
p2.tick()                      # 按下：第 1 次
for _ in range(3):             # 每 100ms 再来一次
    _Clock.add(0.1)
    p2.tick()
check(len(audio2.calls) == 4, "按住 300ms、间隔 100ms → 共响 4 次",
      f"calls={len(audio2.calls)}")

state["f1"] = False
p2.tick()
n_after_release = len(audio2.calls)
_Clock.add(0.5)
p2.tick()
check(len(audio2.calls) == n_after_release, "松手后不再继续连发")

# 次数只扣了一次：还剩下 1 次，所以再按一次仍然能响
state["f1"] = True
p2.tick()
check(len(audio2.calls) == n_after_release + 1,
      "整段按住只消耗 1 次解锁（还剩 1 次，能再按）",
      f"calls={len(audio2.calls)}")
state["f1"] = False
p2.tick()

n2 = len(audio2.calls)
state["f1"] = True
p2.tick()
check(len(audio2.calls) == n2, "两次机会用完之后第三次按不动了",
      f"calls={len(audio2.calls)}")
state["f1"] = False
p2.tick()


print()
print("=== I 暂停 / 轮盘弹出时不触发 ===")

scfg3 = build()
scfg3.order = ["D.wav"]
d = scfg3.setting("D.wav")
d.hotkey = "mouse_left"
d.trigger_mode = TRIGGER_TAP

audio3 = FakeAudio(scfg3)
w3 = FakeWheel()
p3 = sr.InputPoller(cfg, w3, audio3, None)
state.clear()
p3._down = lambda name: bool(state.get(name, False))

state["mouse_left"] = True
p3.tick()
check(len(audio3.calls) == 1, "普通状态：按下就响")
state["mouse_left"] = False
p3.tick()

w3.active = True             # 轮盘弹着：鼠标键是"取消呼出"，不该出声
audio3.calls.clear()
state["mouse_left"] = True
p3.tick()
check(not audio3.calls, "轮盘弹着时按左键不触发音效")
state["mouse_left"] = False
p3.tick()
w3.active = False

p3.user_paused = True
audio3.calls.clear()
state["mouse_left"] = True
p3.tick()
check(not audio3.calls, "暂停期间按快捷键不触发")
state["mouse_left"] = False
p3.tick()

print()
print("=== J 长按触发松手即停（暂停时也要收尾）===")

scfg4 = build()
scfg4.order = ["E.wav"]
e = scfg4.setting("E.wav")
e.hotkey = "f2"
e.trigger_mode = TRIGGER_HOLD

audio4 = FakeAudio(scfg4)
p4 = sr.InputPoller(cfg, FakeWheel(), audio4, None)
state.clear()
p4._down = lambda name: bool(state.get(name, False))

state["f2"] = True
p4.tick()
tok = audio4.calls[0][1] if audio4.calls else 0
check(tok > 0, "长按触发开始响并记下编号")

p4.set_user_pause(True)      # 中途用户按了暂停（轮盘中心松手那种）
p4.tick()
check(audio4.stopped == [tok], "暂停时长按的声音会被掐掉", str(audio4.stopped))
p4.set_user_pause(False)
state["f2"] = False
p4.tick()


print()
print("=== K 混音器：按编号停，且只停这一次 ===")

from PySide6.QtMultimedia import QAudioFormat  # noqa: E402

import numpy as _np  # noqa: E402

fmt = QAudioFormat()
fmt.setSampleRate(48000)
fmt.setChannelCount(2)
fmt.setSampleFormat(QAudioFormat.Float)

mix = sr.Mixer(fmt)
clip = _np.ones((9600, 2), dtype=_np.float32)
mix.trigger(clip, 1.0, token=7)              # 这次按住：正在响的一条
mix.trigger(clip, 1.0, delay=20000, token=7)  # 同一次按住：还没开口的一条
mix.trigger(clip, 1.0, token=8)              # 别的触发：不该被波及

n = mix.stop_token(7)
check(n == 2, "停掉这次触发的两条声部", f"n={n}")
check(len(mix.voices) == 2, "另一路的声音原样留着", f"voices={len(mix.voices)}")
left = [v for v in mix.voices]
check(any(v[6] == 8 for v in left), "token=8 那条还在")
tok7 = [v for v in left if v[6] == 7]
check(len(tok7) == 1 and tok7[0][4] == 0,
      "token=7 的延迟声部被直接摘掉（不会一秒钟后自己冒出来），只剩在响的那条")

mix.readData(2000 * 2 * 4)                   # 走完 12ms 淡出（2000 帧 ≈ 42ms）
check(all(v[6] != 7 for v in mix.voices), "淡出结束后 token=7 的声音彻底消失")
check(any(v[6] == 8 for v in mix.voices), "token=8 仍在正常播放")


print()
print(f"通过 {len(OK)} 项，失败 {len(BAD)} 项")
if BAD:
    print("失败项：" + "；".join(BAD))
    raise SystemExit(1)
