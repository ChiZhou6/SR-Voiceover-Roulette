"""回归：勾「停止淡出」之后，值真的写进了配置（v0.9.3 的 bug）。

v0.9.3 第一版把勾选框和滑块只接到「灰化」那个槽，没接 `_push()`：
界面上勾是勾上了，cfg 里一直是 False，引擎照旧按 12ms 硬切 ——
用户看到的现象就是"开了淡出但没生效"。这个脚本守着这条线。

配置全部走临时沙箱，不碰真实的 config.json / sounds.json。
跑法：python _tests/_t_stop_fade_ui.py
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402

FAILS: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAILS.append(label)


def main() -> int:
    app = QApplication.instance() or QApplication([])
    tmp = Path(tempfile.mkdtemp(prefix="sr_fade_ui_"))
    shutil.copy2(ROOT / "config.json", tmp / "config.json")
    shutil.copy2(ROOT / "sounds.json", tmp / "sounds.json")
    sr.CONFIG_PATH = tmp / "config.json"
    sr.SOUNDS_CONFIG_PATH = tmp / "sounds.json"
    sr.SOUNDS_DIR = tmp / "sounds"
    (tmp / "sounds").mkdir(exist_ok=True)

    from settings_window import SettingsWindow  # noqa: E402

    cfg = sr.load_config()
    cfg["stop_fade_enabled"] = False
    cfg["stop_fade_ms"] = 400
    scfg = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
    scfg.load()
    bank = sr.SoundBank(int(cfg["slots"]), scfg)
    win = SettingsWindow(cfg, scfg, bank)
    win.close()
    page = win.page_wheel

    print("1. 勾选框直接改配置")
    check(cfg.get("stop_fade_enabled") is False, "初始是关的")
    page.chk_stop_fade.setChecked(True)
    app.processEvents()
    check(cfg.get("stop_fade_enabled") is True,
          "勾上之后 cfg 里同步变成 True", str(cfg.get("stop_fade_enabled")))
    page.chk_stop_fade.setChecked(False)
    app.processEvents()
    check(cfg.get("stop_fade_enabled") is False,
          "取消勾选也同步", str(cfg.get("stop_fade_enabled")))

    print("2. 滑块改时长")
    page.chk_stop_fade.setChecked(True)
    page.stop_fade.slider.setValue(1200)
    app.processEvents()
    check(int(cfg.get("stop_fade_ms", 0)) == 1200,
          "拖动滑块 cfg 里的时长跟着变", str(cfg.get("stop_fade_ms")))

    print("3. 引擎马上就能读到（同一份 dict，不用重启）")
    eng = sr.AudioEngine.__new__(sr.AudioEngine)
    eng.cfg = cfg
    check(eng._stop_fade_ms() == 1200.0,
          "引擎立刻按 1200ms 淡出", str(eng._stop_fade_ms()))
    page.chk_stop_fade.setChecked(False)
    app.processEvents()
    check(eng._stop_fade_ms() == 12.0,
          "关掉之后立刻退回 12ms", str(eng._stop_fade_ms()))

    print("4. 写盘也带上了")
    sr.save_config(cfg)
    reloaded = sr.load_config()
    check(reloaded.get("stop_fade_ms") == 1200,
          "config.json 里存下了时长", str(reloaded.get("stop_fade_ms")))

    win.deleteLater()
    app.processEvents()
    shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("=" * 56)
    if FAILS:
        print(f"结果：{len(FAILS)} 项失败")
        for n in FAILS:
            print("  FAIL", n)
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
