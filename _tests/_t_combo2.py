"""组合音效 v0.7.2 新功能测试。

覆盖这一版加的东西：
A. 数据层：裁剪 / 负延迟 / 整体参数 / 随机抖动 的往返保存与收回
B. 排程：负延迟提前起步，但绝不早于组合触发那一刻
C. 裁剪：起点 + 长度真的改变了波形长度和内容
D. 整体速度/变调：乘在每项自己的参数之上
E. 随机：设了随机才会变，没设永远一样
F. 冷却：冷却期内第二次触发被吞掉
G. 发声上限：同组声音条数压得住
H. 从某一行开始试听：只排这一行往后
I. 导出 WAV：文件能读回、时长对得上
J. 预渲染：烘过的组合触发不再重新算
K. 编辑器：新控件、撤销/重做、递进复制、时间条渲染
L. 输入：轮盘弹着时点左键/右键立刻取消，且松手前不再弹
"""
import os
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time

import numpy as np

import sounds_config as sc
import sr_roulette as sr
from PySide6.QtWidgets import QApplication

# 解码走 QtAudioDecoder，必须有 QApplication 陪着跑事件循环，
# 否则每次解码都要等到 6 秒超时才返回（表现为"测试像卡住了"）
app = QApplication.instance() or QApplication([])

FAILS = []


def check(ok, name, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(name)


RATE = 48000


def write_wav(path: Path, seconds: float, freq: float = 440.0):
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    x = (0.4 * np.sin(2 * np.pi * freq * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(x.tobytes())


tmp = Path(tempfile.mkdtemp())
snd = tmp / "sounds"
snd.mkdir()
write_wav(snd / "A.wav", 1.0)
write_wav(snd / "B.wav", 2.0)
sr.SOUNDS_DIR = snd

p = tmp / "sounds.json"
cfg = sc.SoundsConfig(p)
cfg.load()
names = [f.name for f in snd.iterdir()]
cfg.sync(names)

# ============ A. 数据层 ============
print("=== A. 数据层 ===")
cdef = cfg.new_combo("新版组合")
cdef.items = [
    sc.ComboItem(sound="A.wav", trig=sc.TRIG_COMBO, delay_ms=0,
                 clip_start_ms=200, clip_len_ms=300, rand_semi=1.5, rand_rate=0.1),
    sc.ComboItem(sound="A.wav", trig=sc.TRIG_PREV_END, delay_ms=-250),
]
cdef.rate = 1.25
cdef.semitones = -2.0
cdef.rand_rate = 0.05
cdef.rand_semi = 0.5
cdef.cooldown_ms = 400
cdef.max_voices = 2
cfg.order.append(cfg.combo_key(cdef.cid))
cfg.save()

cfg2 = sc.SoundsConfig(p)
cfg2.load()
c2 = cfg2.combo_of(cfg2.order[-1])
it0, it1 = c2.items
check(it0.clip_start_ms == 200 and it0.clip_len_ms == 300,
      "裁剪参数往返一致", f"{it0.clip_start_ms}/{it0.clip_len_ms}")
check(it0.rand_semi == 1.5 and abs(it0.rand_rate - 0.1) < 1e-6,
      "逐项随机往返一致", f"{it0.rand_semi}/{it0.rand_rate}")
check(it1.delay_ms == -250, "负延迟往返一致（不再被夹成 0）", str(it1.delay_ms))
check(abs(c2.rate - 1.25) < 1e-6 and c2.semitones == -2.0,
      "整体速度/变调往返一致", f"{c2.rate}/{c2.semitones}")
check(c2.cooldown_ms == 400 and c2.max_voices == 2,
      "冷却/发声上限往返一致", f"{c2.cooldown_ms}/{c2.max_voices}")

bad = sc.ComboItem(delay_ms=-99999, clip_start_ms=-5, clip_len_ms=9999999,
                   rand_semi=99, rand_rate=9).clamped()
check(bad.delay_ms == sc.DELAY_MIN_MS and bad.clip_start_ms == 0
      and bad.clip_len_ms == 600000 and bad.rand_semi == 12.0
      and bad.rand_rate == 0.5, "越界的裁剪/随机值全部收回", str(bad))
badc = sc.ComboDef(rate=9, semitones=99, cooldown_ms=-1, max_voices=99).clamped()
check(badc.rate == 2.0 and badc.semitones == 24.0
      and badc.cooldown_ms == 0 and badc.max_voices == 16,
      "越界的整体参数全部收回", f"{badc.rate}/{badc.semitones}/{badc.max_voices}")

# ============ B. 负延迟排程 ============
print("\n=== B. 负延迟排程 ===")
items = [
    sc.ComboItem(sound="A.wav", trig=sc.TRIG_COMBO),
    sc.ComboItem(sound="A.wav", trig=sc.TRIG_PREV_END, delay_ms=-400),
    sc.ComboItem(sound="A.wav", trig=sc.TRIG_COMBO, delay_ms=-3000),
]
plan = sr.combo_plan(items, [0, 1, 2], {0: 1.0, 1: 1.0, 2: 1.0}, RATE)
starts = [round(d / RATE, 3) for _, d in plan]
check(starts == [0.0, 0.6, 0.0], "负延迟把第二项提前到 0.6 秒", str(starts))
check(all(d >= 0 for _, d in plan), "再负也不会早于组合触发那一刻", str(starts))

# ============ C. 裁剪 ============
print("\n=== C. 片段裁剪 ===")
fmt = sr._target_format()
full = sr.lib_clip("A.wav", fmt, 6.0)
cut = sr.combo_item_clip(sc.ComboItem(sound="A.wav", clip_start_ms=200, clip_len_ms=300), fmt)
check(cut is not None and abs(len(cut) / RATE - 0.3) < 0.02,
      "起点 200ms + 长度 300ms 裁出约 0.3 秒", f"{len(cut) / RATE:.3f}")
check(float(np.abs(cut[0]).max()) < 0.05 and float(np.abs(cut[-1]).max()) < 0.05,
      "裁剪两端补了淡入淡出（不会啪一声）",
      f"{float(np.abs(cut[0]).max()):.3f}/{float(np.abs(cut[-1]).max()):.3f}")
no_cut = sr.combo_item_clip(sc.ComboItem(sound="A.wav"), fmt)
check(len(no_cut) == len(full), "不填裁剪时波形原样不动", f"{len(no_cut)}")
over = sr.combo_item_clip(sc.ComboItem(sound="A.wav", clip_start_ms=5000), fmt)
check(over is None, "起点越过结尾时这项没内容可放")
check(abs(sr.item_src_duration(sc.ComboItem(sound="A.wav", clip_start_ms=200,
                                            clip_len_ms=300)) - 0.3) < 0.02,
      "item_src_duration 也算剪过的长度")

# ============ D. 整体参数叠加 ============
print("\n=== D. 整体速度/变调 ===")
it = sc.ComboItem(sound="A.wav")
base_clip = sr.combo_item_clip(it, fmt, rate_abs=1.0, semi_abs=0.0)
fast_clip = sr.combo_item_clip(it, fmt, rate_abs=2.0, semi_abs=0.0)
slow_clip = sr.combo_item_clip(it, fmt, rate_abs=0.5, semi_abs=0.0)
check(abs(len(fast_clip) / len(base_clip) - 0.5) < 0.05, "速度 200% 时长减半",
      f"{len(fast_clip) / len(base_clip):.3f}")
check(abs(len(slow_clip) / len(base_clip) - 2.0) < 0.1, "速度 50% 时长翻倍",
      f"{len(slow_clip) / len(base_clip):.3f}")
# 整体与逐项叠乘：逐项 1.5 × 整体 2.0 = 3.0
both = sr.combo_item_clip(sc.ComboItem(sound="A.wav", rate=1.5), fmt, rate_abs=3.0)
check(abs(len(both) / len(base_clip) - 1 / 3.0) < 0.05,
      "整体速度与逐项速度相乘（1.5×2=3）", f"{len(both) / len(base_clip):.3f}")

# ============ E. 引擎：随机 / 冷却 / 限声 / 起播行 ============
print("\n=== E. 引擎新参数 ===")
bank = sr.SoundBank(8, scfg=cfg2)
engine = sr.AudioEngine(bank, dict(sr.DEFAULT_CONFIG))
mix = engine._mixers_all()[0]
c2.cooldown_ms = 0
c2.max_voices = 0
c2.rand_rate = 0.0
c2.rand_semi = 0.0
c2.rate = 1.0
c2.semitones = 0.0

# 冷却
c2.cooldown_ms = 600
mix.voices.clear()
first = engine.play_combo(c2)
second = engine.play_combo(c2)
check(first is True and second is False, "冷却期内第二次触发被吞掉",
      f"{first}/{second}")
engine.stop_all()
c2.cooldown_ms = 0

# 固定参数下两次触发完全一样
c2.items[0].semitones = 0.0
c2.items[0].rand_semi = 0.0
c2.items[0].rand_rate = 0.0
lens = []
for _ in range(3):
    mix.voices.clear()
    engine.play_combo(c2)
    lens.append(round(float(len(mix.voices[0][0])) / RATE, 4))
    engine.stop_all()
check(len(set(lens)) == 1, "没设随机时每次波形完全一致", str(lens))

# 设了随机就会变
c2.items[0].rand_semi = 3.0
engine._combo_cache.clear()
lens = []
for _ in range(12):
    mix.voices.clear()
    engine.play_combo(c2)
    lens.append(round(float(len(mix.voices[0][0])) / RATE, 3))
    engine.stop_all()
check(len(set(lens)) > 1, "设了随机变调后每次时长不同（音高在抖）", f"{len(set(lens))} 种")
c2.items[0].rand_semi = 0.0

# 发声上限
m = sr.Mixer(fmt)
ones = np.ones((RATE // 10, 2), dtype=np.float32)
for _ in range(5):
    m.trigger(ones, 1.0, group="g1", max_voices=2)
live = [v for v in m.voices if v[3] <= 0]
check(len(live) <= 2, "同一分组最多 2 条声音同时响", str(len(live)))
for _ in range(3):
    m.trigger(ones, 1.0, group="g2", max_voices=0)
check(len([v for v in m.voices if v[5] == "g2"]) == 3, "不限流的分组照常叠加")

# 从某一行开始
c2.max_voices = 0
engine._combo_cache.clear()
mix.voices.clear()
ok = engine.play_combo(c2, from_row=1)
check(ok and len(mix.voices) >= 1, "从第二行开始试听能出声", str(len(mix.voices)))
check(min(v[4] for v in mix.voices) == 0, "从某行开始试听时那一行立刻响（不等延迟）")
engine.stop_all()

# ============ F. 导出 WAV ============
print("\n=== F. 导出 WAV ===")
c2.cooldown_ms = 0
baked = engine.bake_combo(c2)
check(baked is not None, "能烘焙成一条波形")
data, rate = baked
wav_path = tmp / "导出.wav"
ok, msg = engine.export_combo_wav(c2, wav_path)
check(ok and wav_path.exists(), "导出文件写出来了", msg)
with wave.open(str(wav_path), "rb") as w:
    n = w.getnframes()
    ch = w.getnchannels()
    sw = w.getsampwidth()
    same_rate = w.getframerate() == rate
check(same_rate and sw == 2 and ch == data.shape[1], "格式正确（16bit / 原采样率 / 双声道）",
      f"{ch}ch/{sw * 8}bit/{rate}")
check(abs(n - len(data)) <= 1, "帧数与烘焙结果一致", f"{n} vs {len(data)}")
order_all = list(range(len(c2.items)))
durs = {}
for i in order_all:
    clip = engine._combo_clip(c2.cid, i, c2.items[i])
    durs[i] = 0.0 if clip is None else len(clip) / RATE
plan_all = sr.combo_plan(c2.items, order_all, durs, RATE)
expect = max(d / RATE + durs.get(i, 0.0) for i, d in plan_all)
check(abs(n / RATE - expect) < 0.05, "导出时长 = 排程算出来的总长",
      f"{n / RATE:.2f} vs {expect:.2f} 秒")

# ============ G. 预渲染 ============
print("\n=== G. 预渲染缓存 ===")
engine._combo_cache.clear()
t0 = time.monotonic()
n = engine.warm_combo(c2)
cold = (time.monotonic() - t0) * 1000
check(n == len(c2.items) and len(engine._combo_cache) >= n,
      "烘焙后每项都进了缓存", f"{n} 项 / 缓存 {len(engine._combo_cache)}")
t0 = time.monotonic()
for _ in range(5):
    engine.play_combo(c2)
    engine.stop_all()
warm = (time.monotonic() - t0) / 5 * 1000
check(warm < 15, "烘过的组合触发几乎不耗时", f"冷 {cold:.0f}ms / 热 {warm:.1f}ms")

# ============ H. 界面 ============
print("\n=== H. 编辑器 ===")
from PySide6.QtWidgets import QSpinBox

import settings_window as sw

ui_cfg = dict(sr.DEFAULT_CONFIG)
win = sw.SettingsWindow(ui_cfg, cfg2, bank, engine)
win.show()
app.processEvents()

dlg = sw.ComboEditorDialog(cfg2, c2, engine, win)
dlg.show()
app.processEvents()
check(dlg.table.rowCount() == len(c2.items), "表格行数 = 成员数", str(dlg.table.rowCount()))
check(dlg.spn_start is not None and dlg.spn_len is not None
      and dlg.spn_rsemi is not None and dlg.spn_rrate is not None,
      "选中项细节控件都在（起点/长度/随机变调/随机变速）")
check(dlg.spn_orate is not None and dlg.spn_osemi is not None
      and dlg.spn_orrate is not None and dlg.spn_osemi_r is not None,
      "整体参数控件都在")
check(dlg.spn_cool is not None and dlg.spn_voices is not None,
      "冷却 / 发声上限控件都在")
check(dlg.key_combo is not None, "专属热键框在")
delay_box = dlg.table.cellWidget(1, 3)
check(delay_box.minimum() == sc.DELAY_MIN_MS, "延迟框允许填负数",
      str(delay_box.minimum()))
sound_box = dlg.table.cellWidget(0, 1)
check(sound_box is not None and sound_box.count() >= 2, "音效列是下拉框（能看见缺失/能替换）")

# 时间条：给几段重叠的跨度，确认画得出来
dlg.timeline.set_spans([(0, 0.0, 1.0, True), (1, 0.5, 1.2, True), (2, 2.0, 0.6, False)],
                       3.2)
app.processEvents()
img = dlg.timeline.grab()
img.save(str(tmp / "timeline.png"))
check(img.width() > 100 and img.height() > 40, "时间条渲染成功",
      f"{img.width()}x{img.height()}")

# 撤销 / 重做
dlg.table.selectRow(0)
app.processEvents()
before = c2.items[0].delay_ms
dlg.table.cellWidget(0, 3).setValue(before + 500)
app.processEvents()
check(c2.items[0].delay_ms == before + 500, "改延迟生效", str(c2.items[0].delay_ms))
dlg._undo()
check(c2.items[0].delay_ms == before, "撤销把延迟退回去了", str(c2.items[0].delay_ms))
dlg._redo()
check(c2.items[0].delay_ms == before + 500, "重做又变回 500 之后的值",
      str(c2.items[0].delay_ms))
dlg._undo()

# 递进复制
class _Stub:
    def __init__(self, *_a, **_k):
        self.spn_copies = QSpinBox()
        self.spn_copies.setRange(1, 12)

    def exec(self):
        return 1          # QDialog.Accepted

    def values(self):
        return (2, 2.0, 10, 200)

real_dlg = sw._ProgressDialog
sw._ProgressDialog = _Stub
try:
    dlg.table.selectRow(0)
    app.processEvents()
    n_before = len(c2.items)
    base_semi = c2.items[0].semitones
    base_rate = c2.items[0].rate
    dlg._progress_copy()
    app.processEvents()
    check(len(c2.items) == n_before + 2, "递进复制插入了 2 份", str(len(c2.items)))
    check(abs(c2.items[1].semitones - (base_semi + 2.0)) < 1e-6
          and abs(c2.items[2].semitones - (base_semi + 4.0)) < 1e-6,
          "每份依次 +2 半音", f"{c2.items[1].semitones}/{c2.items[2].semitones}")
    check(abs(c2.items[1].rate - (base_rate + 0.10)) < 1e-6,
          "每份依次 +10% 速度", f"{c2.items[1].rate}")
    check(c2.items[1].delay_ms == c2.items[0].delay_ms + 200
          and c2.items[2].delay_ms == c2.items[0].delay_ms + 400,
          "每份依次 +200ms 延迟",
          f"{c2.items[1].delay_ms}/{c2.items[2].delay_ms}")
    dlg._undo()
    check(len(c2.items) == n_before, "撤消能把这两份一起拿掉", str(len(c2.items)))
finally:
    sw._ProgressDialog = real_dlg

# 缺失成员可见
c2.items[0].sound = "不存在.wav"
dlg.reload_table()
app.processEvents()
box0 = dlg.table.cellWidget(0, 1)
texts = [box0.itemText(i) for i in range(box0.count())]
check(any("缺失" in t for t in texts), "缺文件的那一列顶部标了 ⚠ 缺失", str(texts[:2]))
check(dlg.table.item(0, 7).text() == "缺失", "时长列直接写缺失二字",
      dlg.table.item(0, 7).text())
check("文件缺失" in dlg.lbl_total.text(), "底部汇总也提示缺了几项", dlg.lbl_total.text())
c2.items[0].sound = "A.wav"
dlg.reload_table()
dlg.close()

# ============ I. 鼠标左右键取消轮盘 ============
print("\n=== I. 鼠标取消呼出 ===")
wcfg = dict(sr.DEFAULT_CONFIG)
wcfg["hotkey"] = "y"
wcfg["hold_ms"] = 180
wheel = sr.WheelController(wcfg, bank, sr.RawMouse(), engine)
poller = sr.InputPoller(wcfg, wheel, engine)
states = {"y": False, "mouse_left": False, "mouse_right": False}
poller._down = lambda name: bool(states.get(name, False))

states["y"] = True
poller.tick()                     # 按下
poller._press_at -= 5.0           # 假装已经按了很久
poller.tick()                     # 应该弹出来
check(wheel.active, "长按后轮盘弹出来了")

states["mouse_left"] = True
poller.tick()                     # 点左键 → 立刻取消
check(not wheel.active, "点左键立刻取消呼出")

states["mouse_left"] = False
poller.tick()
poller._press_at -= 5.0
poller.tick()
check(not wheel.active, "还按着热键也不会重新弹出来")

states["y"] = False
played = []
poller.audio = type("X", (), {"play": lambda self, i: played.append(i),
                              "playing": False})()
poller.tick()
check(not played, "松手后没有误播任何音效", str(played))

# 右键同样有效
poller.audio = engine
states["y"] = True
poller.tick()
poller._press_at -= 5.0
poller.tick()
ok_show = wheel.active
states["mouse_right"] = True
poller.tick()
check(ok_show and not wheel.active, "点右键同样立刻取消")
states["mouse_right"] = False
states["y"] = False
poller.tick()


# ============ J. 专属热键（不必上盘）============
print("\n=== J. 专属热键 ===")
off = cfg2.new_combo("没上盘也能按")
off.items = [sc.ComboItem(sound="A.wav", trig=sc.TRIG_COMBO)]
cfg2.combo_setting(off.cid).hotkey = "f9"
hk = cfg2.hotkey_map()
check("f9" in hk and hk["f9"] == cfg2.combo_key(off.cid),
      "未上盘的组合也会登记到快捷键表", str(hk.get("f9")))
engine._combo_cache.clear()
mix.voices.clear()
check(engine.play_named(cfg2.combo_key(off.cid)) is True, "热键能直接触发未上盘的组合")
engine.stop_all()
cfg2.combo_setting(off.cid).hotkey = ""

# 专属热键撞了"呼出轮盘"的键要标红提示，不能静默失效
dlg2 = sw.ComboEditorDialog(cfg2, c2, engine, win, {"hotkey": "y"})
dlg2.key_combo.clear_key()
dlg2.key_combo.edit._apply("y")
app.processEvents()
check("呼出轮盘" in dlg2.key_combo.toolTip(),
      "专属热键撞了呼出键会提示", dlg2.key_combo.toolTip())
dlg2.key_combo.edit._apply("")
cfg2.combo_setting(c2.cid).hotkey = ""
dlg2.close()

print()
if FAILS:
    print("失败项：")
    for f in FAILS:
        print("  -", f)
    raise SystemExit(1)
print("全部通过")
