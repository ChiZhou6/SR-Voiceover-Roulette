"""沙箱渲染「快捷键」页，确认删掉「音效直按键」说明后布局正常。

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
from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="sr_hotkey_"))
shutil.copy2(ROOT / "sounds.json", TMP / "sounds.json")
shutil.copy2(ROOT / "config.json", TMP / "config.json")
sr.SOUNDS_CONFIG_PATH = TMP / "sounds.json"
sr.CONFIG_PATH = TMP / "config.json"

from settings_window import SettingsWindow  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv[:1])
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")

    cfg = sr.load_config()
    scfg = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
    scfg.load()
    bank = sr.SoundBank(int(cfg["slots"]), scfg)

    w = SettingsWindow(cfg, scfg, bank)
    w.setAttribute(Qt.WA_DontShowOnScreen, True)
    w.show()
    app.processEvents()

    w.tabs.setCurrentIndex(1)
    app.processEvents()
    page = w.tabs.currentWidget()
    print("页面最小高度:", page.sizeHint().height(), "当前:", page.height())
    pm = page.grab()
    out = ROOT / "_tests" / "_shot_hotkey_nohint.png"
    pm.save(str(out))
    print(f"已生成 {out.name} ({pm.width()}x{pm.height()})")

    w.hide()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
