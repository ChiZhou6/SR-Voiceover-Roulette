"""回归：条件停止（v0.9.0）。

用户 2026-11-07 提的规则：
    条件解锁 G、10 秒、1 次；条件停止 3 键。
    按 G → 解锁；按 3 → 停掉正在响的，并重新上锁（哪怕已经响起来了）。

覆盖：
    · 数据层：stop_keys 默认值 / 清洗（可多个） / stop_groups 的收集范围
    · 按 3 立刻停（按编号停 + 按槽位停，两种路径都要走）
    · 停完重新上锁 → 再按触发键没反应，要重新按 G
    · 长按触发按住时按 3：当场哑掉，松手也不会再响
    · 长按连续触发时按 3：连发计划一起清掉，不会过会儿自己冒一声
    · 只停自己，不连累别的音效
    · 按住 3 不放只停一次
    · 界面：控件在位、改键写盘、组合也有、说明随模式变

跑法：python _t_stopkey.py
"""
import os
import sys
import tempfile
import time as _time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "_tests"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402
from sounds_config import (  # noqa: E402
    STOP_KEYS_MAX,
    TRIGGER_HOLD,
    TRIGGER_REPEAT,
    TRIGGER_TAP,
    UNLOCK_KEY,
    ComboDef,
    ComboItem,
    SoundSetting,
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
    return bool(cond)


# ---------------------------------------------------------------- 假时钟
class _Clock:
    t = 5000.0

    def __call__(self):
        return _Clock.t

    @staticmethod
    def add(sec: float):
        _Clock.t += sec


_TIME = _Clock()
# 真引擎那一段要等声卡真的推帧，不能用假时钟（假时钟不会自己往前走）
_REAL_MONOTONIC = _time.monotonic
_time.monotonic = _TIME


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
    """只记"谁被播了、谁被停了"，真出声由 _t_exe / 真机负责。"""

    def __init__(self, scfg):
        self.bank = SimpleNamespace(scfg=scfg)
        self.calls = []        # [(音效键, token)]
        self.stopped = []      # 按编号停的 token
        self.stopped_names = []  # 按音效名停
        self._tok = 0

    def play_named(self, name, token=0):
        self.calls.append((name, token))
        return True

    def play(self, idx, token=0):
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

    def stop_named(self, name):
        self.stopped_names.append(name)
        return 1

    def stop_all(self):
        pass

    def reset_pitch(self):
        pass


def build(order=("AAA.wav", "B.wav")):
    scfg = SoundsConfig(Path(os.devnull))     # 不落盘
    scfg.order = list(order)
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


print("=== A 数据层 ===")

scfg = build()
st = scfg.setting("AAA.wav")
check(st.stop_keys == [], "默认没有条件停止键")
st.stop_keys = ["  G "]
check(st.clamped().stop_keys == ["g"], "停止键清洗：去空格 + 小写",
      repr(st.clamped().stop_keys))

scfg = build()
a = scfg.setting("AAA.wav")
a.stop_keys = ["3"]
b = scfg.setting("B.wav")
b.stop_keys = ["3"]
groups = scfg.stop_groups()
check(groups.get("3") == ["AAA.wav", "B.wav"],
      "一个停止键可以停多个音效", str(groups))
check("" not in groups, "没设停止键的不进表")

# 组合：定义全盘共用，没上轮盘也该能绑停止键
scfg = build()
ck = scfg.combo_key("c1")
scfg.combos["c1"] = ComboDef(cid="c1", name="测试组合",
                             items=[ComboItem(sound="AAA.wav")]).clamped()
scfg.setting(ck).stop_keys = ["3"]
check(scfg.combo_key("c1") in scfg.stop_groups().get("3", []),
      "组合的停止键也收集（不用上轮盘）", str(scfg.stop_groups()))

# 跨轮盘：勾了全局的算数，没勾的不算
scfg = build()
other = scfg.new_wheel("另一套", copy_current=False)
check(other is not None, "能建第二套轮盘（下面几条的前提）")
if other is not None:
    ost = SoundSetting(stop_keys=["4"])
    other.items["OTHER.wav"] = ost
    ost.global_hotkey = False
    check("4" not in scfg.stop_groups(), "别的轮盘、没勾全局的音效不进表")
    ost.global_hotkey = True
    check(scfg.stop_groups().get("4") == ["OTHER.wav"],
          "勾了全局的音效，在哪个轮盘停止键都算数", str(scfg.stop_groups()))

    # 重建绑定每次都会跑一遍 stop_groups：它只读不写，不能往里灌空记录
    before = {w.wid: len(w.items or {}) for w in scfg.wheels}
    for _ in range(3):
        scfg.stop_groups()
    after = {w.wid: len(w.items or {}) for w in scfg.wheels}
    check(before == after, "stop_groups 只读不写（不会给库里的音效灌空记录）",
          f"{before} -> {after}")


print()
print("=== B 用户案例：按 G 解锁 → 按左键响 → 按 3 停掉并重新上锁 ===")

scfg = build()
a = scfg.setting("AAA.wav")
a.hotkey = "mouse_left"
a.trigger_mode = TRIGGER_TAP
a.unlock_mode = UNLOCK_KEY
a.unlock_key = "g"
a.unlock_ms = 10000
a.unlock_count = 0
a.stop_keys = ["3"]
b = scfg.setting("B.wav")
b.stop_keys = ["3"]          # 同一个停止键只管自己那份，不播也不影响

audio = FakeAudio(scfg)
poller = sr.InputPoller(cfg, wheel, audio, None)
poller._down = lambda name: bool(state.get(name, False))


def press(key, on=True, p=None):
    state[key] = on
    (p or poller).tick()


def reset():
    audio.calls.clear()
    audio.stopped.clear()
    audio.stopped_names.clear()


def key_groups():
    return poller._stop_keys


check(key_groups().get("3") == ["AAA.wav", "B.wav"],
      "停止键绑定建起来了", str(key_groups()))

reset()
press("mouse_left")
check(audio.calls == [], "没按 G 之前点左键：不响")

press("mouse_left", False)
press("g")
press("g", False)
press("mouse_left")
played = list(audio.calls)
check([n for n, _t in played] == ["AAA.wav"], "按 G 之后点左键：响了", str(played))
tok = played[0][1] if played else 0
check(tok > 0, "这次触发带了编号（停止键能整批掐）", str(tok))

press("mouse_left", False)
reset()
press("3")
check(tok in audio.stopped, "按 3：按编号停掉了正在响的那一次", str(audio.stopped))
check("AAA.wav" in audio.stopped_names, "按 3：也按槽位停（轮盘点响的也能停）",
      str(audio.stopped_names))
check("AAA.wav" not in poller._unlock, "按 3：解锁状态被清掉（重新上锁）")
press("3", False)

reset()
press("mouse_left")
check(audio.calls == [], "重新上锁后点左键：又不响了", str(audio.calls))
press("mouse_left", False)

# 再解锁一次仍然能用（锁不是一次性的）
press("g")
press("g", False)
press("mouse_left")
check([n for n, _t in audio.calls] == ["AAA.wav"], "再按 G 又能响（锁可以反复开）",
      str(audio.calls))
press("mouse_left", False)

# 按住 3 不放只停一次
reset()
press("3", True)
first = len(audio.stopped_names)
for _ in range(5):
    poller.tick()
check(len(audio.stopped_names) == first, "按住 3 不放只停一次（不反复触发）",
      f"{first} -> {len(audio.stopped_names)}")
press("3", False)

# 本来没在响时按 3：不报错，锁照样清
press("g")
press("g", False)
reset()
press("3")
check("AAA.wav" not in poller._unlock, "没在响时按 3：锁照样清掉")
press("3", False)

# 只停自己：另一个音效的解锁不受影响
scfg2 = build()
x = scfg2.setting("AAA.wav")
x.hotkey = "mouse_left"
x.unlock_mode = UNLOCK_KEY
x.unlock_key = "g"
x.stop_keys = ["3"]
y = scfg2.setting("B.wav")
y.hotkey = "mouse_right"
y.unlock_mode = UNLOCK_KEY
y.unlock_key = "g"
y.stop_keys = ["4"]
audio2 = FakeAudio(scfg2)
p2 = sr.InputPoller(cfg, wheel, audio2, None)
p2._down = lambda name: bool(state.get(name, False))
state.clear()
press("g", True, p2)
press("g", False, p2)
check("AAA.wav" in p2._unlock and "B.wav" in p2._unlock, "G 同时解锁两个音效")
press("3", True, p2)
press("3", False, p2)
check("AAA.wav" not in p2._unlock, "按 3：AAA 重新上锁")
check("B.wav" in p2._unlock, "按 3：B 的锁没被连累")


print()
print("=== B2 一个音效挂多个停止键：哪个都算 ===")

scfg = build()
m = scfg.setting("AAA.wav")
m.stop_keys = ["3", "  F4 ", "3"]
check(m.clamped().stop_keys == ["3", "f4"], "多个停止键：去重 + 清洗",
      repr(m.clamped().stop_keys))
m.stop_keys = ["a", "b", "c", "d", "e"]
check(len(m.clamped().stop_keys) == STOP_KEYS_MAX,
      f"最多保留 {STOP_KEYS_MAX} 个停止键", repr(m.clamped().stop_keys))

scfg = build()
m = scfg.setting("AAA.wav")
m.stop_keys = ["3", "f4"]
g2 = scfg.stop_groups()
check(g2.get("3") == ["AAA.wav"] and g2.get("f4") == ["AAA.wav"],
      "一个音效的两个停止键都进了键表", str(g2))

# 存盘再读回来（列表字段最容易在 json 往返里丢）
tmp_save = Path(tempfile.mkdtemp(prefix="srstop_save_"))
scfg = SoundsConfig(tmp_save / "sounds.json")
scfg.load()
scfg.order = ["AAA.wav"]
scfg.setting("AAA.wav").stop_keys = ["3", "f4"]
scfg.save()
scfg_back = SoundsConfig(tmp_save / "sounds.json")
scfg_back.load()
check(scfg_back.setting("AAA.wav").stop_keys == ["3", "f4"],
      "多个停止键能存盘再读回来",
      repr(scfg_back.setting("AAA.wav").stop_keys))

scfg = build()
m = scfg.setting("AAA.wav")
m.hotkey = "mouse_left"
m.unlock_mode = UNLOCK_KEY
m.unlock_key = "g"
m.unlock_ms = 10000
m.stop_keys = ["3", "f4"]
audio3 = FakeAudio(scfg)
p3 = sr.InputPoller(cfg, wheel, audio3, None)
p3._down = lambda name: bool(state.get(name, False))
state.clear()
check(set(p3._stop_keys) == {"3", "f4"}, "两个停止键都建进轮询表",
      str(list(p3._stop_keys)))

for k in ("f4", "3"):
    press("g", True, p3)
    press("g", False, p3)
    press("mouse_left", True, p3)
    press("mouse_left", False, p3)
    played_ok = [n for n, _t in audio3.calls][-1:] == ["AAA.wav"]
    press(k, True, p3)
    press(k, False, p3)
    check(played_ok and "AAA.wav" in audio3.stopped_names and
          "AAA.wav" not in p3._unlock,
          f"按 {k} 也能停掉并重新上锁", str(audio3.stopped_names))
    audio3.calls.clear()
    audio3.stopped_names.clear()


print()
print("=== C 长按触发：按住时按 3，当场哑掉且松手不再响 ===")

state.clear()
scfg = build()
h = scfg.setting("AAA.wav")
h.hotkey = "mouse_left"
h.trigger_mode = TRIGGER_HOLD
h.unlock_mode = UNLOCK_KEY
h.unlock_key = "g"
h.stop_keys = ["3"]
audio = FakeAudio(scfg)
poller = sr.InputPoller(cfg, wheel, audio, None)
poller._down = lambda name: bool(state.get(name, False))

press("g")
press("g", False)
reset()
press("mouse_left")
held = audio.calls[0][1] if audio.calls else 0
check(held > 0, "按住左键起播，带按住编号", str(audio.calls))
press("3")
check(held in audio.stopped, "按 3：长按那一批也按编号停掉", str(audio.stopped))
check("AAA.wav" in audio.stopped_names, "按 3：同时按槽位停（双保险）")
press("3", False)
check("AAA.wav" not in poller._hold_token, "按住编号已清，松手不会再去停一次")
reset()
press("mouse_left", False)
check(all(t in audio.stopped for _n, t in audio.calls) and not audio.calls,
      "松手：不会再补一声", str(audio.calls))


print()
print("=== D 长按连续触发：按 3 要连发计划一起清掉 ===")

state.clear()
scfg = build()
r = scfg.setting("AAA.wav")
r.hotkey = "mouse_left"
r.trigger_mode = TRIGGER_REPEAT
r.repeat_ms = 100
r.unlock_mode = UNLOCK_KEY
r.unlock_key = "g"
r.stop_keys = ["3"]
audio = FakeAudio(scfg)
poller = sr.InputPoller(cfg, wheel, audio, None)
poller._down = lambda name: bool(state.get(name, False))

press("g")
press("g", False)
reset()
press("mouse_left")
n0 = len(audio.calls)
check(n0 == 1, "按下先响一次", str(n0))
_TIME.add(0.12)
poller.tick()
check(len(audio.calls) == 2, "按住到间隔会再响一次", str(len(audio.calls)))

press("3")
check("AAA.wav" not in poller._repeat_next, "按 3：连发计划被清掉")
before = len(audio.calls)
_TIME.add(0.12)
poller.tick()
_TIME.add(0.12)
poller.tick()
check(len(audio.calls) == before, "按 3 之后按住不放也不会再自己冒声音",
      f"{before} -> {len(audio.calls)}")
press("3", False)
press("mouse_left", False)


print()
print("=== E 界面 ===")

from settings_window import SlotDetail, build_qss  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="srstop_"))
real_cfg, real_scfg = sr.CONFIG_PATH, sr.SOUNDS_CONFIG_PATH
sr.CONFIG_PATH = tmp / "config.json"
sr.SOUNDS_CONFIG_PATH = tmp / "sounds.json"
try:
    scfg = SoundsConfig(sr.SOUNDS_CONFIG_PATH)
    scfg.load()
    scfg.order = ["AAA.wav", "B.wav"]
    scfg.combos["c9"] = ComboDef(cid="c9", name="界面组合",
                                 items=[ComboItem(sound="AAA.wav")]).clamped()
    st = scfg.setting("AAA.wav")
    st.unlock_mode = UNLOCK_KEY
    st.unlock_key = "g"
    st.stop_keys = ["3"]

    detail = SlotDetail(scfg)
    detail.setStyleSheet(build_qss())
    detail.show()
    app.processEvents()
    detail.set_sound("AAA.wav")
    app.processEvents()
    check(detail._stop_boxes[0].isVisible(), "详情卡片里有「停止」按键框")
    check(detail._stop_boxes[0].key_name == "3", "选中音效时显示它自己的停止键",
          detail._stop_boxes[0].key_name)
    check("重新上锁" in detail.lbl_stop_hint.text(),
          "开了条件解锁时，说明写着重新上锁", detail.lbl_stop_hint.text())

    # 模拟用户按键：走 _apply 才会发 key_changed（set_key 是外部回填，故意不发声）
    detail._stop_boxes[0].edit._apply("f4")
    app.processEvents()
    check(scfg.setting("AAA.wav").stop_keys == ["f4"],
          "在界面上改停止键会立刻写回配置",
          scfg.setting("AAA.wav").stop_keys)

    # 多个停止键：点加号 -> 多一个空框 -> 填上就存成两个
    check(detail.btn_add_stop.isVisible(), "还能加键时加号是露着的")
    detail.btn_add_stop.click()
    app.processEvents()
    check(len(detail._stop_boxes) == 2, "点加号多摆一个按键框",
          str(len(detail._stop_boxes)))
    detail._stop_boxes[1].edit._apply("f5")
    app.processEvents()
    check(scfg.setting("AAA.wav").stop_keys == ["f4", "f5"],
          "两个停止键都写进配置了", scfg.setting("AAA.wav").stop_keys)

    detail.btn_add_stop.click()
    detail._stop_boxes[2].edit._apply("f6")
    app.processEvents()
    check(len(detail._stop_boxes) == 3, "最多摆 3 个按键框",
          str(len(detail._stop_boxes)))
    check(not detail.btn_add_stop.isVisible(), "加满了加号就藏起来")
    check(scfg.setting("AAA.wav").stop_keys == ["f4", "f5", "f6"],
          "三个键都存住了", scfg.setting("AAA.wav").stop_keys)

    # 换回无条件：键不能被清掉，说明要改口
    detail.unlock_mode.setCurrentIndex(
        max(0, detail.unlock_mode.findData("none")))
    app.processEvents()
    check("重新上锁" not in detail.lbl_stop_hint.text(),
          "改成无条件后，说明不再提重新上锁", detail.lbl_stop_hint.text())
    check(scfg.setting("AAA.wav").stop_keys == ["f4", "f5", "f6"],
          "换成无条件后停止键不会被清掉（按一下就停照样有用）")

    # 选中另一个音效再选回来：按键框数量要跟着配置走，不能越攒越多
    detail.set_sound("B.wav")
    app.processEvents()
    check(len(detail._stop_boxes) == 1 and detail._stop_boxes[0].key_name == "",
          "换到没设停止键的音效：只剩一个空框",
          f"{len(detail._stop_boxes)} / {detail._stop_boxes[0].key_name!r}")
    detail.set_sound("AAA.wav")
    app.processEvents()
    check([b.key_name for b in detail._stop_boxes] == ["f4", "f5", "f6"],
          "再选回来：三个键都还原", str([b.key_name for b in detail._stop_boxes]))

    # 组合也该有这一项
    st9 = scfg.setting(scfg.combo_key("c9"))
    st9.stop_keys = ["5"]
    detail.set_sound(scfg.combo_key("c9"))
    app.processEvents()
    check(detail._stop_boxes[0].isVisible(), "组合音效也有「停止」框")
    check(detail._stop_boxes[0].key_name == "5", "组合的停止键能正确读出来",
          detail._stop_boxes[0].key_name)

    detail.close()
finally:
    sr.CONFIG_PATH, sr.SOUNDS_CONFIG_PATH = real_cfg, real_scfg


print()
print("=== F 真引擎：按名字停，声音真的没了 ===")

bank = sr.SoundBank(4)
if len(bank) < 2:
    check(False, "至少要有 2 个音效才能测真引擎播放")
else:
    engine = sr.AudioEngine(bank, {"volume": 0.6, "mic_enabled": False})
    name0 = bank.full_at(0)
    name1 = bank.full_at(1)

    engine.play(0)
    deadline = _REAL_MONOTONIC() + 1.5
    while _REAL_MONOTONIC() < deadline and not engine.playing:
        app.processEvents()
        _time.sleep(0.02)
    check(engine.playing, "真引擎：play(0) 起来了", name0)

    killed = engine.stop_named(name0)
    check(killed > 0, "真引擎：stop_named 找得到这个槽位的声音", str(killed))
    # stop_* 走 12ms 淡出，不是立刻清空，等一会儿再断言
    deadline = _REAL_MONOTONIC() + 0.4
    while _REAL_MONOTONIC() < deadline:
        app.processEvents()
        _time.sleep(0.02)
    check(not engine.playing, "真引擎：stop_named 之后不再有声音")

    # 停 A 不能把 B 一起掐了
    engine.play(0)
    engine.play(1)
    deadline = _REAL_MONOTONIC() + 1.5
    while _REAL_MONOTONIC() < deadline and not engine.playing:
        app.processEvents()
        _time.sleep(0.02)
    engine.stop_named(name0)
    deadline = _REAL_MONOTONIC() + 0.3
    while _REAL_MONOTONIC() < deadline:
        app.processEvents()
        _time.sleep(0.02)
    check(engine.playing, "真引擎：停掉 A 之后 B 还在响（按槽位停，不误伤）", name1)
    engine.stop_all()
    deadline = _REAL_MONOTONIC() + 0.4
    while _REAL_MONOTONIC() < deadline:
        app.processEvents()
        _time.sleep(0.02)


print()
print("=" * 60)
print(f"通过 {len(OK)} 项，失败 {len(BAD)} 项")
if BAD:
    print("失败项：" + "；".join(BAD))
    raise SystemExit(1)
