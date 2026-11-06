"""离屏截图：组合音效选中时，「快捷键 + 全局」这一行排得下吗。

跑法：python _shot_combo_global.py
输出：_tests/_shot_combo_global.png
配置全部走临时沙箱，不碰真实的 sounds.json / config.json。
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402
import sounds_config as sc  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv[:1])

    TMP = Path(tempfile.mkdtemp(prefix="sr_shot_combo_"))
    shutil.copy2(ROOT / "config.json", TMP / "config.json")
    shutil.copy2(ROOT / "sounds.json", TMP / "sounds.json")
    sr.CONFIG_PATH = TMP / "config.json"
    sr.SOUNDS_CONFIG_PATH = TMP / "sounds.json"

    from settings_window import SettingsWindow  # noqa: E402

    cfg = sr.load_config()
    scfg = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
    scfg.load()
    bank = sr.SoundBank(int(cfg["slots"]), scfg)

    keys = [k for k, _p in sr.scan_sound_files()]
    ck = "combo::shotdemo"
    scfg.combos["shotdemo"] = sc.ComboDef(
        cid="shotdemo", name="演示组合",
        items=[sc.ComboItem(sound=keys[0]), sc.ComboItem(sound=keys[1])],
    ).clamped()
    st = scfg.setting(ck)
    st.hotkey = "f8"
    st.global_hotkey = True

    win = SettingsWindow(cfg, scfg, bank)
    win.setAttribute(Qt.WA_DontShowOnScreen, True)
    win.resize(1120, 800)
    win.show()
    app.processEvents()
    win.tabs.setCurrentIndex(2)
    app.processEvents()
    win.detail.set_sound(ck)
    app.processEvents()

    out = Path(__file__).resolve().parent / "_shot_combo_global.png"
    win.grab().save(str(out))
    print("saved:", out)

    d = win.detail
    print("chk_global visible:", d.chk_global.isVisible())
    print("chk_global geo:", d.chk_global.geometry())
    print("hotkey geo:", d.hotkey.geometry())
    print("detail width:", d.width())
    win.hide()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
