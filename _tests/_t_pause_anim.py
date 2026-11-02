"""回归：组合按键 / 暂停模式 / 弹出与释放动画。

跑法：python _t_pause_anim.py

三块各验一遍：
  A 组合键解析——"ctrl+shift+y" 要能拆、能比、能显示
  B 暂停模式——中心松手进暂停、怎么解除、暂停期间哪些被挡住
  C 动画——开关生效、动画跑完状态归位、关窗动画不会把新弹出的轮盘藏掉
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


def pump(ms: int) -> None:
    """转一会儿事件循环，让 QVariantAnimation 真的跑起来。"""
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.004)


print("=== A 组合键解析 ===")

check(sr.spec_parts("y") == ["y"], "单键原样通过")
check(sr.spec_parts("ctrl+shift+y") == ["ctrl", "shift", "y"], "三段组合按序拆开")
check(sr.norm_spec("shift+ctrl+y") == sr.norm_spec("ctrl+shift+y"),
      "修饰键顺序不同视为同一个绑定", sr.norm_spec("shift+ctrl+y"))
check(sr.norm_spec("lctrl+y") == sr.norm_spec("ctrl+y"),
      "左右 Ctrl 视为同一个修饰键")
check(sr.spec_parts("ctrl+") == ["ctrl"], "尾部多余的加号不会炸")
check(sr.spec_parts("") == [], "空绑定返回空列表")
check(sr.spec_label("ctrl+shift+y") == "Ctrl + Shift + Y", "托盘用的写法带空格",
      sr.spec_label("ctrl+shift+y"))

# _down 要求组合里每一部分都按着
_down_state = {"y": False, "ctrl": False}
sr_orig_is_down = sr.is_down
sr.is_down = lambda vk: _down_state.get({0x59: "y", 0x11: "ctrl"}.get(vk, ""), False)


class _W:
    active = False
    raw = None


poller_t = sr.InputPoller(dict(sr.DEFAULT_CONFIG), _W(), SimpleNamespace(bank=SimpleNamespace(scfg=None),
                                                                       play=lambda i: None,
                                                                       play_named=lambda n: None,
                                                                       play_repeat_last=lambda: False,
                                                                       play_next=lambda: False,
                                                                       stop_all=lambda: None), None)
check(poller_t._down("ctrl+y") is False, "组合键：一个都没按时不算按下")
_down_state["y"] = True
check(poller_t._down("ctrl+y") is False, "组合键：只按了主键不算按下")
_down_state["ctrl"] = True
check(poller_t._down("ctrl+y") is True, "组合键：都按着才算按下")
_down_state["y"] = False
check(poller_t._down("ctrl+y") is False, "组合键：松开主键立刻不算")
sr.is_down = sr_orig_is_down

# 按键框真的能录到组合（不是只有解析层支持）
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
import settings_window as sw  # noqa: E402

box = sw.KeyBox("y", 128)
QTest.keyClick(box.edit, Qt.Key_Y, Qt.ControlModifier | Qt.ShiftModifier)
check(box.key_name == "ctrl+shift+y", "按键框录得下组合键", box.key_name)
check(box.edit.text() == "Ctrl+Shift+Y", "框里显示成 Ctrl+Shift+Y", box.edit.text())
QTest.keyClick(box.edit, Qt.Key_G, Qt.AltModifier)
check(box.key_name == "alt+g", "再按一个组合会覆盖之前的", box.key_name)
QTest.keyClick(box.edit, Qt.Key_K)
check(box.key_name == "k", "不按修饰键就是单键", box.key_name)
QTest.keyClick(box.edit, Qt.Key_Delete)
check(box.key_name == "", "Delete 能清空绑定", box.key_name)


print()
print("=== B 暂停模式 ===")


class FakeAudio:
    def __init__(self):
        self.bank = SimpleNamespace(scfg=None)
        self.played = []
        self.stopped = 0
        self.tap = 0

    def play(self, i):
        self.played.append(i)

    def play_named(self, n):
        self.played.append(n)

    def play_repeat_last(self):
        self.tap += 1
        return True

    def play_next(self):
        self.tap += 1
        return True

    def stop_all(self):
        self.stopped += 1

    def reset_pitch(self):
        pass


class FakeWheel:
    def __init__(self):
        self.active = False
        self.raw = None
        self.next_commit = None
        self.shown = 0

    def show_wheel(self):
        self.shown += 1
        self.active = True

    def hide_wheel(self, animate=True, keep_flash=False):
        self.active = False

    def commit(self):
        self.active = False
        return self.next_commit

    def poll_selection(self):
        pass


cfg = dict(sr.DEFAULT_CONFIG)
cfg["hotkey"] = "y"
cfg["hold_ms"] = 40
cfg["tap_action"] = "repeat_last"
wheel = FakeWheel()
audio = FakeAudio()
events = []
poller = sr.InputPoller(cfg, wheel, audio, None)
poller.on_pause_changed = lambda on: events.append(on)

state = {"down": False}
poller._down = lambda name: state["down"] if name == "y" else False
poller.paused = lambda: False


def long_press(commit_idx, hold_ms=60):
    """按住热键 → 弹出轮盘 → 松手（模拟一次完整的呼出+释放）。"""
    wheel.next_commit = commit_idx
    state["down"] = True
    poller.tick()
    time.sleep(hold_ms / 1000.0)
    poller.tick()          # 这一步弹出
    state["down"] = False
    poller.tick()          # 这一步松手


# 1) 正常选音效松手：只播放，不进入暂停
long_press(3)
check(audio.played == [3], "选中扇区松手：播放音效", str(audio.played))
check(poller.user_paused is False, "选了音效不会进暂停")
check(audio.stopped == 0, "没有误触发 stop_all")

# 2) 中心松手：停止 + 进入暂停
long_press(None)
check(audio.stopped == 1, "中心松手会先掐掉正在响的声音", str(audio.stopped))
check(poller.user_paused is True, "中心松手进入暂停")
check(events == [True], "暂停状态变化通知了外面（用来播动画）", str(events))

# 3) 暂停期间轻按热键：不许播
tap_before = audio.tap
state["down"] = True
poller.tick()
state["down"] = False
poller.tick()
check(audio.tap == tap_before, "暂停期间轻按热键被挡下", f"tap={audio.tap}")

# 4) 暂停期间额外快捷键：不许播
extra_before = list(audio.played)
poller._extra = [("g", lambda: audio.play_named("g"))]
poller._extra_prev = {"g": False}
poller._down = lambda name: True if name == "g" else (state["down"] if name == "y" else False)
poller.tick()
check(audio.played == extra_before, "暂停期间额外快捷键被挡下", str(audio.played))
poller._down = lambda name: state["down"] if name == "y" else False
poller._extra = []
poller._extra_prev = {}

# 5) 暂停期间长按：轮盘照样能弹（这是唯一的自救入口）
shown_before = wheel.shown
long_press(None)
check(wheel.shown == shown_before + 1, "暂停期间长按仍能弹出轮盘（留活路）")
check(poller.user_paused is False, "暂停中再在中心松手一次 = 解除暂停")
check(events == [True, False], "恢复也通知了外面", str(events))

# 6) 暂停中选音效松手：播放 + 自动恢复
long_press(None)                        # 先进暂停
check(poller.user_paused is True, "（前置）已暂停")
long_press(5)                           # 再选音效
check(poller.user_paused is False, "暂停中选音效松手 = 播放并恢复")
check(audio.played[-1] == 5, "确实播了选中的音效")


print()
print("=== C 动画 ===")

cfg2 = dict(sr.DEFAULT_CONFIG)
cfg2["animations"] = True
w = sr.WheelWidget(cfg2)
check(w.anim_on() is True, "默认开启动画")

cfg_off = dict(sr.DEFAULT_CONFIG)
cfg_off["animations"] = False
w_off = sr.WheelWidget(cfg_off)
w_off.play_open_anim()
check(w_off.anim_busy() is False, "关掉动画后弹出不做缩放（瞬间到位）")

w.play_open_anim()
check(w.anim_busy() is True, "开始弹出动画时处于缩放/半透明状态",
      f"scale={w.anim_scale} alpha={w.anim_alpha}")
pump(260)
check(w.anim_busy() is False, "弹出动画结束后状态归位",
      f"scale={w.anim_scale} alpha={w.anim_alpha}")

# 关窗动画跑完才真的 hide
done = []
w.play_close_anim(lambda: done.append("hidden"))
check(done == [], "关窗动画刚开始时还没有隐藏")
pump(280)
check(done == ["hidden"], "关窗动画跑完才隐藏", str(done))

# 关键保护：关窗动画没跑完就重新弹出，不能被旧的回调藏掉
w.play_close_anim(lambda: done.append("stale"))
pump(30)
w.play_open_anim()                      # 正在关的时候又弹出来
pump(320)
check(done == ["hidden"], "关到一半又弹出时，旧回调不会把新轮盘藏掉", str(done))
check(w.anim_busy() is False, "重新弹出后动画正常打完")

# 释放动画期间选中格的高亮要留着，否则"甩出去"那一下看不出是哪个
ctl = sr.WheelController(dict(sr.DEFAULT_CONFIG), None, SimpleNamespace(registered=False, drop=lambda: None),
                         None)
ctl.widget.bank = None
ctl.active = True
ctl.selected = 4
ctl.widget.selected = 4
idx = ctl.commit()
check(idx == 4, "commit 返回选中的下标")
check(ctl.widget.selected == 4, "释放动画期间选中格保持高亮")
check(ctl.active is False, "commit 之后立刻认为轮盘已关闭（动画期间不读鼠标）")

print()
print("=== D 释放音效：整盘立刻消失，只留选中那一格 ===")

from PySide6.QtGui import QImage  # noqa: E402


class FakeBank:
    """只为渲染服务的假音效库：够 len() 和 name_at() 用就行。"""

    def __init__(self, names):
        self.names = list(names)

    def __len__(self):
        return len(self.names)

    def name_at(self, i):
        return self.names[i]


fb = FakeBank([f"音效{i}" for i in range(6)])


def opaque_in(img, r=None):
    """数不透明像素；r 给了就只数中心那块方块。"""
    img = img.convertToFormat(QImage.Format_ARGB32)
    cx, cy = img.width() // 2, img.height() // 2
    if r is None:
        x0, x1, y0, y1 = 0, img.width(), 0, img.height()
    else:
        x0, x1, y0, y1 = cx - r, cx + r, cy - r, cy + r
    n = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            if ((img.pixel(x, y) >> 24) & 0xFF) > 8:
                n += 1
    return n


cfg_d = dict(sr.DEFAULT_CONFIG)
w2 = sr.WheelWidget(cfg_d)
w2.bank = fb
w2.resize(560, 560)
w2.selected = 2
check(opaque_in(w2.grab().toImage(), r=30) > 0,
      "对照：完整轮盘的中心是不透明的")

done = []
w2.play_flash_anim(lambda: done.append("hidden"))
check(w2.anim_flash is True, "闪出开始后进入 flash 状态")
check(done == [], "闪出刚开始还没有隐藏窗口")
during = w2.grab().toImage()
check(opaque_in(during, r=30) == 0, "闪出期间整盘已经消失（中心全透明）",
      f"中心不透明像素={opaque_in(during, r=30)}")
check(opaque_in(during) > 0, "选中那一格还在画", f"全图不透明像素={opaque_in(during)}")
pump(320)
check(done == ["hidden"], "闪出跑完才真正隐藏", str(done))
check(w2.anim_flash is False, "闪出结束后 flash 状态复位")

# 关掉动画：直接隐藏，不能留下一个只画半格的残影
cfg_off2 = dict(sr.DEFAULT_CONFIG)
cfg_off2["animations"] = False
w3 = sr.WheelWidget(cfg_off2)
w3.bank = fb
w3.selected = 1
done2 = []
w3.play_flash_anim(lambda: done2.append("hidden"))
check(done2 == ["hidden"], "关掉动画时释放立刻完成")
check(w3.anim_flash is False, "关掉动画时不进入 flash 状态")

# 闪到一半又弹出：旧回调不能把新轮盘藏掉
w2.play_flash_anim(lambda: done.append("stale"))
pump(40)
w2.play_open_anim()
pump(320)
check(done == ["hidden"], "闪到一半又弹出时，旧回调不会藏掉新轮盘", str(done))
check(w2.anim_flash is False, "重新弹出后 flash 状态是干净的")

# 控制器这一层：选中了音效松手，走的是闪出动画
ctl3 = sr.WheelController(
    dict(sr.DEFAULT_CONFIG), fb,
    SimpleNamespace(registered=False, drop=lambda: None), None,
)
ctl3.widget.bank = fb
ctl3.widget.show()
ctl3.selected = 3
ctl3.widget.selected = 3
ctl3.commit()
check(ctl3.widget.anim_flash is True, "commit 松手走闪出动画（整盘消失）")
ctl3.widget.hide()

print()
print(f"通过 {len(OK)} 项，失败 {len(BAD)} 项")
if BAD:
    print("失败项：" + "；".join(BAD))
    raise SystemExit(1)
