"""界面到链路的集成测试：在「麦克风」页勾上开关，链路要真的搭起来。

模拟用户操作，不点鼠标，直接改控件状态走信号链——
这样能验证 _push -> changed -> apply_audio_cfg -> rebuild 这条路是通的。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from PySide6.QtWidgets import QApplication

import sr_roulette as sr
from settings_window import SettingsWindow
from sounds_config import SoundsConfig

FAILS: list[str] = []


def check(ok: bool, title: str, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + title + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(title)


def pump(app, ms: int) -> None:
    t0 = time.monotonic()
    while (time.monotonic() - t0) * 1000 < ms:
        app.processEvents()
        time.sleep(0.005)


app = QApplication([])
cfg = dict(sr.DEFAULT_CONFIG)
scfg = SoundsConfig(sr.SOUNDS_CONFIG_PATH)
scfg.load()
bank = sr.SoundBank(sr.MAX_SLOTS, scfg)

engine = sr.AudioEngine(bank, cfg)
engine.start()

win = SettingsWindow(cfg, scfg, bank, engine)
win.audio_changed.connect(engine.apply_audio_cfg)
app.processEvents()

p = win.page_mic
print("== 初始状态（默认关闭）==")
check(not engine.capture and engine.cable is None, "默认不采集、不送声",
      f"capture={engine.capture} cable={engine.cable}")
check(engine._sink is not None, "耳机那一路照常在跑")          # noqa: SLF001

print("\n== 勾上开关 ==")
p.chk_enable.setChecked(True)
pump(app, 200)
st = engine.audio_status()
print(f"   采集={st['mic']} 送声={st['cable']} 错误={st['error'] or '无'}")
check(engine.capture is not None, "麦克风开始采集", st["mic"])
check(engine.cable is not None, "虚拟声卡那一路搭起来了", st["cable"])
check(cfg["mic_enabled"] is True, "配置里记下了启用状态")

print("\n== 播一个音效，看两个出口是不是都在收数据 ==")
before_head = engine.mixer.rendered_frames
before_cable = engine.cable.rendered_frames if engine.cable else 0
ok = engine.play(0)
check(ok, "播放成功")
pump(app, 600)
head_now = engine.mixer.rendered_frames
cable_now = engine.cable.rendered_frames if engine.cable else 0
check(head_now > before_head, "耳机出口在消费数据",
      f"{before_head} -> {head_now}")
check(cable_now > before_cable, "虚拟声卡出口在消费数据",
      f"{before_cable} -> {cable_now}")

print("\n== 音量跟着滑块走 ==")
p.snd_gain.slider.setValue(50)
p.mic_gain.slider.setValue(150)
pump(app, 100)
check(abs(engine.cable.volume - 0.5) < 1e-6, "音效·送对方 = 50%", str(engine.cable.volume))
check(abs(engine.cable.mic_gain - 1.5) < 1e-6, "原声·送对方 = 150%", str(engine.cable.mic_gain))

print("\n== 关掉本地监听 ==")
p.chk_monitor.setChecked(False)
pump(app, 200)
check(engine.mixer.volume == cfg["volume"], "耳机那一路参数仍在（没被销毁）")
check(cfg["monitor_enabled"] is False, "配置记下了关闭本地监听")

print("\n== 再关掉注入，链路要退回去 ==")
p.chk_enable.setChecked(False)
pump(app, 200)
check(engine.capture is None, "采集已停止")
check(engine.cable is None, "虚拟声卡那一路已拆")
# 本地监听被关了，程序应该兜底把耳机那一路重新拉起来，不能变成哑巴
check(engine._sink is not None, "两路都不开时自动保底开耳机")       # noqa: SLF001

print("\n== 说话测试按钮 ==")
p.chk_enable.setChecked(True)
pump(app, 150)
p._toggle_test()
pump(app, 400)
lvl = p.meter.value()
check(p._timer.isActive(), "测试计时器在跑")
print(f"   电平条数值={lvl}")
p._toggle_test()
check(not p._timer.isActive(), "再点一下能停下来")

engine.stop_outputs()
win.deleteLater()
print()
if FAILS:
    print(f"FAILED {len(FAILS)}:")
    for f in FAILS:
        print("   -", f)
    sys.exit(1)
print("ALL PASS")
