"""沙箱渲染「说明」页的补充区，确认 v0.9.2 新增的「按键」段落排版正常。"""

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

TMP = Path(tempfile.mkdtemp(prefix="sr_help_"))
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
    w.tabs.setCurrentIndex(w.tabs.count() - 1)
    app.processEvents()

    page = w.tabs.currentWidget()
    area = page.findChild(QScrollArea)
    inner = area.widget()
    inner.adjustSize()
    app.processEvents()
    pm = inner.grab()
    out = ROOT / "_tests" / "_shot_help_keys.png"
    pm.save(str(out))
    print(f"已生成 {out.name} ({pm.width()}x{pm.height()})")
    w.hide()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
