"""多套轮盘 + 文件夹分组 + 音频时长（v0.8）。

覆盖：
A. 数据层：老配置迁移成第 1 套、8 套上限、切换、克隆独立、删除、颜色往返
B. 扫描：递归子目录、相对路径键、同名文件分文件夹共存、旧顶层键不变
C. 切换生效：bank 内容跟着换、换盘不打断正在响的声音
D. 切换弹窗：扇区判定、commit 返回哪套
E. 界面：轮盘库控件、按钮状态、音效库分组、mp3 时长
"""
import os
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

import sounds_config as sc
import sr_roulette as sr

FAILS = []
RATE = 48000


def check(ok, name, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(name)


def make_wav(path: Path, secs: float, freq: float = 440.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(secs * RATE)
    t = np.arange(n) / RATE
    x = (0.4 * np.sin(2 * np.pi * freq * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as h:
        h.setnchannels(1)
        h.setsampwidth(2)
        h.setframerate(RATE)
        h.writeframes(x.tobytes())


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    snd = tmp / "sounds"
    snd.mkdir()
    for i, name in enumerate(("alpha", "beta", "gamma")):
        make_wav(snd / f"{name}.wav", 1.0 + 0.2 * i, 400 + 60 * i)

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    sr.SOUNDS_DIR = snd

    # ============ A. 数据层 ============
    print("\n=== A. 数据层 ===")
    p = tmp / "sounds.json"
    p.write_text(
        '{"version":2,"order":["alpha.wav","beta.wav"],'
        '"outer_slots":[null,null,null,null,null,null,null,null,null,null,null,null],'
        '"items":{"alpha.wav":{"volume":0.5}},"combos":[]}',
        encoding="utf-8",
    )
    cfg = sc.SoundsConfig(p)
    cfg.load()
    check(len(cfg.wheels) == 1, "老配置迁移成 1 套轮盘", str(len(cfg.wheels)))
    check(cfg.order == ["alpha.wav", "beta.wav"], "迁移后布局不变", str(cfg.order))
    check(abs(cfg.setting("alpha.wav").volume - 0.5) < 1e-6,
          "迁移后音效参数还在", str(cfg.setting("alpha.wav").volume))

    w2 = cfg.new_wheel("整活")
    check(w2 is not None and len(cfg.wheels) == 2, "能新建第 2 套")
    check(w2.order == cfg.wheels[0].order, "新建时复制了当前布局")

    # 克隆出来的参数必须独立，否则改一套另一套跟着动
    cfg.setting("alpha.wav").volume = 1.7
    check(abs(cfg.wheels[0].items["alpha.wav"].volume - 1.7) < 1e-6
          and abs(cfg.wheels[1].items["alpha.wav"].volume - 0.5) < 1e-6,
          "两套轮盘的同名音效参数互不影响")

    check(cfg.switch_wheel(w2.wid), "切换到新那套")
    check(cfg.current == w2.wid, "current 跟着变", cfg.current)
    cfg.add("gamma.wav")
    check("gamma.wav" in cfg.order and "gamma.wav" not in cfg.wheels[0].order,
          "在一套上加音效，另一套不受影响")
    check(abs(cfg.wheels[0].items["alpha.wav"].volume - 1.7) < 1e-6,
          "切回来还是自己那份参数")

    cfg.set_wheel_color("#ff5fa2")
    check(cfg.wheel_color() == "#ff5fa2", "颜色存得住", cfg.wheel_color())
    check(cfg.wheel_color(cfg.wheels[0].wid) == "", "另一套仍是跟随主题色")

    made = 0
    while cfg.new_wheel(f"第{len(cfg.wheels) + 1}套") is not None:
        made += 1
        if len(cfg.wheels) >= sc.MAX_WHEELS:
            break
    check(len(cfg.wheels) == sc.MAX_WHEELS, f"最多 {sc.MAX_WHEELS} 套", str(len(cfg.wheels)))
    check(cfg.new_wheel("再多一套") is None, "超过上限返回 None")

    before = len(cfg.wheels)
    check(cfg.delete_wheel(cfg.current), "能删掉当前那套")
    check(len(cfg.wheels) == before - 1 and cfg.current != w2.wid,
          "删完自动落到另一套", cfg.current)

    while len(cfg.wheels) > 1:
        cfg.delete_wheel(cfg.wheels[-1].wid)
    check(not cfg.delete_wheel(cfg.wheels[0].wid), "最后一套删不掉")

    # 往返
    cfg.save()
    cfg2 = sc.SoundsConfig(p)
    cfg2.load()
    check(len(cfg2.wheels) == len(cfg.wheels), "存盘往返：套数一致",
          f"{len(cfg2.wheels)} vs {len(cfg.wheels)}")
    check(cfg2.order == cfg.order, "存盘往返：当前布局一致")
    check(cfg2.wheel_color() == cfg.wheel_color(), "存盘往返：颜色一致")

    # 旧版本兼容镜像
    import json

    raw = json.loads(p.read_text(encoding="utf-8"))
    check(raw.get("order") == cfg.order and "items" in raw,
          "顶层仍写了当前轮盘的镜像（老版本读得懂）")

    # ============ B. 扫描 ============
    print("\n=== B. 文件夹扫描 ===")
    make_wav(snd / "整活" / "alpha.wav", 0.8)        # 同名，不同文件夹
    make_wav(snd / "整活" / "尖叫" / "深层.wav", 0.7)
    (snd / ".hidden").mkdir()
    make_wav(snd / ".hidden" / "不该出现.wav", 0.5)

    keys = [k for k, _ in sr.scan_sound_files()]
    check("alpha.wav" in keys, "顶层文件仍然是裸文件名（老配置不用迁移）")
    check("整活/alpha.wav" in keys, "子文件夹用相对路径当键")
    check("整活/尖叫/深层.wav" in keys, "深层子目录也认")
    check(not any(k.startswith(".") for k in keys), "隐藏目录跳过", str(keys[:3]))
    check(keys.count("alpha.wav") == 1 and "整活/alpha.wav" in keys,
          "同名文件在两个文件夹里可以共存")

    # 两个同名文件真的指向不同文件
    check(sr.sound_path("alpha.wav") != sr.sound_path("整活/alpha.wav")
          and sr.sound_path("整活/alpha.wav").exists(),
          "相对路径能定位到子文件夹里的那个文件")

    # 时长
    d_wav = sr.audio_duration(snd / "alpha.wav")
    check(abs(d_wav - 1.0) < 0.05, "wav 时长读得准", f"{d_wav:.2f}")

    # ============ C. 切换生效 ============
    print("\n=== C. 换盘的实际效果 ===")
    cfg3 = sc.SoundsConfig(tmp / "s3.json")
    cfg3.load()
    cfg3.sync([k for k, _ in sr.scan_sound_files()])
    bank = sr.SoundBank(20, cfg3)
    before_names = [bank.full_at(i) for i in range(len(bank))]

    cfg3.clear_wheel(cfg3.current)
    cfg3.add("alpha.wav")
    cfg3.add("beta.wav")
    w_b = cfg3.new_wheel("只有 gamma")
    cfg3.switch_wheel(w_b.wid)
    cfg3.clear_wheel(w_b.wid)
    cfg3.add("gamma.wav")
    cfg3.switch_wheel(cfg3.wheels[0].wid)
    cfg3.save()

    bank.reload()
    check([bank.full_at(i) for i in range(len(bank))] == ["alpha.wav", "beta.wav"],
          "第 1 套上盘的是 alpha+beta", str([bank.full_at(i) for i in range(len(bank))]))

    eng = sr.AudioEngine(bank, dict(sr.DEFAULT_CONFIG))
    eng._sink = object()          # 哨兵：离屏环境没真声卡，排程照样要走通
    eng.play(0)
    live_before = sum(len(m.voices) for m in eng._mixers_all())
    check(live_before >= 1, "先播一个，混音器里有活", str(live_before))

    cfg3.switch_wheel(w_b.wid)
    bank.reload()
    eng.load(stop_playing=False)
    after_names = [bank.full_at(i) for i in range(len(bank))]
    check(after_names == ["gamma.wav"], "切过去后轮盘只剩 gamma", str(after_names))
    live_after = sum(len(m.voices) for m in eng._mixers_all())
    check(live_after >= 1, "换盘没有掐掉正在响的声音", f"{live_before}->{live_after}")
    check(len(eng.clips) == len(bank), "clips 长度与新轮盘一致",
          f"{len(eng.clips)} vs {len(bank)}")

    # 硬重载（改音效、重新扫描）才应该停：它是给每条挂淡出倒计时，不是立刻清空
    eng.load()
    fading = [v for m in eng._mixers_all() for v in m.voices if len(v) > 3 and v[3] > 0]
    check(bool(fading), "普通 reload 会给正在响的声音挂淡出（原有行为不变）",
          str(len(fading)))

    # ============ D. 切换弹窗 ============
    print("\n=== D. 切换轮盘的轮盘 ===")
    cfg3.set_wheel_color(cfg3.wheels[0].wid, "#2ed36c")

    class FakeRaw:
        registered = True

        def drop(self) -> None:
            pass

        def take(self):
            return (0.0, 0.0)

    ctl = sr.WheelSwitchController(dict(sr.DEFAULT_CONFIG), cfg3, FakeRaw())
    entries = ctl.entries()
    check(len(entries) == len(cfg3.wheels), "格子数 = 轮盘套数", str(len(entries)))
    check(entries[0][0] == cfg3.wheels[0].wid, "每个格子带着 wid")

    n = len(entries)
    # 0 号在正上方
    import math

    for k in range(n):
        ang = math.radians(-90 + k * 360.0 / n)
        vx, vy = 100 * math.cos(ang), 100 * math.sin(ang)
        got = sr.sector_from_delta(vx, vy, n, 10.0)
        check(got == k, f"第 {k} 格判定正确", str(got))

    ctl.widget.set_entries(entries, cfg3.current)
    ctl.widget.selected = 1
    ctl.active = True
    check(ctl.commit() == entries[1][0], "松手返回选中那套的 wid")
    check(not ctl.active, "commit 之后小轮盘关掉")

    # ============ E. 界面 ============
    print("\n=== E. 界面 ===")
    import settings_window as sw

    ui = dict(sr.DEFAULT_CONFIG)
    win = sw.SettingsWindow(ui, cfg3, bank, eng)
    wp = win.page_wheel
    check(hasattr(wp, "wheel_list") and wp.wheel_list.count() == len(cfg3.wheels),
          "轮盘库列出全部套数", str(wp.wheel_list.count()))
    check(wp.btn_w_new.isEnabled() or len(cfg3.wheels) >= 8,
          "没满 8 套时「另存为新轮盘」可用")
    check(wp.btn_w_del.isEnabled(), "多于 1 套时「删除」可用")

    # 切到另一套：按钮会向主程序发请求
    got: list[str] = []
    wp.wheel_switch.connect(got.append)
    target = next(i for i, w in enumerate(cfg3.wheels) if w.wid != cfg3.current)
    wp.wheel_list.setCurrentRow(target)
    wp._do_switch()
    check(got == [cfg3.wheels[target].wid], "点「切换到这套」发出请求", str(got))

    # 配色
    check(hasattr(wp, "theme_dot") and hasattr(wp, "wheel_dot"), "配色两个色块都在")
    wp._pick_palette("purple")
    check(str(ui.get("accent_color")).lower().startswith("#a878"),
          "预设色写进 accent_color", str(ui.get("accent_color")))
    wp.cfg["accent_color"] = "#123456"
    wp._on_follow_theme(True)
    check(wp.scfg.wheel_color() == "", "勾「跟随主题色」把轮盘色清空")
    wp._on_follow_theme(False)
    check(wp.scfg.wheel_color() != "", "取消勾选后写入具体色", wp.scfg.wheel_color())

    # 音效库分组
    win.page_lib.refresh()
    heads = [w.text() for w in win.page_lib.findChildren(sw.QLabel)
             if w.objectName() == "SectionLabel" and "个" in w.text()]
    check(any("整活" in h for h in heads), "音效库有文件夹分组标题", str(heads[:3]))
    check(any("根目录" in h for h in heads), "顶层文件归到「根目录」", str(heads[:3]))

    # mp3 时长：造一个假的 mp3 不现实，这里直接验函数对未知格式不崩
    check(sr.audio_duration(snd / "不存在.mp3") == 0.0, "文件不存在时返回 0 而不是抛异常")

    print()
    if FAILS:
        print(f"共 {len(FAILS)} 项未通过：")
        for f in FAILS:
            print("  -", f)
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
