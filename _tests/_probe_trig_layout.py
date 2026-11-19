"""检查设置窗口加了「触发/条件」两行之后有没有被挤爆。

**必须沙箱化**：SettingsWindow 里任何改动都会立刻写盘，直接跑会改掉真实的
sounds.json（第一次写这个脚本就踩了，把某个音效的触发方式改成了"长按连发"）。
所以这里把 sr.SOUNDS_CONFIG_PATH / sr.CONFIG_PATH 指到临时目录，
拿真实配置**复制一份**出来改，绝不碰原文件。

跑法：python _probe_trig_layout.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
# 不加载中文字体的话，离屏渲染出来全是方块，看不出排版问题
QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")

import sr_roulette as sr  # noqa: E402
from sounds_config import SoundsConfig  # noqa: E402
from settings_window import SettingsWindow  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="sr_probe_"))
shutil.copy2(sr.SOUNDS_CONFIG_PATH, tmp / "sounds.json")
shutil.copy2(sr.CONFIG_PATH, tmp / "config.json")
sr.SOUNDS_CONFIG_PATH = tmp / "sounds.json"
sr.CONFIG_PATH = tmp / "config.json"
print("沙箱:", tmp)


def build(radius: int = 180, height: int | None = None):
    cfg = dict(sr.DEFAULT_CONFIG)
    cfg["wheel_radius"] = radius
    scfg = SoundsConfig(sr.SOUNDS_CONFIG_PATH)
    scfg.load()
    bank = sr.SoundBank(16, scfg)
    win = SettingsWindow(cfg, scfg, bank)
    if height:
        win.resize(1120, height)
    win.show()
    app.processEvents()
    return win, scfg, bank


def report(win, tag: str) -> None:
    p = win.preview
    h = p.parentWidget()
    need = p.height() + 12 + 14 + 20 + 4     # 上边距 + 下边距 + 标题行 + 间距
    gap = h.height() - need
    print(f"[{tag}] 窗口 {win.width()}x{win.height()} 预览 {p.width()}x{p.height()} "
          f"容器 {h.height()} 余量 {gap:+d}px "
          + ("OK" if gap >= 0 else "★ 预览被挤掉"))
    det = win.detail
    print(f"       卡片高 {det.height()}，最后一行底部 "
          f"{det.unlock_count.mapTo(det, det.unlock_count.rect().bottomLeft()).y()}")


win, scfg, bank = build()
report(win, "默认 840 / 直径 180")

det = win.detail
det.set_sound(bank.full_at(0))
app.processEvents()
for nm in ("title", "volume", "pitch_mode", "speed_mode", "pitch_window",
           "hotkey", "trigger_mode", "repeat_ms", "unlock_mode",
           "unlock_key", "unlock_ms", "unlock_count"):
    w = getattr(det, nm, None)
    if w is None:
        continue
    tl = w.mapTo(det, w.rect().topLeft())
    br = w.mapTo(det, w.rect().bottomRight())
    print(f"  {nm:15s} y={tl.y():3d}..{br.y():3d} x={tl.x():3d}..{br.x():3d} "
          f"可见={w.isVisible()}")

print("\n默认音效（点击触发）：间隔框该藏、解锁三项该藏")
print("  repeat_ms:", det.repeat_ms.isVisible(), "| unlock_key:",
      det.unlock_key.isVisible(), "| unlock_count:", det.unlock_count.isVisible())

det.trigger_mode.setCurrentIndex(3)     # 长按连续触发
det.unlock_mode.setCurrentIndex(1)      # 条件解锁
app.processEvents()
print("改成「长按连续触发 + 条件解锁」后：")
print("  repeat_ms:", det.repeat_ms.isVisible(), "| unlock_key:",
      det.unlock_key.isVisible(), "| unlock_count:", det.unlock_count.isVisible())
win.grab().save(str(Path(__file__).parent / "_shot_trig_detail.png"))

# 组合条目：变调那几行藏掉，触发/条件要留着
scfg.new_combo("测试组合")
det.set_sound(scfg.combo_key("c1"))
app.processEvents()
print("\n组合条目：trigger_mode 可见 =", det.trigger_mode.isVisible(),
      "| pitch_mode 可见 =", det.pitch_mode.isVisible())

win2, _, _ = build(radius=215)
report(win2, "默认 840 / 直径 215")
win2.close()

win3, _, _ = build(height=800)
report(win3, "最小 800 / 直径 180")
win3.close()

win.close()
print("\n截图已存 _shot_trig_detail.png")
