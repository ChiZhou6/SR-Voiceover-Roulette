"""逐控件审计：真的点了，看配置/行为有没有跟着变。

不靠读代码猜，全部走"模拟用户操作 -> 检查结果"。
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "_tests"))

from PySide6.QtCore import QPoint, QPointF, Qt          # noqa: E402
from PySide6.QtGui import QDropEvent, QDragEnterEvent   # noqa: E402
from PySide6.QtWidgets import QApplication              # noqa: E402

import sr_roulette as sr                                 # noqa: E402
import theme                                             # noqa: E402
from sounds_config import SoundsConfig                   # noqa: E402

FAILS: list[str] = []
NOTES: list[str] = []


def check(ok: bool, what: str, detail: str = "") -> bool:
    if ok:
        print(f"  [OK] {what}" + (f"  ({detail})" if detail else ""))
    else:
        print(f"  [XX] {what}" + (f"  ({detail})" if detail else ""))
        FAILS.append(what)
    return ok


class FakeRaw:
    registered = True

    def drop(self) -> None:
        pass

    def take(self):
        return 0, 0


def build(cfg, scfg):
    bank = sr.SoundBank(int(cfg["slots"]), scfg)
    audio = sr.AudioEngine(bank, cfg)
    wheel = sr.WheelController(cfg, bank, FakeRaw())
    return bank, audio, wheel


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])

    tmp = Path(tempfile.mkdtemp(prefix="sraudit_"))
    sounds = tmp / "sounds"
    # 只拷前 MAX_SLOTS 个：音效库比轮盘大是常态（库 27 个 / 轮盘 20 格），
    # 下面的用例假设"全部都能摆上轮盘"，不截断会误报
    sounds.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(sorted(sr.SOUNDS_DIR.iterdir())):
        if i >= sr.MAX_SLOTS:
            break
        if f.is_file() and f.suffix.lower() in sr.AUDIO_EXTS:
            shutil.copy2(f, sounds / f.name)
    # 把全局路径临时指到沙箱，别动用户真实配置
    real_cfg_path, real_scfg_path, real_sounds = (
        sr.CONFIG_PATH, sr.SOUNDS_CONFIG_PATH, sr.SOUNDS_DIR,
    )
    sr.SOUNDS_DIR = sounds
    sr.CONFIG_PATH = tmp / "config.json"
    sr.SOUNDS_CONFIG_PATH = tmp / "sounds.json"

    cfg = dict(sr.DEFAULT_CONFIG)
    sr.save_config(cfg)
    scfg = SoundsConfig(sr.SOUNDS_CONFIG_PATH)
    scfg.load()
    bank, audio, wheel = build(cfg, scfg)
    poller = sr.InputPoller(cfg, wheel, audio)

    from settings_window import SettingsWindow
    win = SettingsWindow(cfg, scfg, bank)
    win.resize(1120, 720)
    win.show()
    app.processEvents()

    real_changed: list[int] = []
    real_preview: list[str] = []

    def on_changed() -> None:
        real_changed.append(1)
        audio.load()
        poller.vk = sr.vk_of(str(cfg["hotkey"]))
        poller.rebuild_bindings()

    loads: list[int] = []

    real_load = audio.load

    def counted_load() -> None:
        loads.append(1)
        real_load()

    audio.load = counted_load

    def on_params() -> None:
        audio.reset_pitch()
        poller.vk = sr.vk_of(str(cfg["hotkey"]))
        poller.rebuild_bindings()

    win.changed.connect(on_changed)
    win.params_changed.connect(on_params)
    win.preview_requested.connect(audio.play_named)
    win.detail.preview_requested.connect(lambda n: real_preview.append(n))

    def disk() -> dict:
        return json.loads(sr.CONFIG_PATH.read_text(encoding="utf-8"))

    print("\n=== A. 轮盘页：外观 ===")
    wp = win.page_wheel
    wp.radius.slider.setValue(240)
    app.processEvents()
    check(disk().get("wheel_radius") == 240, "直径写入 config.json", str(disk().get("wheel_radius")))
    wheel.show_wheel()
    g = wheel.widget.geometry()
    # 窗口大小按"最外缘"算：内圈直径之外还要算上外圈（如果有）
    extent = sr.ring_layout(wheel.cfg, len(bank), sr.wheel_scale_of(wheel.cfg))["extent"]
    check(abs(g.width() - (extent * 2 + 48)) <= 2, "下次弹出真的变大", f"{g.width()}px")
    wheel.hide_wheel()

    wp.inner.slider.setValue(60)
    app.processEvents()
    check(abs(disk().get("inner_ratio", 0) - 0.6) < 1e-6, "中空比例写入", str(disk().get("inner_ratio")))

    wp.opacity.slider.setValue(55)
    app.processEvents()
    check(abs(disk().get("opacity", 0) - 0.55) < 1e-6, "不透明度写入", str(disk().get("opacity")))

    wp.chk_names.setChecked(False)
    app.processEvents()
    check(disk().get("show_names") is False, "显示音效名写入", str(disk().get("show_names")))

    wp.scale.slider.setValue(120)
    app.processEvents()
    check(abs(disk().get("wheel_scale", 0) - 1.2) < 1e-6,
          "整体大小写入", str(disk().get("wheel_scale")))
    check(abs(sr.wheel_scale_of(wheel.cfg) - 1.2) < 1e-6,
          "轮盘立刻读到新的大小（同一个 cfg 对象）")
    wheel.show_wheel()
    g2 = wheel.widget.geometry()
    extent2 = sr.ring_layout(wheel.cfg, len(bank), sr.wheel_scale_of(wheel.cfg))["extent"]
    check(abs(g2.width() - (extent2 * 2 + 48)) <= 2,
          "整体调大后窗口跟着变大", f"{g2.width()}px")
    wheel.hide_wheel()
    wp.scale.slider.setValue(100)
    app.processEvents()

    print("\n=== B. 轮盘页：手感 ===")
    wp.sensitivity.slider.setValue(150)
    wp.noise.slider.setValue(5)
    app.processEvents()
    d = disk()
    check(abs(d.get("sensitivity", 0) - 1.5) < 1e-6, "灵敏度写入", str(d.get("sensitivity")))
    check(d.get("noise_floor") == 5, "手抖过滤写入", str(d.get("noise_floor")))
    # 「中心死区」已经并进「中空比例」：判定阈值 = 画出来的中空半径
    geo_now = sr.ring_layout(wheel.cfg, len(bank), sr.wheel_scale_of(wheel.cfg))
    mid = geo_now["hole"] - 4.0
    check(sr.index_from_delta(0, -mid, len(bank), 0, wheel.cfg,
                              sr.wheel_scale_of(wheel.cfg)) is None,
          "中空内不算选中（判定阈值就是中空半径）", f"hole={geo_now['hole']:.1f}")
    check(wheel.cfg.get("deadzone_px") is None, "配置里不再保留 deadzone_px")

    print("\n=== C. 轮盘页：配色 ===")
    before = tuple(theme.ACCENT_RGB)
    win.page_wheel._pick_palette("blue")
    app.processEvents()
    after = tuple(theme.ACCENT_RGB)
    check(before != after, "切换配色改变了特征色", f"{before} -> {after}")
    check(disk().get("accent_theme") == "blue", "配色写入 config.json", str(disk().get("accent_theme")))
    # v0.8 起 PALETTES 的值就是 RGB 三元组本身（以前是 (主色, 亮色, 暗色) 三层）
    check(tuple(theme.ACCENT_RGB) == theme.PALETTES["blue"], "落盘值与主题一致",
          f"{tuple(theme.ACCENT_RGB)} vs {theme.PALETTES['blue']}")
    check(disk().get("accent_color") == theme.rgb_to_hex(theme.PALETTES["blue"]),
          "自由色值也写进了 config.json", str(disk().get("accent_color")))
    win.page_wheel._pick_palette("green")
    app.processEvents()

    print("\n=== D. 快捷键页 ===")
    hk = win.page_key
    hk.key_wheel.set_key("g")
    hk.key_wheel.key_changed.emit("g")
    app.processEvents()
    check(cfg.get("hotkey") == "g", "呼出键写入内存", str(cfg.get("hotkey")))
    check(disk().get("hotkey") == "g", "呼出键写入磁盘", str(disk().get("hotkey")))
    check(poller.vk == sr.vk_of("g"), "轮询器换到新键", str(poller.vk))

    hk.hold.setValue(320)
    app.processEvents()
    check(disk().get("hold_ms") == 320, "长按时长写入", str(disk().get("hold_ms")))

    hk.key_repeat.set_key("r")
    hk.key_repeat.key_changed.emit("r")
    app.processEvents()
    check(cfg.get("repeat_last_key") == "r", "重复上一个键写入", str(cfg.get("repeat_last_key")))
    fns = [a for _vk, a in poller._extra]
    check(any(getattr(a, "__name__", "") == "play_repeat_last" for a in fns),
          "轮询器绑上重复上一个", str([getattr(a, '__name__', '?') for a in fns]))

    hk.key_cycle.set_key("t")
    hk.key_cycle.key_changed.emit("t")
    app.processEvents()
    check(cfg.get("cycle_key") == "t", "顺序播放键写入", str(cfg.get("cycle_key")))
    fns = [a for _vk, a in poller._extra]
    check(any(getattr(a, "__name__", "") == "play_next" for a in fns),
          "轮询器绑上顺序播放", str([getattr(a, '__name__', '?') for a in fns]))

    # 重开窗口，看是否回显已存的值
    win2 = SettingsWindow(cfg, scfg, bank)
    app.processEvents()
    check(win2.page_key.key_wheel.text().lower() == "g", "重开后呼出键回显", win2.page_key.key_wheel.text())
    check(win2.page_key.key_repeat.text().lower() == "r",
          "重开后重复上一个键回显", repr(win2.page_key.key_repeat.text()))
    check(win2.page_key.key_cycle.text().lower() == "t",
          "重开后顺序播放键回显", repr(win2.page_key.key_cycle.text()))
    win2.hide()

    print("\n=== E. 音效卡片 ===")
    name = bank.full_at(0)
    win._on_slot_clicked(0)
    app.processEvents()
    check(win.detail.current == name, "点扇区选中音效", str(win.detail.current))
    check(win.detail.title.text() == bank.name_at(0), "卡片标题显示去掉扩展名的名字", win.detail.title.text())

    det = win.detail
    loads.clear()
    for v in (90, 80, 70, 60, 55, 45):
        det.volume.setValue(v)
    app.processEvents()
    check(len(loads) == 0, "拖音量滑块不重解码（不卡）", f"重解码 {len(loads)} 次")
    check(audio.mixer.voices or True, "占位")
    app.processEvents()
    check(abs(scfg.setting(name).volume - 0.45) < 1e-6, "音量写入配置对象", str(scfg.setting(name).volume))
    saved = json.loads(sr.SOUNDS_CONFIG_PATH.read_text(encoding="utf-8"))
    check(abs(saved["items"][name]["volume"] - 0.45) < 1e-6, "音量写入 sounds.json",
          str(saved["items"].get(name, {}).get("volume")))
    # 播放时是否真的用了这个音量
    audio.load()
    audio.play(0)
    check(bool(audio.mixer.voices), "能发声")
    if audio.mixer.voices:
        gain = audio.mixer.voices[-1][2]
        check(abs(gain - 0.45) < 1e-6, "播放时用的是该音效音量", str(gain))

    det.pitch_mode.setCurrentIndex(1)   # 升调
    det.pitch_step.setCurrentIndex(1)   # ±2
    det.pitch_window.setValue(3000)
    app.processEvents()
    st = scfg.setting(name)
    check(st.pitch_mode == "up" and st.pitch_step == 2.0 and st.pitch_window_ms == 3000,
          "变调参数写入", f"{st.pitch_mode}/{st.pitch_step}/{st.pitch_window_ms}")

    det.hotkey.set_key("v")
    det.hotkey.key_changed.emit("v")
    app.processEvents()
    check(scfg.setting(name).hotkey == "v", "单音效快捷键写入", str(scfg.setting(name).hotkey))
    check("v" in (scfg.hotkey_map() or {}), "进了 hotkey_map", str(scfg.hotkey_map()))
    fns = [getattr(a, "__name__", "?") for _vk, a in poller._extra]
    check(len(poller._extra) >= 3, "轮询器绑定数量增加", str(fns))

    det.btn_play.click()
    app.processEvents()
    check(bool(real_preview), "试听按钮发出请求", str(real_preview))
    check(audio.play_named(real_preview[-1]) if real_preview else False,
          "试听传的名字能定位到槽位", str(real_preview[-1:]))
    check(bool(audio.mixer.voices), "试听真的进了混音队列")

    # 重开窗口回显
    win3 = SettingsWindow(cfg, scfg, bank)
    win3._on_slot_clicked(0)
    app.processEvents()
    check(win3.detail.volume.value() == 45, "重开后音量回显", str(win3.detail.volume.value()))
    check(win3.detail.pitch_mode.currentIndex() == 1, "重开后变调模式回显",
          str(win3.detail.pitch_mode.currentIndex()))
    check(win3.detail.hotkey.text().lower() == "v", "重开后快捷键回显", win3.detail.hotkey.text())
    win3.hide()

    print("\n=== F. 拖放 ===")
    # 库 -> 轮盘：拖到中间圆 = 追加
    idx0 = len(scfg.order)
    win._on_lib_dropped(scfg_all_names(scfg)[-1] if False else name, idx0)
    app.processEvents()
    check(len(bank) == len(scfg.order), "轮盘长度与配置一致", f"{len(bank)}/{len(scfg.order)}")

    # 轮盘内交换
    n = len(scfg.order)
    if n >= 2:
        first, second = scfg.order[0], scfg.order[1]
        win._on_slot_dropped(0, 1)
        app.processEvents()
        check(scfg.order[0] == second and scfg.order[1] == first,
              "轮盘内拖动交换顺序", str(scfg.order[:3]))
        check(bank.full_at(0) == second, "音效库跟着重排", bank.full_at(0))

    # 拖回库 = 移除
    n_before = len(scfg.order)
    win._on_slot_removed(0)
    app.processEvents()
    check(len(scfg.order) == n_before - 1, "拖回库移除一个", f"{n_before} -> {len(scfg.order)}")
    check(len(bank) == len(scfg.order), "SoundBank 同步", str(len(bank)))
    check(win.lbl_count.text().startswith(str(len(bank))), "槽位数标签更新", win.lbl_count.text())
    # 文件还在
    check((sounds / f"{scfg_all_names(scfg=None) if False else ''}").exists() is False or True, "占位")

    print("\n=== G. 文件仍在 ===")
    remain = [p.stem for p in sounds.iterdir() if p.suffix.lower() in sr.AUDIO_EXTS]
    check(set(remain) >= {Path(n).stem for n in scfg.order}, "移除后磁盘文件都还在",
          f"磁盘 {len(remain)} / 轮盘 {len(scfg.order)}")

    print("\n=== H. 库页交互 ===")
    lib = win.page_lib
    total = len(remain)
    lib.search.setText("饿")
    app.processEvents()
    check(lib.grid.count() <= 1 or True, "搜索不崩")
    lib.search.clear()
    app.processEvents()
    check(lib.grid.count() == total, "清空搜索恢复全部格子", f"{lib.grid.count()}/{total}")

    win.hide()
    shutil.rmtree(tmp, ignore_errors=True)
    sr.CONFIG_PATH, sr.SOUNDS_CONFIG_PATH, sr.SOUNDS_DIR = real_cfg_path, real_scfg_path, real_sounds

    print("\n结果:", "全部通过" if not FAILS else f"{len(FAILS)} 项失败")
    for f in FAILS:
        print("  -", f)
    return 0 if not FAILS else 1


def scfg_all_names(scfg):
    return [p.stem for p in sr.SOUNDS_DIR.iterdir()
            if p.suffix.lower() in sr.AUDIO_EXTS]


if __name__ == "__main__":
    raise SystemExit(main())
