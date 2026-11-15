"""离屏截图：v0.10 新加的「打断」一行排得下吗（含滚轮/手柄录入提示）。

跑法：python _shot_cut_row.py
输出：_tests/_shot_cut_1120.png / _tests/_shot_cut_980.png
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
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")

    TMP = Path(tempfile.mkdtemp(prefix="sr_shot_cut_"))
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
    st.stop_prev = True
    st.hotkey = "wheel_down"

    win = SettingsWindow(cfg, scfg, bank)
    win.setAttribute(Qt.WA_DontShowOnScreen, True)
    win.show()
    app.processEvents()
    win.detail.set_sound(name)
    app.processEvents()

    d = win.detail
    print("detail height:", d.height(), "needs:", d.sizeHint().height())
    print("cut row visible:", d.chk_stop_prev.isVisible(),
          "checked:", d.chk_stop_prev.isChecked())
    print("hotkey label:", d.hotkey.edit.text())

    for w, h in ((1120, 900), (980, 860)):
        win.resize(w, h)
        app.processEvents()
        out = Path(__file__).resolve().parent / f"_shot_cut_{w}.png"
        win.grab().save(str(out))
        g = d.chk_stop_prev.geometry()
        p = d.chk_stop_prev.mapTo(d, g.topLeft())
        print(f"saved {out}  detail={d.width()}x{d.height()} "
              f"chk x={p.x()} w={g.width()} right={p.x() + g.width()}")

    win.hide()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
