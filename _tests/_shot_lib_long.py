"""沙箱渲染音效库：验证超长文件名不再把格子撑宽、文件夹筛选框正常。

跑法：python _tests/_shot_lib_long.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="sr_lib_"))
SOUNDS = TMP / "sounds"
SOUNDS.mkdir(parents=True)
SUB = SOUNDS / "整活"
SUB.mkdir()

sr.SOUNDS_CONFIG_PATH = TMP / "sounds.json"
sr.CONFIG_PATH = TMP / "config.json"
sr.SOUNDS_DIR = SOUNDS
shutil.copy2(ROOT / "config.json", sr.CONFIG_PATH)

src = ROOT / "sounds" / "冰冰冰.wav"
LONG = "Surround+Sound+(Explicit)-JJD&21+Savage&Baby+Tate_metool (1).wav"
shutil.copy2(src, SOUNDS / LONG)
shutil.copy2(src, SOUNDS / "normal no more imps.wav")
shutil.copy2(src, SOUNDS / "怒.wav")
shutil.copy2(src, SUB / "巴哈哈哈哈哈.wav")
shutil.copy2(src, SUB / "哎呀呀呀呀呀呀呀呀呀呀呀呀.wav")

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

    lib = w.page_lib
    print("筛选框条目:", [lib.folder_filter.itemText(i) for i in range(lib.folder_filter.count())])

    vp = lib.scroll.viewport().width()
    cells = [lib.grid.itemAt(i).widget() for i in range(lib.grid.count())]
    cells = [c for c in cells if c is not None and c.objectName() == "Cell"]
    widest = max((c.width() for c in cells), default=0)
    overflow = [c.path.name for c in cells if c.x() + c.width() > vp + 1]
    print(f"视口宽 {vp}px，格子最宽 {widest}px，越界格子 {len(overflow)} 个 {overflow}")

    out = ROOT / "_tests" / "_shot_lib_long.png"
    lib.grab().save(str(out))
    print("已生成", out.name)

    # 选中子文件夹再截一张（deleteLater 的旧格子要等 DeferredDelete 才真的走掉，
    # 否则截图里新旧两批会叠在一起）
    idx = lib.folder_filter.findData("整活")
    lib.folder_filter.setCurrentIndex(idx)
    app.processEvents()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    print("切到「整活」后格子:", [
        c.path.name for c in (lib.grid.itemAt(i).widget() for i in range(lib.grid.count()))
        if hasattr(c, "path")
    ])
    lib.grab().save(str(ROOT / "_tests" / "_shot_lib_folder.png"))
    print("已生成 _shot_lib_folder.png")

    w.hide()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
