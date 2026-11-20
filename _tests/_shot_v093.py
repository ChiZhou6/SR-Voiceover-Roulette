"""沙箱渲染 v0.9.3 的两页：轮盘页（停止淡出 + 每套呼出键）、快捷键页（预选模式）。

必须先沙箱：SettingsWindow 里任何控件改动都会立刻写盘。
"""

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication, QScrollArea  # noqa: E402

import sr_roulette as sr  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="sr_shot093_"))
shutil.copy2(ROOT / "sounds.json", TMP / "sounds.json")
shutil.copy2(ROOT / "config.json", TMP / "config.json")
sr.SOUNDS_CONFIG_PATH = TMP / "sounds.json"
sr.CONFIG_PATH = TMP / "config.json"

from settings_window import SettingsWindow  # noqa: E402


def pump(app, n=8):
    for _ in range(n):
        app.processEvents()


def main() -> int:
    app = QApplication(sys.argv[:1])
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyhbd.ttc")

    cfg = sr.load_config()
    scfg = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
    scfg.load()
    # 给第二套盘绑个键，好看出列表里那一列
    if len(scfg.wheels) > 1:
        scfg.wheels[1].hotkey = "u"
    bank = sr.SoundBank(int(cfg["slots"]), scfg)

    w = SettingsWindow(cfg, scfg, bank)
    w.setAttribute(Qt.WA_DontShowOnScreen, True)
    w.resize(1280, 940)
    w.show()
    pump(app, 12)

    out_dir = ROOT / "_tests"

    # ---- 快捷键页（预选模式）----
    w.tabs.setCurrentIndex(1)
    pump(app)
    page = w.tabs.currentWidget()
    page.grab().save(str(out_dir / "_shot_preselect_page.png"))
    print("快捷键页已出图")

    # ---- 轮盘页：下半部分（停止淡出）----
    w.tabs.setCurrentIndex(2)
    pump(app)
    page = w.tabs.currentWidget()
    sa = page.findChild(QScrollArea)
    if sa is not None:
        bar = sa.verticalScrollBar()
        bar.setValue(bar.maximum())
        pump(app)
    page.grab().save(str(out_dir / "_shot_stopfade_page.png"))
    print("轮盘页（滚到底）已出图")

    # ---- 轮盘库那一块（每套的呼出键）----
    if sa is not None:
        bar = sa.verticalScrollBar()
        bar.setValue(int(bar.maximum() * 0.45))
        pump(app)
    page.grab().save(str(out_dir / "_shot_wheelkey_page.png"))
    print("轮盘页（中间）已出图")

    print("当前 cfg：preselect =", cfg.get("preselect_mode"),
          " stop_fade =", cfg.get("stop_fade_enabled"), cfg.get("stop_fade_ms"),
          " tap_action =", cfg.get("tap_action"))

    w.hide()
    shutil.rmtree(TMP, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
