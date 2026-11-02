"""回归：设置窗口不该把轮盘热键永久憋死。

背景（2026-11-01 用户报「设置页面会导致无法呼出轮盘」）：
    旧逻辑把「设置窗口可见」当成「正在占着键盘」就暂停热键。而程序默认
    启动就打开设置窗口（open_settings_on_start 默认 True），用户切到游戏
    后那个窗口仍在后台"可见"，热键就被永久判成暂停 —— 轮盘怎么按都不出来。

跑法：python _t_hotkey_pause.py
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


class FakeWin:
    """只回答三个问题：可见？最小化？在前台？"""

    def __init__(self, visible=True, minimized=False, active=True):
        self._v, self._m, self._a = visible, minimized, active

    def isVisible(self):
        return self._v

    def isMinimized(self):
        return self._m

    def isActiveWindow(self):
        return self._a


print("=== A 设置窗口状态判定 ===")

check(sr.settings_blocks_hotkey(None) is False, "没有设置窗口时不暂停")

# 三种"切到游戏"的情形，都必须是 False（不挡住热键）
check(sr.settings_blocks_hotkey(FakeWin(visible=False, active=False)) is False,
      "窗口已关闭 → 不暂停")
check(sr.settings_blocks_hotkey(FakeWin(visible=True, active=False)) is False,
      "窗口在后台（切去游戏了）→ 不暂停  ★这就是本次修的 bug")
check(sr.settings_blocks_hotkey(FakeWin(visible=True, minimized=True)) is False,
      "窗口最小化 → 不暂停")
check(sr.settings_blocks_hotkey(FakeWin(visible=True, active=True)) is True,
      "窗口在前台 → 暂停（免得打字把轮盘弹出来）")


class DeadWin:
    """已经被销毁的窗口对象：访问它的属性会抛 RuntimeError。"""

    def isVisible(self):
        raise RuntimeError("wrapped C/C++ object has been deleted")


check(sr.settings_blocks_hotkey(DeadWin()) is False,
      "窗口对象已销毁 → 不暂停（不会一直卡死）")


print()
print("=== B 轮询真的按新规则走 ===")


class FakeWheel:
    def __init__(self):
        self.active = False
        self.shown = 0
        self.hidden = 0
        self.raw = None

    def show_wheel(self):
        self.shown += 1
        self.active = True

    def hide_wheel(self):
        self.hidden += 1
        self.active = False

    def commit(self):
        self.active = False
        return None

    def poll_selection(self):
        pass

    def reload_entries(self):
        pass


class FakeAudio:
    def __init__(self):
        # rebuild_bindings 会通过 audio.bank.scfg 去找"每个音效的专属热键"，
        # 这里给 None 表示没有，跳过那段就行
        self.bank = SimpleNamespace(scfg=None)

    def play(self, i):
        pass

    def play_named(self, n):
        pass

    def play_repeat_last(self):
        return False

    def play_next(self):
        return False

    def stop_all(self):
        pass

    def reset_pitch(self):
        pass


cfg = dict(sr.DEFAULT_CONFIG)
cfg["hotkey"] = "y"
cfg["hold_ms"] = 60
wheel = FakeWheel()
poller = sr.InputPoller(cfg, wheel, FakeAudio(), None)

# 用一个手动开关模拟"设置窗口在前台"
state = {"down": False, "paused": False}
poller._down = lambda name: state["down"] if name == "y" else False
poller.paused = lambda: state["paused"]

# 1) 不暂停：按住够久应该弹出来
state["down"] = True
poller.tick()                      # 记下按下时刻
time.sleep(0.08)
poller.tick()
check(wheel.shown == 1, "正常状态：长按能弹出轮盘", f"shown={wheel.shown}")

# 2) 暂停（设置窗口在前台）：不该弹，而且已经开着的轮盘要被收掉
state["paused"] = True
poller.tick()
check(wheel.active is False, "切到设置窗口时，已弹出的轮盘会自动收起")
check(wheel.hidden >= 1, "确实调用过收起", f"hidden={wheel.hidden}")

shown_before = wheel.shown
time.sleep(0.08)
poller.tick()
check(wheel.shown == shown_before, "暂停期间按住不会弹出轮盘")

# 3) 关掉设置窗口（恢复）：再按一次应该能正常弹
state["paused"] = False
state["down"] = False
poller.tick()                      # 先松手，清状态
state["down"] = True
poller.tick()
time.sleep(0.08)
poller.tick()
check(wheel.shown == shown_before + 1, "恢复后长按又能弹出（不是永久卡死）",
      f"shown={wheel.shown}")

print()
print(f"通过 {len(OK)} 项，失败 {len(BAD)} 项")
if BAD:
    print("失败项：" + "；".join(BAD))
    raise SystemExit(1)
