"""回归：每套轮盘的专属呼出键 + 按轮盘记「上次放的音效」（v0.9.3）。

跑法：python _t_wheel_hotkey.py
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


# ---------------------------------------------------------------- 假时钟
class _Clock:
    t = 1000.0

    def __call__(self):
        return _Clock.t

    @staticmethod
    def add(sec: float):
        _Clock.t += sec


_TIME = _Clock()
time.monotonic = _TIME          # 整进程走假时钟，测试不用真 sleep


# ---------------------------------------------------------------- 假对象
class FakeWheel:
    def __init__(self):
        self.active = False
        self.raw = None
        self.shown = 0
        self.want = 0           # commit 返回哪个槽位

    def show_wheel(self):
        self.active = True
        self.shown += 1

    def hide_wheel(self):
        self.active = False

    def commit(self):
        self.active = False
        return self.want

    def poll_selection(self):
        pass


class FakeAudio:
    def __init__(self, scfg):
        # full_at 用来模拟"当前这套盘第 idx 格是谁"——预选模式要靠它记下选中的音效
        self.bank = SimpleNamespace(
            scfg=scfg,
            full_at=lambda idx: "BBB.wav" if str(scfg.current) == "w2" else "AAA.wav",
        )
        self.played = []
        self.repeated = 0
        self.nexted = 0

    def play(self, idx, token=0):
        self.played.append(idx)
        return True

    def play_named(self, name, token=0):
        self.played.append(name)
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


def build_scfg(hk1="", hk2=""):
    """两套轮盘，各塞一个音效，第二套可以带专属键。"""
    scfg = SoundsConfig(Path(os.devnull))      # 不落盘，纯内存
    scfg.wheels = [
        WheelDef(wid="w1", name="轮盘 1", hotkey=hk1, order=["AAA.wav"]),
        WheelDef(wid="w2", name="轮盘 2", hotkey=hk2, order=["BBB.wav"]),
    ]
    scfg._cur = "w1"
    scfg._orders = {"w1": ["AAA.wav"], "w2": ["BBB.wav"]}
    return scfg


def make_poller(scfg, state, switched=None, previewed=None, preselect=False):
    cfg = dict(sr.DEFAULT_CONFIG)
    cfg["hotkey"] = "y"
    cfg["hold_ms"] = 60
    cfg["switch_key"] = ""
    cfg["repeat_last_key"] = ""
    cfg["cycle_key"] = ""
    cfg["tap_action"] = "repeat_last"
    cfg["preselect_mode"] = bool(preselect)
    wheel = FakeWheel()
    audio = FakeAudio(scfg)
    p = sr.InputPoller(cfg, wheel, audio, None)
    p._down = lambda name: bool(state.get(name, False))
    p.rebuild_bindings()      # 用伪造的 _down 重新播种状态
    if switched is not None:
        p.on_switch_wheel = switched.append
    if previewed is not None:
        # 照着主程序 preview_wheel() 的语义做一份：
        # 非空 = 临时切内存里的 current；空 = 还原
        keep = {"back": ""}

        def _preview(wid):
            previewed.append(wid)
            if wid:
                if wid != scfg.current:
                    keep["back"] = str(scfg.current or "")
                    scfg.switch_wheel(wid)
            elif keep["back"]:
                back, keep["back"] = keep["back"], ""
                scfg.switch_wheel(back)

        p.on_preview_wheel = _preview
    return p, wheel, audio


def press(p, state, key, on):
    state[key] = on
    p.tick()


print("=== A 没绑盘键：什么都不变 ===")
scfg = build_scfg()
state = {}
sw = []
p, wheel, audio = make_poller(scfg, state, sw)
check(p.hotkey_name == "y", "呼出键就是主热键", p.hotkey_name)
press(p, state, "y", True)
check(p.hotkey_name == "y", "按主热键不会被借走", p.hotkey_name)
press(p, state, "y", False)
check(not sw, "没有盘键就不该切盘", str(sw))

print()
print("=== B 按着盘键：临时摆出那套盘 + 借用呼出键 ===")
scfg = build_scfg(hk2="u")
state = {}
sw = []
pv = []
p, wheel, audio = make_poller(scfg, state, sw, pv)
press(p, state, "u", True)
check(pv == ["w2"], "按下盘键临时摆出 w2", str(pv))
check(not sw, "不调 on_switch_wheel —— 那不是「切盘」", str(sw))
check(p.hotkey_name == "u", "呼出键借给盘键了", p.hotkey_name)
check(p._borrowed_wid == "w2", "记住了借的是哪套盘", p._borrowed_wid)
check(p._previewed_wid == "w2", "记住了临时摆出的是哪套", p._previewed_wid)

print()
print("=== C 长按：弹出轮盘 ===")
_Click = _Clock
_Click.add(0.10)
p.tick()
check(wheel.shown == 1, "按住超过 hold_ms 弹出轮盘", str(wheel.shown))
check(p._held_to_wheel is True, "标记成「这次按到弹盘了」", str(p._held_to_wheel))

print()
print("=== D 松手：放选中的那格，交还主热键，并把盘收回去 ===")
wheel.want = 3
press(p, state, "u", False)
check(audio.played == [3], "松手播放选中的槽位", str(audio.played))
check(p.hotkey_name == "y", "呼出键交还主热键", p.hotkey_name)
check(p._borrowed_wid == "", "借用状态清干净", p._borrowed_wid)
check(pv == ["w2", ""], "松手时通知主程序还原", str(pv))
check(p._previewed_wid == "", "临时摆出的标记也清了", p._previewed_wid)

print()
print("=== E 轻按（不到 hold_ms）：不弹盘，走轻按动作 ===")
scfg = build_scfg(hk2="u")
state = {}
sw = []
pv = []
p, wheel, audio = make_poller(scfg, state, sw, pv)
press(p, state, "u", True)
press(p, state, "u", False)      # 同一时刻松手，没到 60ms
check(wheel.shown == 0, "轻按不弹盘", str(wheel.shown))
check(audio.repeated == 1, "轻按执行「重复上一个」", str(audio.repeated))
check(p.hotkey_name == "y", "轻按之后也交还主热键", p.hotkey_name)
check(pv == ["w2", ""], "轻按也临时摆出、松手还原", str(pv))

print()
print("=== F 盘键跟主热键撞车：不借、不抢 ===")
scfg = build_scfg(hk2="y")
state = {}
sw = []
p, wheel, audio = make_poller(scfg, state, sw)
press(p, state, "y", True)
check(p._borrowed_wid == "", "同一个键不借（否则主热键就乱了）", p._borrowed_wid)

print()
print("=== G 换主热键时借用状态作废 ===")
scfg = build_scfg(hk2="u")
state = {}
sw = []
p, wheel, audio = make_poller(scfg, state, sw)
press(p, state, "u", True)
check(p._borrowed_wid == "w2", "先借上", p._borrowed_wid)
p.set_hotkey("h")
check(p._borrowed_wid == "", "换主热键后借用清零", p._borrowed_wid)
check(p.hotkey_name == "h", "呼出键变成新的主热键", p.hotkey_name)

print()
print("=== H 按轮盘分别记「上次放的音效」 ===")


class FakeBank:
    def __init__(self, scfg, keys):
        self.scfg = scfg
        self.keys = keys

    def __len__(self):
        return len(self.keys)

    def full_at(self, idx):
        return self.keys[idx] if 0 <= idx < len(self.keys) else ""


eng = sr.AudioEngine.__new__(sr.AudioEngine)
eng.last_idx = None
eng.last_key = ""
eng.last_by_wheel = {}
eng.bank = FakeBank(SimpleNamespace(current="w1"), ["AAA.wav", "CCC.wav"])

eng._remember_last(1)
check(eng.last_by_wheel.get("w1") == "CCC.wav", "第一套盘记下了 CCC", str(eng.last_by_wheel))
check(eng.last_key_of_current() == "CCC.wav", "当前盘查得到", eng.last_key_of_current())

eng.bank = FakeBank(SimpleNamespace(current="w2"), ["BBB.wav"])
check(eng.last_key_of_current() == "", "换到从没放过的那套盘：查不到（不串台）",
      eng.last_key_of_current())
eng._remember_last(0)
check(eng.last_key_of_current() == "BBB.wav", "第二套盘记下自己的 BBB",
      eng.last_key_of_current())
check(eng.last_by_wheel.get("w1") == "CCC.wav", "第一套盘的记录没被覆盖",
      str(eng.last_by_wheel))

print()
print("=== I 数据层：hotkey 能存能读、克隆不带键 ===")
w = WheelDef(wid="w9", name="测试", hotkey="ctrl+u")
raw = w.to_dict()
check(raw.get("hotkey") == "ctrl+u", "写进 dict 了", str(raw.get("hotkey")))
check(WheelDef(wid="a", name="b", hotkey="u").clone("b", "c").hotkey == "",
      "另存为新轮盘时不复制呼出键（两套绑同一个键没法用）")

print()
print("=== K 预选模式：长按 B 的键选中，再按一次同一个键才播 ===")
scfg = build_scfg(hk2="u")
state = {}
pv = []
p, wheel, audio = make_poller(scfg, state, [], pv, preselect=True)
p.on_pending_changed = lambda _pending, _idx: None
press(p, state, "u", True)
_Clock.add(0.10)
p.tick()                          # 按满 → 弹盘
check(wheel.shown == 1, "长按弹出 B 的盘", str(wheel.shown))
wheel.want = 0
press(p, state, "u", False)       # 松手：只选中，不出声
check(audio.played == [], "预选模式松手不出声", str(audio.played))
check(p._pending is not None and p._pending[0] == "w2",
      "记下了「w2 上的 BBB」（按轮盘记，不是按槽位）", str(p._pending))
check(pv == ["w2", ""], "松手后已经把盘还原", str(pv))

press(p, state, "u", True)        # 再按一次同一个键 = 确认播放
press(p, state, "u", False)
check(audio.played == ["BBB.wav"], "确认播放放的是 B 上的那一个", str(audio.played))
check(p._pending is None, "待播清空，不会连着放第二次")

print()
print("=== J 临时摆出必须「不落盘」：关掉程序后当前轮盘还是原来那套 ===")
import tempfile  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    path = Path(td) / "sounds.json"
    real = SoundsConfig(path)
    real.wheels = [
        WheelDef(wid="w1", name="轮盘 1", order=["AAA.wav"]),
        WheelDef(wid="w2", name="轮盘 2", order=["BBB.wav"]),
    ]
    real._cur = "w1"
    real.save()

    live = SoundsConfig(path)
    live.load()
    check(live.current == "w1", "读回来是 w1", live.current)
    live.switch_wheel("w2")          # 就是 preview_wheel 干的事：只改内存
    check(live.current == "w2", "内存里临时变成 w2", live.current)
    check(live.sync(["AAA.wav", "BBB.wav"]) == ["BBB.wav"],
          "临时状态下读到的确实是 w2 的内容")

    again = SoundsConfig(path)
    again.load()
    check(again.current == "w1", "没 save 就不落盘：磁盘上还是 w1", again.current)

print()
print("=" * 56)
if BAD:
    print(f"结果：{len(BAD)} 项失败 / 共 {len(OK) + len(BAD)} 项")
    for n in BAD:
        print("  FAIL", n)
    raise SystemExit(1)
print(f"结果：全部通过（{len(OK)} 项）")
