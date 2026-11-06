"""离屏截图：新增的「停止」那一行在最小窗口下排得下吗。

跑法：python _shot_stop_key.py
输出：_tests/_shot_stop_key_1120.png / _tests/_shot_stop_key_980.png
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
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv[:1])
    # 离屏渲染必须自己挂中文字体，否则全是方块
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")

    TMP = Path(tempfile.mkdtemp(prefix="sr_shot_stop_"))
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
    name = keys[0]
    st = scfg.setting(name)
    st.unlock_mode = "key"
    st.unlock_key = "g"
    st.unlock_ms = 10000
    st.unlock_count = 1
    st.stop_keys = ["3"]

    win = SettingsWindow(cfg, scfg, bank)
    win.setAttribute(Qt.WA_DontShowOnScreen, True)
    win.show()
    app.processEvents()
    win.detail.set_sound(name)
    app.processEvents()

    d = win.detail
    print("detail fixed height:", d.height())
    print("body sizeHint:", d.body.sizeHint().height(),
          "body height:", d.body.height())
    print("stop boxes:", [b.key_name for b in d._stop_boxes])
    print("add btn visible:", d.btn_add_stop.isVisible())
    print("stop_hint text:", d.lbl_stop_hint.text())

    for w, h in ((1120, 880), (980, 840)):
        win.resize(w, h)
        app.processEvents()
        out = Path(__file__).resolve().parent / f"_shot_stop_key_{w}.png"
        win.grab().save(str(out))
        print(f"saved {out}  detail={d.width()}x{d.height()}")

    # 3 个停止键：最挤的情况（说明文字要让位、加号要藏起来）
    st.stop_keys = ["3", "f4", "f5"]
    d.set_sound(name)
    app.processEvents()
    print("3 键后 boxes:", [b.key_name for b in d._stop_boxes],
          "add:", d.btn_add_stop.isVisible(),
          "hint:", d.lbl_stop_hint.isVisible())
    for w, h in ((1120, 880), (980, 840)):
        win.resize(w, h)
        app.processEvents()
        out = Path(__file__).resolve().parent / f"_shot_stop_key3_{w}.png"
        win.grab().save(str(out))
        print(f"saved {out}")
    win.hide()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
