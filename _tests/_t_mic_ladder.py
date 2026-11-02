"""「设备谎报格式」+「只装了虚拟声卡」两种情况的回归测试。

背景（2026-11-01 用户反馈）：有人说"麦克风不支持 48kHz 立体声，然后设备检测不到，
没办法麦克风注入"。查证后是两个不同的问题：

1. 那句"不支持 48kHz 立体声"是 **v0.7.0 及更早**的原话，v0.7.7 已改成格式梯子。
2. 但梯子只在**第一档**试一次就换设备：设备谎报"48k 立体声没问题"、真开却拒绝时，
   整台设备被放弃，明明 16k 单声道能出声也用不上 —— 这个在 v0.8.0 仍然存在。

覆盖：
A. capture_formats：一台设备给出一整条梯子（而不是一个格式）
B. 谎报设备：48k 打不开会自动往下退，最终能用 16k 单声道开起来
C. 全失败：有时长上限，不会把启动拖成几秒
D. 界面：一个真麦克风都没筛出来时，列全部设备并标注，而不是显示"没检测到麦克风"
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
from PySide6.QtMultimedia import QAudioFormat
from PySide6.QtWidgets import QApplication

import sounds_config as sc
import sr_roulette as sr

FAILS: list[str] = []


def check(ok, name, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(name)


F32, I16 = QAudioFormat.Float, QAudioFormat.Int16

app = QApplication.instance() or QApplication([])

tmp = Path(tempfile.mkdtemp())
snd = tmp / "sounds"
snd.mkdir()
RATE = 48000
with wave.open(str(snd / "a.wav"), "wb") as h:
    h.setnchannels(1)
    h.setsampwidth(2)
    h.setframerate(RATE)
    h.writeframes(
        (0.4 * np.sin(2 * np.pi * 440 * np.arange(4800) / RATE) * 32767)
        .astype("<i2").tobytes()
    )
sr.SOUNDS_DIR = snd
cfg_snd = sc.SoundsConfig(tmp / "sounds.json")
cfg_snd.load()
cfg_snd.sync([p.name for p in snd.iterdir()])
bank = sr.SoundBank(8, scfg=cfg_snd)


class LieDev:
    """谎言型设备：isFormatSupported 满口答应，真 open 只认一个格式。"""

    def __init__(self, name="爱撒谎的麦克风", real=(16000, 1, I16), claim_all=True):
        self._name = name
        self._real = real
        self._claim_all = claim_all

    def description(self):
        return self._name

    def isFormatSupported(self, f):
        if self._claim_all:
            return True
        return (f.sampleRate(), f.channelCount(), f.sampleFormat()) == self._real

    def preferredFormat(self):
        return sr._fmt(48000, 2, F32)


def fake_src(engine):
    class FakeSrc:
        def bufferSize(self):
            return 1920

        def state(self):
            class S:
                name = "ActiveState"
            return S()

        def stop(self):
            pass

        def deleteLater(self):
            pass

    return FakeSrc()


def make_engine(dev, delay=0.0):
    """造一个引擎，把候选设备换成给定的一台，并记录试了哪些格式。"""
    engine = sr.AudioEngine(bank, dict(sr.DEFAULT_CONFIG))
    tried = []
    orig_cands = sr.capture_candidates
    sr.capture_candidates = lambda prefer="": [dev]

    def probe(d, fmt):
        if delay:
            time.sleep(delay)
        key = (fmt.sampleRate(), fmt.channelCount(), fmt.sampleFormat())
        tried.append(key)
        if key != (16000, 1, I16):
            return None, "打不开（设备拒绝了）"
        return ((sr.MicCapture(engine.fmt, src_fmt=fmt), fake_src(engine), object()), "")

    engine._probe_capture = probe
    engine._restore_cands = lambda: setattr(sr, "capture_candidates", orig_cands)
    return engine, tried


# ============ A. 一台设备 = 一串格式 ============
print("\n=== A. capture_formats 给整条梯子 ===")
lie = LieDev()
fmts = sr.capture_formats(lie)
check(len(fmts) >= 6, "谎报设备：给出的候选格式不止一两个", f"{len(fmts)} 个")
check(
    any((f.sampleRate(), f.channelCount()) == (16000, 1) for f in fmts),
    "候选里包含 16k 单声道（最后那根救命稻草）",
    str([(f.sampleRate(), f.channelCount()) for f in fmts]),
)
check(
    (fmts[0].sampleRate(), fmts[0].channelCount()) == (48000, 2),
    "顺序仍然从最好的开始（48k 立体声）",
    f"{fmts[0].sampleRate()}Hz/{fmts[0].channelCount()}ch",
)
check(
    sr.capture_format(lie).sampleRate() == 48000,
    "capture_format 仍然只取第一选择（老接口没变）",
)

only16 = LieDev("只认16k的麦", real=(16000, 1, I16), claim_all=False)
f2 = sr.capture_formats(only16)
check(
    len(f2) == 1 and (f2[0].sampleRate(), f2[0].channelCount()) == (16000, 1),
    "老实的设备只报 16k：候选就只有一条，不瞎试",
    f"{len(f2)} 个",
)

# ============ B. 谎报设备能救回来 ============
print("\n=== B. 谎报设备：退到底能开起来 ===")
engine, tried = make_engine(LieDev())
engine._start_capture()
check(engine.capture is not None, "48k 打不开之后，最终用 16k 单声道开起来了",
      engine.mic_error or "无错误")
check(engine._mic_name == "爱撒谎的麦克风", "用的还是这台设备", engine._mic_name)
check(len(tried) > 1, "确实是在同一台设备上换了多个格式试", f"试了 {len(tried)} 种")
check("16kHz" in engine.mic_note and "单声道" in engine.mic_note,
      "状态里说明了自动适配的结果", engine.mic_note)
check(engine.mic_error == "", "成功时不留下错误信息", engine.mic_error)
engine._stop_capture()
engine._restore_cands()

# ============ C. 全失败不会卡住 ============
print("\n=== C. 全失败：有总时长上限 ===")
dead = LieDev("死掉的麦克风")
engine2, tried2 = make_engine(dead, delay=0.25)
t0 = time.monotonic()
engine2._start_capture()
cost = time.monotonic() - t0
check(engine2.capture is None, "确实开不起来")
check(cost < 2.5, "没有把启动拖成好几秒（上限 1.5 秒左右）", f"{cost:.2f} 秒")
check(engine2.mic_error.startswith("麦克风打不开："), "错误信息能看懂", engine2.mic_error)
check("试了" in engine2.mic_error and "48k" in engine2.mic_error,
      "错误里带了「试了几种」和具体是哪个格式不行", engine2.mic_error)
engine2._restore_cands()

# ============ D. 界面：一个真麦都没有时 ============
print("\n=== D. 只有虚拟设备时的下拉框 ===")
import settings_window as sw

real_backup = sr.real_inputs
all_backup = sr.all_inputs
sr.real_inputs = lambda: []
sr.all_inputs = lambda: [LieDev("CABLE Output (VB-Audio Virtual Cable)")]
win = sw.SettingsWindow(dict(sr.DEFAULT_CONFIG), cfg_snd, bank, None)
app.processEvents()
box = win.page_mic.cmb_mic
texts = [box.itemText(i) for i in range(box.count())]
check(texts and "没检测到麦克风" not in texts[0], "不再显示「没检测到麦克风」这种死路", str(texts))
check(any("虚拟设备" in t for t in texts), "设备被标了「虚拟设备，选它对方听不到你说话」", str(texts))
check(box.itemData(0) == "CABLE Output (VB-Audio Virtual Cable)",
      "下拉框的取值仍是原始设备名（配置还能对上）", str(box.itemData(0)))

sr.real_inputs = real_backup
sr.all_inputs = all_backup

print("\n" + "=" * 56)
if FAILS:
    print(f"结果：{len(FAILS)} 项未通过")
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("全部通过")
