"""组合新增的两种"推进式"播放模式测试（v0.7.6）。

CM_STEP 按顺序点击播放：每触发一次只响 1 项，ABCD→ABCD 一直循环。
CM_ACC  累加播放：第 1 次响 A，第 2 次响 A+B，第 3 次响 A+B+C……叠满后回到 A。

覆盖：
A. 数据层：新模式不会被 clamped 打回 seq，能往返保存
B. play_order 纯函数：游标 -> 成员下标
C. 引擎：连按多次，每次真的只播应播的项数，游标按 ABCD 循环
D. 导出：bake_combo 在推进式模式下导出完整一轮，而不是"下一次那一段"
E. UI：下拉框四项、选 step 时隐藏 N/打乱、文案口径正确
"""
import os
import sys
import tempfile
import time
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
write_wav(snd / "A.wav", 1.0, 440.0)
write_wav(snd / "B.wav", 2.0, 495.0)
write_wav(snd / "C.wav", 1.0, 550.0)
write_wav(snd / "D.wav", 1.0, 660.0)
NAMES = ["A.wav", "B.wav", "C.wav", "D.wav"]

# ============ A. 数据层 ============
print("=== A. 数据层 ===")
cfg = sc.SoundsConfig(tmp / "sounds.json")
cfg.load()
cfg.sync([f.name for f in snd.iterdir()])
cd1 = cfg.new_combo("点击接龙")
cd1.mode = sc.CM_STEP
cd1.items = [sc.ComboItem(sound=n, trig=sc.TRIG_COMBO if i == 0 else sc.TRIG_PREV_END)
             for i, n in enumerate(NAMES)]
cd2 = cfg.new_combo("越点越多")
cd2.mode = sc.CM_ACC
cd2.items = [sc.ComboItem(sound=n, trig=sc.TRIG_COMBO if i == 0 else sc.TRIG_PREV_END)
             for i, n in enumerate(NAMES)]
cfg.order += [cfg.combo_key(cd1.cid), cfg.combo_key(cd2.cid)]
cfg.save()

cfg2 = sc.SoundsConfig(tmp / "sounds.json")
cfg2.load()
a1 = cfg2.combo_of(cfg2.combo_key(cd1.cid))
a2 = cfg2.combo_of(cfg2.combo_key(cd2.cid))
check(a1 is not None and a1.mode == sc.CM_STEP, "step 模式往返保存", a1.mode if a1 else "-")
check(a2 is not None and a2.mode == sc.CM_ACC, "acc 模式往返保存", a2.mode if a2 else "-")
check(sc.CM_STEP in sc.COMBO_MODES and sc.CM_ACC in sc.COMBO_MODES, "新模式进了 COMBO_MODES")
check(len(sc.COMBO_MODES) == 4, "模式总数 4", str(len(sc.COMBO_MODES)))
for m in sc.COMBO_MODES:
    check(m in sc.COMBO_MODE_LABEL and m in sc.COMBO_MODE_TIP, f"{m} 有文案")
check(sc.ComboDef(items=a1.items, mode=sc.CM_STEP).clamped().mode == sc.CM_STEP,
      "clamped 不会把 step 打回 seq")

# ============ B. play_order ============
print("\n=== B. play_order ===")
step_def = sc.ComboDef(cid="s1", mode=sc.CM_STEP, items=a1.items)
check([step_def.play_order(k) for k in range(4)] == [[0], [1], [2], [3]],
      "step: 游标 0/1/2/3 -> 单项", str([step_def.play_order(k) for k in range(4)]))
check(step_def.play_order(4) == [0], "step: 游标绕过末尾回到第 1 项")
check(step_def.play_order(9) == [1], "step: 游标越界也安全", str(step_def.play_order(9)))
check(step_def.steps_per_trigger() == 1, "step: 每次推进 1 格")

acc_def = sc.ComboDef(cid="s2", mode=sc.CM_ACC, items=a2.items)
check([acc_def.play_order(k) for k in range(4)] == [[0], [0, 1], [0, 1, 2], [0, 1, 2, 3]],
      "acc: 游标 k -> 前 k+1 项", str([acc_def.play_order(k) for k in range(4)]))
check(acc_def.play_order(4) == [0], "acc: 叠满后回到只响第 1 项")

seq_def = sc.ComboDef(cid="s3", mode=sc.CM_SEQ, items=a1.items)
check(seq_def.play_order(3) == [0, 1, 2, 3], "seq: 传游标也不受影响")
check(seq_def.steps_per_trigger() == 0, "seq: 不用游标")

# ============ C. 引擎 ============
print("\n=== C. 引擎连按 ===")
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)
sr.SOUNDS_DIR = snd
bank = sr.SoundBank(8, scfg=cfg2)
engine = sr.AudioEngine(bank, dict(sr.DEFAULT_CONFIG))
mix = engine._mixers_all()[0]

step_key = cfg2.combo_key(cd1.cid)
acc_key = cfg2.combo_key(cd2.cid)
step_i = bank.index_of_name(step_key)
acc_i = bank.index_of_name(acc_key)
check(step_i >= 0 and acc_i >= 0, "两个组合都上了轮盘", f"{step_i}/{acc_i}")


def press(idx: int) -> int:
    """按一次，返回这次真的被塞进混音器的语音条数。

    不调 stop_all：离屏环境里停掉 sink 再播会走 rebuild，rebuild 会把
    voices 清空，增量就数不准了（这是测试环境的伪影，不是产品问题）。
    """
    before = len(engine.mixer.voices)
    ok = engine.play(idx)
    after = len(engine.mixer.voices)
    return (after - before) if ok else -1


# 这一段验的是"排程往混音器里塞了几条 voice"，本来就不需要真的出声。
# 但声卡是独占资源：连着跑一堆测试时设备偶尔还被上一个进程占着，
# rebuild 建不出 sink -> _active_mixers() 为空 -> play() 直接返回 False，
# 数出来就是 -1。那是环境问题，不是排程问题，所以挂个哨兵让
# _active_mixers() 恒为真（stop_all 只碰 mixer，不碰这个哨兵）。
engine._sink = object()


cd1_obj = cfg2.combo_of(step_key)
cd2_obj = cfg2.combo_of(acc_key)
check(cd1_obj is not None and cd2_obj is not None, "两个组合都能取回定义")
engine._combo_step.clear()
engine.play(step_i)                 # 预热：先把输出设备拉起来，之后增量才稳
engine.stop_all()
engine.play(step_i)                 # rebuild 会清空 voices，再预热一次
engine._combo_step.clear()
step_counts = [press(step_i) for _ in range(6)]
check(step_counts == [1, 1, 1, 1, 1, 1],
      "step: 连按 6 次每次都只响 1 项", str(step_counts))
check(engine._combo_step.get(cd1_obj.cid) == 2,
      "step: 6 次后游标落在第 3 项（6 % 4）",
      str(engine._combo_step.get(cd1_obj.cid)))

engine.stop_all()
engine._combo_step.clear()
acc_counts = [press(acc_i) for _ in range(6)]
check(acc_counts == [1, 2, 3, 4, 1, 2],
      "acc: 1/2/3/4 叠满后回到 1", str(acc_counts))

engine.stop_all()

# 试听（from_row）不能动游标
engine._combo_step.clear()
engine.play_combo(cd1_obj, from_row=2)
engine.stop_all()
check(engine._combo_step.get(cd1_obj.cid, 0) == 0,
      "从第 3 项试听不推进游标", str(engine._combo_step.get(cd1_obj.cid, 0)))

# 冷却期内不推进游标（冷却状态在 engine 里按 cid 记，得先清掉上一轮留下的时间戳）
live_cdef = bank.entry_at(step_i).cdef
live_cdef.cooldown_ms = 100000
engine._combo_step.clear()
engine._combo_last.pop(live_cdef.cid, None)
engine.play_combo(live_cdef)                       # 第一次放行
engine._combo_last[live_cdef.cid] = time.monotonic()
blocked = engine.play_combo(live_cdef)             # 第二次被冷却挡掉
engine.stop_all()
check(blocked is False, "冷却期内的第二次确实被挡", str(blocked))
check(engine._combo_step.get(live_cdef.cid) == 1,
      "冷却挡掉的那次不推进游标", str(engine._combo_step.get(live_cdef.cid)))
live_cdef.cooldown_ms = 0

# ============ D. 导出 ============
print("\n=== D. 导出 ===")
engine._combo_step.clear()
engine._combo_step[cd1_obj.cid] = 2      # 游标停在第 3 项
baked = engine.bake_combo(cd1_obj)
left_step = engine._combo_step.get(cd1_obj.cid)
check(baked is not None, "step 模式下能导出")
if baked is not None:
    wave_arr, rate = baked
    dur = len(wave_arr) / float(rate)
    # 完整一轮 = 1+2+1+1 = 5 秒（接龙，无重叠）
    check(3.9 < dur < 6.1, "导出的是完整一轮（约 5 秒），不是单项",
          f"{dur:.2f}s")
check(left_step == 2, "导出不推进游标", str(left_step))

# ============ E. UI ============
print("\n=== E. 界面 ===")
import settings_window as sw

ui_cfg = dict(sr.DEFAULT_CONFIG)
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
shown = False
try:
    win = sw.SettingsWindow(ui_cfg, cfg2, bank, engine)
    win.resize(1120, 780)
    win.show()
    app.processEvents()
    dlg = sw.ComboEditorDialog(cfg2, cd1_obj, engine, win)
    dlg.resize(1020, 660)
    dlg.show()
    app.processEvents()
    labels = [dlg.cmb_mode.itemText(i) for i in range(dlg.cmb_mode.count())]
    check(len(labels) == 4, "下拉框 4 个模式", str(labels))
    check(any("点击" in s for s in labels), "下拉框里有「按顺序点击播放」")
    check(any("累加" in s for s in labels), "下拉框里有「累加播放」")

    dlg.cmb_mode.setCurrentIndex(dlg.cmb_mode.findData(sc.CM_STEP))
    dlg._sync_mode_widgets()
    app.processEvents()
    check(not dlg.spn_count.isVisible() and not dlg.chk_shuffle.isVisible(),
          "step 模式下 N/打乱控件隐藏")
    dlg._sync_combo_widgets()
    txt = dlg.lbl_total.text()
    check("每次点只响其中 1 项" in txt and "一整轮" in txt, "状态栏写明口径", txt)

    # 切到累加模式要改下拉框：_sync_combo_widgets 会从控件回读 mode，直接改 cdef 会被覆盖
    dlg.cmb_mode.setCurrentIndex(dlg.cmb_mode.findData(sc.CM_ACC))
    dlg._sync_mode_widgets()
    dlg._sync_combo_widgets()
    check("第 N 次叠前 N 项" in dlg.lbl_total.text(), "acc 口径", dlg.lbl_total.text())

    # "试听整个组合"在推进式模式下要播完整一轮，且不能动游标
    dlg.cmb_mode.setCurrentIndex(dlg.cmb_mode.findData(sc.CM_STEP))
    dlg._sync_mode_widgets()
    dlg._sync_combo_widgets()
    engine.stop_all()
    engine._combo_step.clear()
    # 哨兵不是真的 sink，没人把 voices 抽走，列表会累积，所以只比增量
    _v0 = len(engine.mixer.voices)
    dlg._preview_all()
    n_all = len(engine.mixer.voices) - _v0
    engine.stop_all()
    check(n_all == 4, "step 模式「试听整个组合」播的是一整轮（4 项）", str(n_all))
    check(engine._combo_step.get(live_cdef.cid, 0) == 0,
          "「试听整个组合」不推进游标", str(engine._combo_step.get(live_cdef.cid, 0)))

    shot = tmp / "combo_editor_step.png"
    dlg.grab().save(str(shot))
    check(shot.exists() and shot.stat().st_size > 8000, "编辑器渲染成功（截图留档）",
          f"{shot.stat().st_size // 1024} KB")
    shown = True
    dlg.close()
    win.close()
except Exception as exc:
    import traceback
    traceback.print_exc()
    check(False, "界面创建/渲染流程", repr(exc))
    shown = True

print()
if FAILS:
    print("失败 %d 项：%s" % (len(FAILS), "、".join(FAILS)))
    sys.exit(1)
print("结果：全部通过")
