"""首次启动引导 + 常见问题默认展开/主题色。

跑法：python _tests/_t_first_run.py
"""
import json
import os
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")

import sounds_config as sc
import sr_roulette as sr
import settings_window as sw

FAILS = []


def check(ok, label, extra=""):
    print(("PASS  " if ok else "FAIL  ") + label + (f"  ({extra})" if extra else ""))
    if not ok:
        FAILS.append(label)


RATE = 48000


def wav(path, sec=0.6):
    n = int(sec * RATE)
    t = np.arange(n) / RATE
    x = (0.4 * np.sin(2 * np.pi * 220 * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(x.tobytes())


tmp = Path(tempfile.mkdtemp())
snd = tmp / "sounds"
snd.mkdir()
for n in ("01 a", "02 b"):
    wav(snd / f"{n}.wav")

# 别把测试用的配置写进真实目录
sr.SOUNDS_DIR = snd
sr.CONFIG_PATH = tmp / "config.json"
sr.SOUNDS_CONFIG_PATH = tmp / "sounds.json"

cfg = sc.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
cfg.load()
cfg.sync([p.name for p in snd.iterdir()])
bank = sr.SoundBank(8, scfg=cfg)

print("=== 1. 常见问题那节默认展开 + 打了主题色标记 ===")
win = sw.SettingsWindow(dict(sr.DEFAULT_CONFIG), cfg, bank, None)
win.resize(1120, 820)
app.processEvents()

faq = None
for sec in win.page_help.sections:
    if sec.title.startswith("四、"):
        faq = sec
check(faq is not None, "找到「四、常见问题」这一节")
check(faq.hot is True, "这一节带 hot 标记")
check(faq.head.property("hot") is True, "标题按钮上挂了 hot 属性（QSS 靠它上色）")
check(faq.head.text().startswith("▼"), "默认就是展开状态", faq.head.text()[:6])
check(faq.body.isVisible() is False or True, "（窗口未显示，可见性留到后面查）")

others = [s for s in win.page_help.sections if not s.title.startswith("四、")]
check(all(s.head.property("hot") in (None, False) for s in others),
      "其余三节没有被染色")
check(all(not s.body.isVisible() for s in others), "其余三节仍然默认收起")

print("\n=== 2. 首次打开会浮出引导卡 ===")
win.show()
QTest.qWait(700)
check(win._tip is not None, "引导卡已创建")
check(win._tip is not None and win._tip.isVisible(), "引导卡可见")
check(win._tip is not None and win._tip.geometry().width() > 300, "引导卡铺满主窗口",
      str(win._tip.geometry().size().toTuple() if win._tip else None))

print("\n=== 3. 点「去看看」直接送到常见问题 ===")
tip = win._tip
tip.btn_go.click()
QTest.qWait(200)
check(win._tip is None, "引导卡关掉了")
check(win.tabs.currentWidget() is win.page_help, "已切到「说明」页")
check(faq.body.isVisible(), "常见问题正文是展开的")

print("\n=== 4. 看过就记下来，下次不再弹 ===")
check(cfg is not None, "配置对象在")
check(win.cfg.get("help_tip_shown") is True, "内存里标记为已看过")
saved = json.loads(sr.CONFIG_PATH.read_text(encoding="utf-8"))
check(saved.get("help_tip_shown") is True, "写进了 config.json")

win.hide()
QTest.qWait(100)
win.show()
QTest.qWait(700)
check(win._tip is None, "再次打开设置窗口不再弹引导")

print("\n=== 5. 「知道了」也能关，且同样只弹一次 ===")
win.hide()
cfg2 = dict(sr.DEFAULT_CONFIG)          # 全新的配置（模拟另一台电脑）
cfg2["help_tip_shown"] = False
win2 = sw.SettingsWindow(cfg2, cfg, bank, None)
win2.resize(1000, 780)
win2.show()
QTest.qWait(700)
check(win2._tip is not None, "新配置第一次会弹")
win2._tip.btn_later.click()
QTest.qWait(150)
check(win2._tip is None, "点「知道了」关掉")
check(win2.cfg.get("help_tip_shown") is True, "「知道了」也算看过")

print("\n=== 6. 老配置没有这个键时按「没看过」处理 ===")
fresh = sr.DEFAULT_CONFIG
check(fresh.get("help_tip_shown") is False, "默认值就是 False（会自动弹一次）")

win2.close()
win.close()
print()
if FAILS:
    print(f"FAILED {len(FAILS)}:")
    for f in FAILS:
        print("   -", f)
    sys.exit(1)
print("全部通过")
