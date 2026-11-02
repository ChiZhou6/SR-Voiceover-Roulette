"""组合音效 v0.7.1 测试。

覆盖用户给的两个真实场景 + 稳定性关键点：
A. 数据层：往返保存、越界收回、第一项触发点被强制成"组合开始时"
B. 排程（纯函数）：场景 1 的 0/0.2/0.4/1.65、场景 2 的随机抽 3 个 + 1s 间隔
C. 混音器：延迟语音、stop_all 摘掉未响的、不同长度波形共存不崩（v0.7 闪退元凶）
D. 引擎：真实解码 + play_combo 的延迟和项数
E. UI：配置窗口与编辑器能建起来、表格行数对、渲染不炸（截图留档防错位）
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
write_wav(snd / "C.wav", 1.0, 550.0)
write_wav(snd / "D.wav", 1.0, 660.0)

# ============ A. 数据层 ============
print("=== A. 数据层 ===")
p = tmp / "sounds.json"
cfg = sc.SoundsConfig(p)
cfg.load()
cfg.sync([f.name for f in snd.iterdir()])
cdef = cfg.new_combo("测试组合1")
cdef.items = [
    sc.ComboItem(sound="A.wav", trig=sc.TRIG_COMBO, delay_ms=0),
    sc.ComboItem(sound="A.wav", trig=sc.TRIG_PREV_START, delay_ms=200, semitones=2, rate=1.25),
    sc.ComboItem(sound="A.wav", trig=sc.TRIG_PREV_START, delay_ms=200, semitones=-3, rate=0.8),
    sc.ComboItem(sound="B.wav", trig=sc.TRIG_PREV_END, delay_ms=0),
]
cfg.order.append(cfg.combo_key(cdef.cid))
cfg.outer_slots[0] = cfg.combo_key(cdef.cid)
cfg.save()

cfg2 = sc.SoundsConfig(p)
cfg2.load()
c2 = cfg2.combo_of(cfg2.order[-1])
check(c2 is not None, "组合能从轮盘键找回")
check(len(c2.items) == 4, "成员数往返一致", str(len(c2.items)))
check(c2.items[1].semitones == 2.0 and c2.items[1].rate == 1.25,
      "变调/变速往返一致", f"{c2.items[1].semitones}/{c2.items[1].rate}")
check(c2.items[3].trig == sc.TRIG_PREV_END, "触发条件往返一致", c2.items[3].trig)
check(cfg2.sync([f.name for f in snd.iterdir()])[-1].startswith(sc.COMBO_PREFIX),
      "sync 不会把组合从轮盘上清掉")

bad = sc.ComboItem(trig="whatever", delay_ms=999999, semitones=99, rate=9).clamped()
check(bad.trig == sc.TRIG_PREV_END and bad.delay_ms == 10000
      and bad.semitones == 24.0 and bad.rate == 2.0, "越界值全部收回", str(bad))
first = sc.ComboDef(cid="x", items=[sc.ComboItem(trig=sc.TRIG_PREV_START)]).clamped()
check(first.items[0].trig == sc.TRIG_COMBO, "第一项被强制成组合开始时")

# ============ B. 排程 ============
print("\n=== B. 排程（用户场景）===")
items = c2.items
durs = {0: 1.0, 1: 1.0 / 1.25, 2: 1.0 / 0.8, 3: 2.0}
plan = sr.combo_plan(items, [0, 1, 2, 3], durs, RATE)
starts = [round(d / RATE, 3) for _, d in plan]
check(starts == [0.0, 0.2, 0.4, 1.65], "场景1: 0 / 0.2 / 0.4 / 1.65 秒", str(starts))

items2 = [
    sc.ComboItem(sound=f"{n}.wav", trig=sc.TRIG_COMBO if k == 0 else sc.TRIG_PREV_START,
                 delay_ms=0 if k == 0 else 1000)
    for k, n in enumerate(("A", "B", "C", "D"))
]
rand_def = sc.ComboDef(cid="r", mode=sc.CM_RAND, count=3, items=items2)
ok_cnt = ok_ord = ok_plan = True
for _ in range(40):
    order = rand_def.play_order()
    if len(order) != 3 or len(set(order)) != 3:
        ok_cnt = False
    if order != sorted(order):
        ok_ord = False
    s2 = [round(d / RATE, 2) for _, d in
          sr.combo_plan(items2, order, {i: 1.0 for i in order}, RATE)]
    if s2 != [0.0, 1.0, 2.0]:
        ok_plan = False
check(ok_cnt, "场景2: 每次恰好抽 3 个且不重复")
check(ok_ord, "场景2: 默认保持组合内原顺序")
check(ok_plan, "场景2: 0 / 1 / 2 秒（第一声立刻响，不等 1 秒）")

shuffled = sc.ComboDef(cid="s", mode=sc.CM_RAND, count=4, shuffle=True, items=items2)
seen = {tuple(shuffled.play_order()) for _ in range(60)}
check(len(seen) > 1, "勾了打乱后顺序确实会变", f"{len(seen)} 种")

# 缺失成员不打断
plan_miss = sr.combo_plan(items, [0, 1, 2, 3], {0: 1.0, 1: 0.0, 2: 0.0, 3: 2.0}, RATE)
check([round(d / RATE, 2) for _, d in plan_miss] == [0.0, 0.2, 0.4, 0.4],
      "中间两项缺失时后续仍能排出来", str([round(d / RATE, 2) for _, d in plan_miss]))

# ============ C. 混音器 ============
print("\n=== C. 混音器 ===")
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QAudioFormat

app = QApplication.instance() or QApplication(sys.argv)
fmt = QAudioFormat()
fmt.setSampleRate(RATE)
fmt.setChannelCount(2)
fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)


def ones(seconds: float) -> np.ndarray:
    return np.ones((int(RATE * seconds), 2), dtype=np.float32) * 0.5


m = sr.Mixer(fmt)
m.trigger(ones(0.1), 1.0)
m.trigger(ones(0.3), 1.0)      # 长度不同的两路：v0.7 就是在这里 list.remove 报错闪退
peaks = []
for _ in range(8):
    a = np.frombuffer(m.readData(RATE // 10 * 2 * 4), dtype=np.float32).reshape(-1, 2)
    peaks.append(round(float(np.abs(a).max()), 2))
check(True, "两个不同长度的波形共存不抛异常", str(peaks))
check(m.voices == [], "播完之后列表清空（没有幽灵语音）", str(len(m.voices)))

m2 = sr.Mixer(fmt)
m2.trigger(ones(0.1), 1.0, delay=RATE)     # 1 秒后才响
silent = 0
for _ in range(6):
    a = np.frombuffer(m2.readData(RATE // 10 * 2 * 4), dtype=np.float32).reshape(-1, 2)
    if float(np.abs(a).max()) == 0.0:
        silent += 1
check(silent == 6, "延迟 1 秒：前 0.6 秒完全静音", str(silent))
a = None
for _ in range(5):
    a = np.frombuffer(m2.readData(RATE // 10 * 2 * 4), dtype=np.float32).reshape(-1, 2)
check(float(np.abs(a).max()) > 0.1, "延迟到点后正常出声", f"{float(np.abs(a).max()):.2f}")

m3 = sr.Mixer(fmt)
m3.trigger(ones(0.1), 1.0, delay=RATE * 5)
m3.stop_all()
check(m3.voices == [], "stop_all 会摘掉还没响的延迟语音", str(len(m3.voices)))

# ============ D. 引擎 ============
print("\n=== D. 引擎播放 ===")
sr.SOUNDS_DIR = snd
bank = sr.SoundBank(8, scfg=cfg2)
engine = sr.AudioEngine(bank, dict(sr.DEFAULT_CONFIG))
mix = engine._mixers_all()[0]

combo_idx = bank.index_of_name(cfg2.combo_key(c2.cid))
check(combo_idx >= 0, "组合占了轮盘一个槽位", str(combo_idx))
mix.voices.clear()
check(engine.play(combo_idx) is True, "轮盘触发组合返回成功")
# 期望的延迟要用"处理后的真实时长"算：降 3 半音会把 1.25s 拉成约 1.49s，
# 所以第 4 项接在"上一项结束"后面时是 0.4 + 1.49 ≈ 1.89s（不是 1.65）
real_durs = {}
for i, it in enumerate(c2.items):
    clip = engine._combo_clip(c2.cid, i, it)
    real_durs[i] = len(clip) / RATE if clip is not None else 0.0
exp_plan = sr.combo_plan(c2.items, [0, 1, 2, 3], real_durs, RATE)
expect = [d / RATE for _, d in exp_plan]
delays = sorted(v[4] / RATE for v in mix.voices)
check(all(abs(a - b) < 0.01 for a, b in zip(delays, expect)),
      "混音器里四项的延迟符合排程",
      f"{[round(d, 2) for d in delays]} vs 期望 {[round(d, 2) for d in expect]}")
engine.stop_all()
check(all(v[4] == 0 for v in mix.voices), "停止后没有残留的延迟语音",
      str([v[4] for v in mix.voices]))
mix.voices.clear()

# 组合音量独立（不影响成员）
cfg2.setting(cfg2.combo_key(c2.cid)).volume = 0.5
mix.voices.clear()
engine.play(combo_idx)
gains = {round(v[2], 2) for v in mix.voices}
check(gains == {0.5}, "组合整体音量作用于每一项", str(gains))
engine.stop_all()

# 成员缺失：只跳过那一项
c2.items[1].sound = "不存在.wav"
engine._combo_cache.clear()
mix.voices.clear()
engine.play(combo_idx)
check(len(mix.voices) == 3, "缺一个成员时其余三项照常响", str(len(mix.voices)))
engine.stop_all()
c2.items[1].sound = "A.wav"
engine._combo_cache.clear()

# ============ E. UI ============
print("\n=== E. 界面 ===")
from PySide6.QtWidgets import QApplication as QA
import settings_window as sw

ui_cfg = dict(sr.DEFAULT_CONFIG)   # 用默认配置打底，新增键也不会漏
ui_cfg.update({
    "hotkey": "y", "hold_ms": 180, "volume": 0.8, "slots": 8,
    "sensitivity": 0.85, "deadzone_px": 24, "noise_floor": 2,
    "max_offset_ratio": 0.9, "wheel_radius": 180, "wheel_anchor": "screen",
    "tap_action": "none", "repeat_last_key": "", "cycle_key": "",
    "open_settings_on_start": True, "autostart": False, "accent_theme": "green",
    "mic_enabled": False, "mic_device": "", "cable_device": "",
    "monitor_enabled": True, "mic_gain": 0.9, "cable_effect_gain": 1.0,
    "mic_latency_ms": 60, "fade_ms": 6, "audio_buffer_ms": 60,
})
try:
    win = sw.SettingsWindow(ui_cfg, cfg2, bank, engine)
    win.resize(1120, 780)
    win.show()
    app.processEvents()
    check(True, "配置窗口能创建")
    check(win.page_lib.combo_list.count() >= 1, "音效库里能列出组合",
          str(win.page_lib.combo_list.count()))
    win.page_lib.combo_list.setCurrentRow(0)
    dlg = sw.ComboEditorDialog(cfg2, c2, engine, win)
    dlg.resize(1020, 660)
    dlg.show()
    app.processEvents()
    check(dlg.table.rowCount() == 4, "编辑器表格行数 = 成员数", str(dlg.table.rowCount()))
    check(dlg.table.rowCount() == len(dlg.COLS) - 8 + 4, "表头列数正常")
    # 渲染一版留证：颜色/裁切/错位都能从图里看出来
    shot = tmp / "combo_editor.png"
    dlg.grab().save(str(shot))
    check(shot.exists() and shot.stat().st_size > 8000, "编辑器渲染成功（截图留档）",
          f"{shot.stat().st_size // 1024} KB")
    # 第一项的下拉必须锁死在"组合开始时"
    box = dlg.table.cellWidget(0, 2)
    check(box is not None and not box.isEnabled(), "第一项触发条件锁定为组合开始时")
    # 加一项 / 删一项：结构变了要重建，且不崩
    dlg.cdef.items.append(sc.ComboItem(sound="C.wav", trig=sc.TRIG_PREV_END))
    dlg.reload_table()
    check(dlg.table.rowCount() == 5, "加成员后表格同步", str(dlg.table.rowCount()))
    dlg.table.selectRow(4)
    dlg._remove_item()
    check(dlg.table.rowCount() == 4, "删成员后表格同步", str(dlg.table.rowCount()))
    dlg.close()
    win.close()
except Exception as exc:
    import traceback
    traceback.print_exc()
    check(False, "界面创建/渲染流程", repr(exc))

print()
if FAILS:
    print(f"结果：{len(FAILS)} 项失败")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("结果：全部通过")
