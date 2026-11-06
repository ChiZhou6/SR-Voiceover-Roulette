"""回归：程序提示不再用托盘气泡（会响），改成屏幕内的无声提示条。

背景（2026-11-07 用户反馈「使用过程中后台老是有通知音」）：
Windows 10/11 会把 QSystemTrayIcon.showMessage 转成系统通知，默认带一声提示音，
Qt 没有「只显示不发声」的开关。切轮盘这类高频动作每次都叮一下，用户觉得吵。
现在全部换成自绘的 HintToast：置顶、鼠标穿透、不抢焦点、跟随不透明度，不发声。

跑法：python _t_hint_toast.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
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


cfg = dict(sr.DEFAULT_CONFIG)
cfg["opacity"] = 0.94

print("=== A. 源码里不该再有托盘气泡 ===")
src = (ROOT / "sr_roulette.py").read_text(encoding="utf-8")
# 注释里可以提到，真正调用才算
calls = [ln.strip() for ln in src.splitlines()
         if "showMessage(" in ln and not ln.strip().startswith("#")]
check(not calls, "没有任何 tray.showMessage 调用", str(calls[:3]))
check("HintToast" in src, "HintToast 已经就位")

print("\n=== B. 提示条的属性 ===")
t = sr.HintToast(cfg)
flags = t.windowFlags()
check(bool(flags & Qt.WindowStaysOnTopHint), "置顶（游戏里也看得见）")
check(bool(flags & Qt.WindowDoesNotAcceptFocus), "不抢焦点")
check(t.testAttribute(Qt.WA_TransparentForMouseEvents), "整窗鼠标穿透")
check(t.testAttribute(Qt.WA_ShowWithoutActivating), "显示时不激活窗口")

print("\n=== C. 文字与宽度 ===")
check(t.width_for("短") >= 260, "再短也留得下内边距", str(t.width_for("短")))
long_text = "这是一条很长很长的提示文字" * 12
check(t.width_for(long_text) <= 540, "太长不撑破屏幕", str(t.width_for(long_text)))
w_short = t.width_for("已切换到「默认轮盘」")
w_long = t.width_for("已切换到「默认轮盘」" * 3)
check(w_long >= w_short, "字多就更宽（不会挤成一团）", f"{w_short} -> {w_long}")

print("\n=== D. 三种级别 ===")
t.show_hint("已切换到「默认轮盘」")
app.processEvents()
check(t.text == "已切换到「默认轮盘」", "正文记下来了")
check(t.level == "info", "默认是 info")
check(t.isVisible(), "已经显示出来")
info_tint = t._tint().name()

t.show_hint("麦克风掉线了", "warn")
app.processEvents()
check(t.level == "warn", "warn 级别")
warn_tint = t._tint().name()
check(warn_tint != info_tint, "warn 配色和 info 不同", f"{info_tint} vs {warn_tint}")

t.show_hint("鼠标原始输入注册失败", "error")
app.processEvents()
check(t.level == "error", "error 级别")
err_tint = t._tint().name()
check(err_tint not in (info_tint, warn_tint), "error 又是另一种颜色", err_tint)

print("\n=== E. 边界 ===")
show_before = t.isVisible()
t.show_hint("   ")
app.processEvents()
check(t.isVisible() == show_before, "空文字直接忽略，不会弹个空壳", str(t.isVisible()))

t.show_hint("x" * 300, "info")
app.processEvents()
check(t.isVisible(), "超长文字也能显示（靠省略号收尾，不崩）")

# 连续弹两条：同一时刻只留最后一条，不叠两个窗口
t.show_hint("第一条")
app.processEvents()
t.show_hint("第二条")
app.processEvents()
check(t.text == "第二条", "后来的提示覆盖前一条")

print("\n=== F. 不发声 ===")
# 走的就是自绘 paintEvent，没有任何声音 API；这里钉住"没有引入发声调用"
for kw in ("winsound", "QSoundEffect", "MessageBeep", "QApplication.beep"):
    check(kw not in src, f"源码里没有 {kw}")

print("\n=== G. 去重与关动画 ===")
import time  # noqa: E402

t2 = sr.HintToast(dict(sr.DEFAULT_CONFIG))
t2.show_hint("麦克风掉线了")
app.processEvents()
at1 = t2._last_at
time.sleep(0.05)
t2.show_hint("麦克风掉线了")
app.processEvents()
check(t2._last_at == at1, "同一句话 6 秒内不重复弹（麦克风抖动时不至于一直闪）")

t2.show_hint("换一句话")
app.processEvents()
check(t2._last_at != at1, "换了内容照常弹")

cfg_off = dict(sr.DEFAULT_CONFIG)
cfg_off["animations"] = False
t3 = sr.HintToast(cfg_off)
t3.show_hint("麦克风掉线了", "warn", 400)
app.processEvents()
check(t3.isVisible(), "关掉动画时提示照样看得见（不像暂停提示那样直接不显示）")
check(abs(t3.t - 0.5) < 1e-6, "关动画时是静止帧，不做淡入淡出", str(t3.t))

print()
print(f"通过 {len(OK)} 项，失败 {len(BAD)} 项")
if BAD:
    print("失败项：" + "；".join(BAD))
    raise SystemExit(1)
