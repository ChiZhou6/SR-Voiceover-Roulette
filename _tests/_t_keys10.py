"""回归：v0.9.1 的三项改动。

1. 可绑定按键扩展：滚轮上/下、单独绑 Alt / Shift / Ctrl
2. 组合音效突破 24 项上限
3. 每个轮盘格单独的「连击时停掉上一次」

跑法：python _t_keys10.py
"""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "_tests"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402
from sounds_config import (  # noqa: E402
    MAX_COMBO_ITEMS,
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


# ---------------------------------------------------------------- A. 滚轮
print()
print("=== A. 滚轮绑定 ===")


def fake_mouse(flags=0, data=0):
    return SimpleNamespace(usButtonFlags=flags, usButtonData=data,
                           usFlags=0, lLastX=0, lLastY=0)


raw = sr.RawMouse()
check(sr.WHEEL_KEYS == ("wheel_up", "wheel_down", "wheel_left", "wheel_right"),
      "滚轮键名固定为 wheel_up / wheel_down / wheel_left / wheel_right")

# 往上滚：usButtonData 是正数（按 SHORT 解释）
raw._on_raw(fake_mouse(0x0400, 120))
check(raw.wheel_hit("wheel_up"), "滚轮上：一个刻度记一次")
check(not raw.wheel_hit("wheel_down"), "滚轮上不会误报滚轮下")

raw.clear_wheel()
check(not raw.wheel_hit("wheel_up"), "清账之后不再算按下")

# 往下滚的数据是 0xFF88 = -120（USHORT 存的是补码）
raw._on_raw(fake_mouse(0x0400, 0xFF88))
check(raw.wheel_hit("wheel_down"), "滚轮下：负的刻度被正确解成向下")
check(not raw.wheel_hit("wheel_up"), "滚轮下不会误报滚轮上")

# 连滚三格
raw.clear_wheel()
for _ in range(3):
    raw._on_raw(fake_mouse(0x0400, 120))
check(raw.wheel_hit("wheel_up"), "连滚多格仍然算一次按下（同一帧内合并）")
raw.clear_wheel()

# 普通按键标志不能碰滚轮
raw._on_raw(fake_mouse(0x0001, 0))
check(not raw.wheel_hit("wheel_up") and not raw.wheel_hit("wheel_down"),
      "单独的按键事件不会被当成滚轮")

# _down() 认得滚轮。InputPoller 是 QObject 子类，不能 object.__new__；
# 借一份未绑定的方法挂到普通类上就够（只测这一个方法）。
class _PollerStub:
    _down = sr.InputPoller._down


poller = _PollerStub()
poller.wheel = SimpleNamespace(raw=raw)
poller.gamepad = SimpleNamespace(down=lambda k: False)
poller._pad_suppressed = set()
raw.registered = True
raw.clear_wheel()
check(not poller._down("wheel_up"), "没滚的时候不算按下")
raw._on_raw(fake_mouse(0x0400, 120))
check(poller._down("wheel_up"), "滚一下：_down 认得 wheel_up")
check(not poller._down("wheel_down"), "这一下不会同时认成 wheel_down")

check(sr.norm_spec("wheel_up") == "wheel_up", "滚轮键名规范化后不变")
check(sr.spec_parts("ctrl+wheel_up") == ["ctrl", "wheel_up"], "滚轮也能当组合键的主键")


# ---------------------------------------------------------------- B. 修饰键独绑
print()
print("=== B. 单独绑 Alt / Shift / Ctrl ===")

from settings_window import _KeyEdit, key_label  # noqa: E402

check(key_label("wheel_up") == "滚轮上", "滚轮上的显示名", key_label("wheel_up"))
check(key_label("wheel_down") == "滚轮下", "滚轮下的显示名", key_label("wheel_down"))
check(key_label("ctrl") == "Ctrl", "单独 Ctrl 的显示名", key_label("ctrl"))


def press(w, key, mods=Qt.NoModifier):
    w.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, mods))


def release(w, key, mods=Qt.NoModifier):
    w.keyReleaseEvent(QKeyEvent(QEvent.KeyRelease, key, mods))


# 单独按 Shift：按下不绑，松手才绑
e1 = _KeyEdit()
press(e1, Qt.Key_Shift, Qt.ShiftModifier)
check(e1.key_name == "", "只按下 Shift 时先不绑（可能是组合的前半截）", e1.key_name)
release(e1, Qt.Key_Shift, Qt.NoModifier)
check(e1.key_name == "shift", "Shift 单独松手 = 绑 shift", e1.key_name)
release(e1, Qt.Key_Shift)

# 单独 Alt / Ctrl
for qt_key, expect in ((Qt.Key_Alt, "alt"), (Qt.Key_Control, "ctrl")):
    box = _KeyEdit()
    press(box, qt_key)
    release(box, qt_key)
    check(box.key_name == expect, f"单独按一下就能绑 {expect}", box.key_name)

# 组合键不能退化成修饰键
e2 = _KeyEdit()
press(e2, Qt.Key_Control, Qt.ControlModifier)
press(e2, Qt.Key_Y, Qt.ControlModifier)
check(e2.key_name == "ctrl+y", "Ctrl 再按 Y 仍然是组合键", e2.key_name)
release(e2, Qt.Key_Control, Qt.NoModifier)
check(e2.key_name == "ctrl+y", "随后松开 Ctrl 不会把它改成单独 ctrl", e2.key_name)

# Ctrl+Shift 只松开一个：不能绑成半个组合
e3 = _KeyEdit()
press(e3, Qt.Key_Control, Qt.ControlModifier)
press(e3, Qt.Key_Shift, Qt.ControlModifier | Qt.ShiftModifier)
release(e3, Qt.Key_Control, Qt.ShiftModifier)
check(e3.key_name == "", "Ctrl+Shift 先松 Ctrl：不绑成单独 ctrl", e3.key_name)

# 滚轮录入
e4 = _KeyEdit()
e4.hasFocus = lambda: True          # 离屏环境拿不到真实焦点，直接短路


def wheel(w, dy, focused=True):
    w.hasFocus = lambda: focused
    ev = QWheelEvent(QPointF(1, 1), QPointF(1, 1), QPoint(0, 0), QPoint(0, dy),
                     Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    w.wheelEvent(ev)


wheel(e4, 120)
check(e4.key_name == "wheel_up", "滚轮上滚一下就能绑上", e4.key_name)
wheel(e4, -120)
check(e4.key_name == "wheel_down", "滚轮下滚一下就能绑上", e4.key_name)

e5 = _KeyEdit()
wheel(e5, 120, focused=False)
check(e5.key_name == "", "框没有焦点时滚轮不改绑定（在列表里滚不会误改）", e5.key_name)

# Delete 清除对滚轮同样有效
wheel(e4, 120)
press(e4, Qt.Key_Delete)
check(e4.key_name == "", "Delete 能清掉滚轮绑定", e4.key_name)

# 配置层：这些新键名能原样存下来并读回来
tmp = Path(tempfile.mkdtemp(prefix="sr_keys10_"))
scfg0 = SoundsConfig(tmp / "sounds.json")
scfg0.order = ["A.wav"]
scfg0.setting("A.wav").hotkey = "wheel_down"
scfg0.setting("A.wav").stop_keys = ["ctrl", "wheel_up"]
scfg0.setting("A.wav").unlock_key = "shift"
scfg0.save()
scfg0b = SoundsConfig(tmp / "sounds.json")
scfg0b.load()
st0 = scfg0b.setting("A.wav")
check(st0.hotkey == "wheel_down", "滚轮热键存盘往返", st0.hotkey)
check(st0.stop_keys == ["ctrl", "wheel_up"], "滚轮/修饰键都能当停止键", str(st0.stop_keys))
check(st0.unlock_key == "shift", "单独修饰键能当解锁键", st0.unlock_key)


# ---------------------------------------------------------------- C. 组合上限
print()
print("=== C. 组合 24 → 100 ===")

check(MAX_COMBO_ITEMS == 100, "组合成员上限提到 100", str(MAX_COMBO_ITEMS))

many = [ComboItem(sound=f"s{i}.wav") for i in range(100)]
cd100 = ComboDef(cid="c100", name="百条", items=many).clamped()
check(len(cd100.items) == 100, "100 项的组合不再被截断", str(len(cd100.items)))

over = [ComboItem(sound=f"s{i}.wav") for i in range(130)]
cd_over = ComboDef(cid="cover", name="超量", items=over).clamped()
check(len(cd_over.items) == 100, "超过 100 项才截断", str(len(cd_over.items)))

cd_old = ComboDef(cid="cold", name="旧的", items=many[:24]).clamped()
check(len(cd_old.items) == 24, "原来 24 项的老组合原样保留", str(len(cd_old.items)))

# 存盘往返：100 项能完整读回来
tmp2 = Path(tempfile.mkdtemp(prefix="sr_combo100_"))
scfg1 = SoundsConfig(tmp2 / "sounds.json")
scfg1.order = ["A.wav"]
scfg1.combos["c100"] = cd100
scfg1.save()
scfg1b = SoundsConfig(tmp2 / "sounds.json")
scfg1b.load()
check(len(scfg1b.combos["c100"].items) == 100, "100 项组合存盘往返不丢",
      str(len(scfg1b.combos["c100"].items)))

from settings_window import ComboEditorDialog  # noqa: E402

dlg = ComboEditorDialog(scfg1b, cd100)
check(dlg.spn_count.maximum() == 100, "「每次取几项」的上限也跟着放开",
      str(dlg.spn_count.maximum()))
dlg.close()


# ---------------------------------------------------------------- D. 连击打断
print()
print("=== D. 连击时停掉上一次 ===")

check(SoundSetting().stop_prev is False, "默认不打断（和以前一样叠加）")
s_t = SoundSetting(stop_prev=1)
check(s_t.clamped().stop_prev is True, "手写 1 也当开启")
s_f = SoundSetting(stop_prev="")
check(s_f.clamped().stop_prev is False, "手写空值当关闭")


class FakeBank:
    """只提供 play() 需要的那几个查询。"""

    def __init__(self, entry=None):
        self.entry = entry

    def index_of_name(self, name):
        return 0 if name == "A.wav" else -1

    def entry_at(self, idx):
        return self.entry


class _EngineStub:
    """AudioEngine 也是 QObject 子类，同样借方法挂到普通类上。"""

    play = sr.AudioEngine.play
    _remember_last = sr.AudioEngine._remember_last


def make_engine(stop_prev, entry=None):
    """造一台不碰声卡的引擎：clips 是假的、混音器只记调用顺序。"""
    eng = _EngineStub()
    eng.clips = [np.zeros(4800, dtype=np.float32)]
    eng.bank = FakeBank(entry)
    eng._global_slots = {}
    eng.last_idx = None
    # play() 里记连击位置的几张小表，参数是默认值也照样会读写
    eng._last_at = {}
    eng._pitch_now = {}
    eng._speed_now = {}
    eng.calls = []
    st = SoundSetting(stop_prev=stop_prev)

    def setting_of_slot(idx):
        return st

    def stop_slot(idx, fade_ms=12.0):
        eng.calls.append(("stop", idx))
        return 1

    def active_mixers():
        return [SimpleNamespace(
            trigger=lambda clip, gain=1.0, delay=0, group=None,
            max_voices=0, token=0, slot=-1: eng.calls.append(("play", slot)) or True)]

    eng._setting_of_slot = setting_of_slot
    eng.stop_slot = stop_slot
    eng._active_mixers = active_mixers
    return eng


eng_off = make_engine(False)
eng_off.play(0)
eng_off.play(0)
check([c[0] for c in eng_off.calls] == ["play", "play"],
      "没勾：连按两次就是两条声音叠着（不用停）", str(eng_off.calls))

eng_on = make_engine(True)
eng_on.play(0)
eng_on.play(0)
check([c[0] for c in eng_on.calls] == ["stop", "play", "stop", "play"],
      "勾了：每次开口前先把上一声掐掉", str(eng_on.calls))

# 组合条目同样受这一项管
combo = SimpleNamespace(cdef=SimpleNamespace(cid="cx"))
eng_combo = make_engine(True, entry=sr.ComboEntry(combo.cdef))
eng_combo.play_combo = lambda cdef, token=0, slot=-1: eng_combo.calls.append(
    ("combo", slot)) or True
eng_combo.play(0)
check(eng_combo.calls[:2] == [("stop", 0), ("combo", 0)],
      "组合格子勾了这一项也会先掐上一遍", str(eng_combo.calls))


# ---------------------------------------------------------------- E. 界面
print()
print("=== E. 设置页里的「打断」 ===")

import sr_roulette as sr_mod  # noqa: E402
from settings_window import SlotDetail, build_qss  # noqa: E402

real_cfg, real_scfg = sr_mod.CONFIG_PATH, sr_mod.SOUNDS_CONFIG_PATH
sandbox = Path(tempfile.mkdtemp(prefix="sr_cut_ui_"))
import shutil  # noqa: E402

for f in ("config.json", "sounds.json"):
    try:
        shutil.copy2(ROOT / f, sandbox / f)
    except Exception:
        pass
sr_mod.CONFIG_PATH = sandbox / "config.json"
sr_mod.SOUNDS_CONFIG_PATH = sandbox / "sounds.json"

try:
    scfg2 = SoundsConfig(sr_mod.SOUNDS_CONFIG_PATH)
    scfg2.load()
    if not scfg2.order:
        scfg2.order = ["A.wav"]
    name = scfg2.order[0]
    scfg2.setting(name).stop_prev = True
    detail = SlotDetail(scfg2)
    detail.setStyleSheet(build_qss())
    detail.show()
    app.processEvents()
    detail.set_sound(name)
    app.processEvents()

    check(detail.chk_stop_prev.isVisible(), "详情卡片里有「连击时停掉上一次」")
    check(detail.chk_stop_prev.isChecked(), "选中音效时读回它自己的开关状态")

    detail.chk_stop_prev.setChecked(False)
    app.processEvents()
    check(scfg2.setting(name).stop_prev is False, "取消勾选会立刻写回配置")
    detail.chk_stop_prev.setChecked(True)
    app.processEvents()
    check(scfg2.setting(name).stop_prev is True, "重新勾上也会立刻写回")

    detail.set_sound(None)
    app.processEvents()
    check(not detail.chk_stop_prev.isEnabled(), "没选中音效时置灰")
    check(not detail.chk_stop_prev.isChecked(), "没选中时复位成不勾")
    detail.close()
finally:
    sr_mod.CONFIG_PATH, sr_mod.SOUNDS_CONFIG_PATH = real_cfg, real_scfg


print()
print("=" * 60)
print(f"通过 {len(OK)} 项，失败 {len(BAD)} 项")
if BAD:
    print("失败项：" + "；".join(BAD))
    raise SystemExit(1)
