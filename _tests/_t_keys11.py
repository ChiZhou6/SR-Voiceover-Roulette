"""回归：把 v0.9.1 之后能做的按键全开了。

新增：方向键、Insert/Home/End/PgUp/PgDn、小键盘整套、主键区符号
（- = [ ] \\ `）、PrtSc/ScrLk/Pause/Menu、横向滚轮（左右拨）。

跑法：python _t_keys11.py
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402

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


# ---------------------------------------------------------------- A. 虚拟键码
print()
print("=== A. 新键名的虚拟键码 ===")

EXPECT = {
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "insert": 0x2D, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
    "numlock": 0x90,
    "num_mul": 0x6A, "num_add": 0x6B, "num_sub": 0x6D,
    "num_dot": 0x6E, "num_div": 0x6F,
    "minus": 0xBD, "equal": 0xBB,
    "lbracket": 0xDB, "rbracket": 0xDD,
    "backslash": 0xDC, "backquote": 0xC0,
    "printscreen": 0x2C, "scrolllock": 0x91,
    "pause": 0x13, "menu": 0x5D,
}
bad = {k: hex(sr.vk_of(k)) for k, v in EXPECT.items() if sr.vk_of(k) != v}
check(not bad, "所有新键名的虚拟键码都对", str(bad))
check(all(sr.vk_of(f"num{i}") == 0x60 + i for i in range(10)),
      "小键盘数字 num0..num9 = 0x60..0x69")

# vk_of 对不认识的名字会默默返回 0x59（Y），这才是最容易出的事故：
# 加了显示名却忘了补表，绑上去按了没反应、或者按 Y 出声。
NEWEST = list(EXPECT) + [f"num{i}" for i in range(10)]
leaked = [k for k in NEWEST if sr.vk_of(k) == 0x59]
check(not leaked, "新键名没有一个掉进 Y(0x59) 兜底", str(leaked))


# ---------------------------------------------------------------- B. 两张表对得上
print()
print("=== B. 录入表 / 显示表 / 键码表 三张表不脱节 ===")

from settings_window import (  # noqa: E402
    _KEY_LABEL,
    _QT_KEYPAD_TO_KEY,
    _QT_TO_KEY,
    _KeyEdit,
    key_label,
    key_name_of,
)

qt_names = set(_QT_TO_KEY.values()) | set(_QT_KEYPAD_TO_KEY.values())
qt_names |= {f"num{i}" for i in range(10)}
missing_label = sorted(n for n in qt_names if n not in _KEY_LABEL)
check(not missing_label, "能录的键都有中文显示名", str(missing_label))
missing_vk = sorted(n for n in qt_names if sr.vk_of(n) == 0x59 and n != "y")
check(not missing_vk, "能录的键都能翻译成虚拟键码", str(missing_vk))

check(key_label("num5") == "小键盘5", "小键盘数字的显示名", key_label("num5"))
check(key_label("num_add") == "小键盘+", "小键盘加号的显示名", key_label("num_add"))
check(key_label("up") == "↑", "方向键的显示名", key_label("up"))
check(key_label("pageup") == "PgUp", "PageUp 的显示名", key_label("pageup"))
check(key_label("ctrl+num5") == "Ctrl+小键盘5", "小键盘也能当组合键主键",
      key_label("ctrl+num5"))


# ---------------------------------------------------------------- C. Qt 事件 -> 键名
print()
print("=== C. 按键事件翻译 ===")


def name_of(key, mods=Qt.NoModifier):
    return key_name_of(QKeyEvent(QEvent.KeyPress, key, mods))


CASES = [
    (Qt.Key_Up, "up"), (Qt.Key_Down, "down"),
    (Qt.Key_Left, "left"), (Qt.Key_Right, "right"),
    (Qt.Key_Insert, "insert"), (Qt.Key_Home, "home"), (Qt.Key_End, "end"),
    (Qt.Key_PageUp, "pageup"), (Qt.Key_PageDown, "pagedown"),
    (Qt.Key_NumLock, "numlock"),
    (Qt.Key_Print, "printscreen"), (Qt.Key_ScrollLock, "scrolllock"),
    (Qt.Key_Pause, "pause"), (Qt.Key_Menu, "menu"),
    (Qt.Key_Minus, "minus"), (Qt.Key_Equal, "equal"),
    (Qt.Key_BracketLeft, "lbracket"), (Qt.Key_BracketRight, "rbracket"),
    (Qt.Key_Backslash, "backslash"), (Qt.Key_QuoteLeft, "backquote"),
]
wrong = [(hex(k), name_of(k), want) for k, want in CASES if name_of(k) != want]
check(not wrong, "方向键 / 编辑区 / 特殊键 / 符号键都能录", str(wrong))

# 主键区没被小键盘抢走
check(name_of(Qt.Key_Slash) == "slash", "主键区 / 仍是 slash", name_of(Qt.Key_Slash))
check(name_of(Qt.Key_Period) == "period", "主键区 . 仍是 period")
check(name_of(Qt.Key_Minus) == "minus", "主键区 - 仍是 minus")
check(name_of(Qt.Key_Backspace) == "", "Backspace 仍留给「清除绑定」，不当按键")

# 小键盘：同键值 + KeypadModifier
KP = Qt.KeypadModifier
kp_wrong = []
for i in range(10):
    got = name_of(getattr(Qt, f"Key_{i}"), KP)
    if got != f"num{i}":
        kp_wrong.append((i, got))
check(not kp_wrong, "小键盘 0-9 录成 num0..num9", str(kp_wrong))
check(name_of(Qt.Key_Asterisk, KP) == "num_mul", "小键盘 * 录成 num_mul")
check(name_of(Qt.Key_Plus, KP) == "num_add", "小键盘 + 录成 num_add")
check(name_of(Qt.Key_Minus, KP) == "num_sub", "小键盘 - 录成 num_sub")
check(name_of(Qt.Key_Period, KP) == "num_dot", "小键盘 . 录成 num_dot")
check(name_of(Qt.Key_Slash, KP) == "num_div", "小键盘 / 录成 num_div")
check(name_of(Qt.Key_Enter, KP) == "enter", "小键盘回车仍是回车")


# ---------------------------------------------------------------- D. 横向滚轮
print()
print("=== D. 横向滚轮 ===")


def fake_mouse(flags=0, data=0):
    return SimpleNamespace(usButtonFlags=flags, usButtonData=data,
                           usFlags=0, lLastX=0, lLastY=0)


raw = sr.RawMouse()
raw.registered = True

raw._on_raw(fake_mouse(0x0800, 120))
check(raw.wheel_hit("wheel_right"), "横向右拨 = wheel_right")
check(not raw.wheel_hit("wheel_left"), "右拨不会误报左拨")
check(not raw.wheel_hit("wheel_up"), "横向滚轮不会误报竖向")
raw.clear_wheel()

raw._on_raw(fake_mouse(0x0800, 0xFF88))
check(raw.wheel_hit("wheel_left"), "横向左拨（负数）= wheel_left")
raw.clear_wheel()

raw._on_raw(fake_mouse(0x0400, 120))
check(not raw.wheel_hit("wheel_right"), "竖向滚轮不会误报横向")
raw.clear_wheel()

check(sr.spec_parts("ctrl+wheel_right") == ["ctrl", "wheel_right"],
      "横向滚轮也能当组合键主键")


class _PollerStub:
    _down = sr.InputPoller._down


poller = _PollerStub()
poller.wheel = SimpleNamespace(raw=raw)
poller.gamepad = SimpleNamespace(down=lambda k: False)
poller._pad_suppressed = set()
check(not poller._down("wheel_left"), "没拨的时候不算按下")
raw._on_raw(fake_mouse(0x0800, 0xFF88))
check(poller._down("wheel_left"), "拨一下：_down 认得 wheel_left")


# ---------------------------------------------------------------- E. 真正录进框里
print()
print("=== E. 按键框实际录入 ===")


def press(w, key, mods=Qt.NoModifier):
    w.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, mods))


def release(w, key, mods=Qt.NoModifier):
    w.keyReleaseEvent(QKeyEvent(QEvent.KeyRelease, key, mods))


e = _KeyEdit()
press(e, Qt.Key_Up)
check(e.key_name == "up", "按 ↑ 就绑上 up", e.key_name)
press(e, Qt.Key_PageDown, Qt.ControlModifier)
check(e.key_name == "ctrl+pagedown", "Ctrl+PgDn 能组合", e.key_name)
press(e, Qt.Key_Minus)
check(e.key_name == "minus", "按 - 绑上 minus", e.key_name)
press(e, Qt.Key_5, Qt.KeypadModifier)
check(e.key_name == "num5", "小键盘 5 绑上 num5", e.key_name)
press(e, Qt.Key_5)
check(e.key_name == "5", "主键区 5 仍绑 5", e.key_name)
press(e, Qt.Key_Print)
check(e.key_name == "printscreen", "PrtSc 绑上 printscreen", e.key_name)

e2 = _KeyEdit()
e2.hasFocus = lambda: True


def wheel(w, dx=0, dy=0):
    ev = QWheelEvent(QPointF(1, 1), QPointF(1, 1), QPoint(0, 0), QPoint(dx, dy),
                     Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    w.wheelEvent(ev)


wheel(e2, dy=120)
check(e2.key_name == "wheel_up", "竖向滚轮照旧", e2.key_name)
wheel(e2, dx=120)
check(e2.key_name == "wheel_right", "往右拨录成 wheel_right", e2.key_name)
wheel(e2, dx=-120)
check(e2.key_name == "wheel_left", "往左拨录成 wheel_left", e2.key_name)

# Delete 仍能清空
press(e2, Qt.Key_Delete)
check(e2.key_name == "", "Delete 仍能清掉绑定", e2.key_name)


print()
print("=" * 56)
if BAD:
    print(f"结果：{len(BAD)} 项失败 / 共 {len(OK) + len(BAD)} 项")
    for n in BAD:
        print("  FAIL", n)
    raise SystemExit(1)
print(f"结果：全部通过（{len(OK)} 项）")
