"""把配置窗口离屏渲染成图，用来确认布局。

用 WA_DontShowOnScreen 让窗口不真的弹出来，但仍然走完整的布局与绘制。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402
from settings_window import SettingsWindow  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv[:1])

    cfg = sr.load_config()
    scfg = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
    scfg.load()
    bank = sr.SoundBank(int(cfg["slots"]), scfg)

    w = SettingsWindow(cfg, scfg, bank)
    w.setAttribute(Qt.WA_DontShowOnScreen, True)
    w.resize(1120, 720)
    w.show()
    app.processEvents()

    # 逐页截图
    for idx, name in enumerate(["library", "hotkey", "wheel"]):
        w.tabs.setCurrentIndex(idx)
        app.processEvents()
        pm = w.grab()
        out = ROOT / f"settings_{name}.png"
        pm.save(str(out))
        print(f"已生成 {out.name}  ({pm.width()}x{pm.height()})")

    w.hide()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
