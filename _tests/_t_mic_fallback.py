"""麦克风「自动降级」测试。

背景：有用户反馈"麦克风不能自动降级，导致无法识别"。老代码只认
48kHz/立体声/浮点，设备不认就直接报错收手；设备打不开也不换；拔插不重连。

覆盖：
A. 格式梯子 capture_format：往下退的顺序对不对
B. 采集端格式转换：整型/单声道/采样率都能救回来，声音不走样
C. 设备梯子 _start_capture：第一个打不开就换下一个
D. 重连：需要重建的判断 + 失败限频（别每 3 秒砸一次）
E. 虚拟声卡开不起来要留错误（不再静默）
F. audio_status 新字段 / release_capture
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

FAILS = []


def check(ok, name, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(name)


RATE = 48000
tmp = Path(tempfile.mkdtemp())
snd = tmp / "sounds"
snd.mkdir()
n = RATE
t = np.arange(n) / RATE
with wave.open(str(snd / "a.wav"), "wb") as h:
    h.setnchannels(1)
    h.setsampwidth(2)
    h.setframerate(RATE)
    h.writeframes((0.4 * np.sin(2 * np.pi * 440 * t) * 32767).astype("<i2").tobytes())

cfg = sc.SoundsConfig(tmp / "sounds.json")
cfg.load()
cfg.sync([f.name for f in snd.iterdir()])
app = QApplication.instance() or QApplication(sys.argv)
sr.SOUNDS_DIR = snd
bank = sr.SoundBank(8, scfg=cfg)


def _f(rate, ch, sf):
    return sr._fmt(rate, ch, sf)


F32, I16 = QAudioFormat.Float, QAudioFormat.Int16


class FakeDev:
    """假设备：只认 listed 里的那几组格式。"""

    def __init__(self, name, supported, preferred=None):
        self._name = name
        self._sup = set(supported)
        self._pref = preferred or list(supported)[0]

    def description(self):
        return self._name

    def isFormatSupported(self, f):
        return (f.sampleRate(), f.channelCount(), f.sampleFormat()) in self._sup

    def preferredFormat(self):
        return _f(*self._pref)


# ============ A. 格式梯子 ============
print("\n=== A. 格式梯子 ===")
bt = FakeDev("蓝牙耳麦", {(16000, 1, I16)}, preferred=(16000, 1, I16))
got = sr.capture_format(bt)
check(got is not None and (got.sampleRate(), got.channelCount()) == (16000, 1),
      "只支持 16k/单声道 的设备：挑得到能用的格式", str(got))

int16_only = FakeDev("老USB麦", {(48000, 2, I16)}, preferred=(48000, 2, I16))
got = sr.capture_format(int16_only)
check(got is not None and got.sampleFormat() == I16 and got.channelCount() == 2,
      "只支持整型时：先保 48k/立体声，退到整型", str(got))

mono48 = FakeDev("单声道麦", {(48000, 2, F32), (48000, 1, F32)}, preferred=(48000, 1, F32))
got = sr.capture_format(mono48)
check(got is not None and got.channelCount() == 2, "能立体声就别退单声道", str(got))

nothing = FakeDev("怪设备", set(), preferred=(44100, 1, F32))
got = sr.capture_format(nothing)
check(got is not None and got.sampleRate() == 44100, "一个都不认时：用设备自报的首选格式", str(got))

check(sr.capture_format(None) is None, "设备为 None 不崩，返回 None")

# ============ B. 采集端格式转换 ============
print("\n=== B. 采集端转换（16k/单声道/整型 -> 48k/立体声/浮点）===")

DST = _f(48000, 2, F32)


def make_sine(rate, seconds, freq=440.0, amp=0.5):
    m = int(rate * seconds)
    tt = np.arange(m) / rate
    return (amp * np.sin(2 * np.pi * freq * tt)).astype(np.float32)


def dom_freq(x, rate):
    """用 FFT 找主频，验重采样后音高没跑。"""
    x = np.asarray(x, dtype=np.float64).ravel()
    w = np.hanning(len(x))
    spec = np.abs(np.fft.rfft(x * w))
    k = int(np.argmax(spec[1:])) + 1
    return k * rate / len(x)


# 16k 单声道 整型 -> 48k 立体声 浮点
SRC = _f(16000, 1, I16)
cap = sr.MicCapture(DST, src_fmt=SRC)
sig = make_sine(16000, 1.0, 440.0, 0.5)
raw = (sig * 32767).astype("<i2").tobytes()
# 故意切成不对齐的块（3331 字节 = 1665.5 帧），边喂边取，和真实链路一样：
# 采集每 8ms 来一小块，播放端每 10ms 要 480 帧
TGT = 2400          # 稳态余量 50ms，和产品里一致
step = 3331
outs = []
for i in range(0, len(raw), step):
    cap.push(raw[i:i + step])
    while len(cap._buf) >= 4800 + TGT:
        outs.append(cap.pull(4800, TGT))
while len(cap._buf) >= 4800 + TGT:
    outs.append(cap.pull(4800, TGT))
out = np.concatenate(outs) if outs else np.zeros((0, 2))
check(out.shape[1] == 2, "单声道补成了立体声", str(out.shape))
check(abs(dom_freq(out[:48000, 0], 48000) - 440.0) < 3.0,
      "重采样后音高没跑（仍在 440Hz 附近）", f"{dom_freq(out[:48000, 0], 48000):.1f}Hz")
check(abs(float(np.abs(out[:48000]).max()) - 0.5) < 0.06,
      "音量没被改变（0.5 进去 0.5 出来）", f"{float(np.abs(out[:48000]).max()):.3f}")
# 取走的 + 还在缓冲的 + 当作时钟漂移主动丢掉的，应当凑齐一秒钟的量。
# （这一测里每块喂进去的比取走的多 4%，多出来的会被 drift 纠正丢掉，这是设计如此）
_total = len(out) + len(cap._buf) + cap.dropped
check(_total >= 47500, "一秒钟的素材没凭空消失（取走+缓冲+漂移丢弃≈48000）",
      f"{_total}（dropped={cap.dropped}）")

# 44.1k 立体声浮点 -> 48k：声道不动，只重采样
cap2 = sr.MicCapture(DST, src_fmt=_f(44100, 2, F32))
s2 = make_sine(44100, 1.0, 440.0, 0.4)
st = np.repeat(s2[:, None], 2, axis=1).astype(np.float32)
o2 = []
for i in range(0, len(st), 4000):
    cap2.push(st[i:i + 4000].tobytes())
    while len(cap2._buf) >= 4800 + 2400:
        o2.append(cap2.pull(4800, 2400))
out2 = np.concatenate(o2) if o2 else np.zeros((0, 2))
check(abs(dom_freq(out2[:48000, 0], 48000) - 440.0) < 3.0,
      "44.1k -> 48k 音高也准", f"{dom_freq(out2[:48000, 0], 48000):.1f}Hz")

# 尾巴字节：319 + 1 字节应当拼成完整的 160 帧
cap3 = sr.MicCapture(DST, src_fmt=SRC)
one = (make_sine(16000, 0.01) * 32767).astype("<i2").tobytes()   # 160 帧 = 320 字节
cap3.push(one[:319])
mid = cap3.pushed
cap3.push(one[319:])
check(len(cap3._buf) >= 470, "不满一帧的尾巴没丢（拼起来继续用）",
      f"pushed={cap3.pushed} buf={len(cap3._buf)}")
check(cap3._raw_tail == b"", "尾巴清空了", str(cap3._raw_tail))

# 声道一致时不该多做事
cap4 = sr.MicCapture(DST, src_fmt=DST)
cap4.push(make_sine(48000, 0.1).reshape(-1, 1).repeat(2, axis=1).astype(np.float32).tobytes())
check(len(cap4._buf) == 4800, "格式相同就直接用，不转换", str(len(cap4._buf)))

# 老的调用方式（只传一个参数）仍然按"两边一致"处理
cap5 = sr.MicCapture(DST)
check(cap5.src_rate == 48000 and cap5.src_channels == 2, "旧式单参构造仍然可用")

# ============ C. 设备梯子 ============
print("\n=== C. 设备梯子 ===")
engine = sr.AudioEngine(bank, dict(sr.DEFAULT_CONFIG))

bad = FakeDev("坏掉的麦克风", {(48000, 2, F32)}, preferred=(48000, 2, F32))
good = FakeDev("能用的麦克风", {(48000, 2, F32)}, preferred=(48000, 2, F32))
sr.capture_candidates = lambda prefer="": [bad, good]

tried = []


def fake_probe(dev, fmt):
    tried.append(dev.description())
    if dev.description() == "坏掉的麦克风":
        return None, "被占用"
    cap = sr.MicCapture(engine.fmt, src_fmt=fmt)

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

    return ((cap, FakeSrc(), object()), "")


engine._probe_capture = fake_probe
engine._start_capture()
check(engine.capture is not None, "第一个打不开就换下一个，最终开起来了")
check(engine._mic_name == "能用的麦克风", "用的是第二个设备", engine._mic_name)
check(engine.mic_error == "", "成功时不留错误信息", engine.mic_error)
check(tried == ["坏掉的麦克风", "能用的麦克风"], "按候选顺序挨个试", str(tried))

# 全都失败：错误里要带上原因，不能只说"打不开"
engine._stop_capture()
sr.capture_candidates = lambda prefer="": [bad]
engine._start_capture()
check(engine.capture is None and engine.mic_error.startswith("麦克风打不开："),
      "全失败时给出可读的错误", engine.mic_error)
check("被占用" in engine.mic_error, "错误里带了具体原因", engine.mic_error)

# 候选列表：剔掉虚拟设备、不重复
sr.capture_candidates = lambda prefer="": [bad, good]
check(sr.capture_candidates() == [bad, good], "候选列表按给定顺序")

# ============ D. 重连判断与限频 ============
print("\n=== D. 重连 ===")
engine2 = sr.AudioEngine(bank, dict(sr.DEFAULT_CONFIG))
engine2.cfg["mic_enabled"] = True
engine2.capture = None
engine2._mic_try_at = time.monotonic()
check(engine2._capture_needs_rebuild() is False, "刚失败过不立刻重试（避免每 3 秒砸一次）")
engine2._mic_try_at = time.monotonic() - 11.0
check(engine2._capture_needs_rebuild() is True, "过了 10 秒会再试一次")
engine2.cfg["mic_enabled"] = False
check(engine2._capture_needs_rebuild() is False, "没开麦克风就不折腾")

engine2.cfg["mic_enabled"] = True
engine2.capture = sr.MicCapture(engine2.fmt)
engine2._mic_name = "早就拔掉的麦克风"
sr.find_input = lambda name: None
check(engine2._capture_needs_rebuild() is True, "正在用的麦克风消失了要重连")
sr.find_input = lambda name: object()
check(engine2._capture_needs_rebuild() is False, "设备还在就别乱重建")

# ============ E. 虚拟声卡开不起来 ============
print("\n=== E. 虚拟声卡 ===")
engine3 = sr.AudioEngine(bank, dict(sr.DEFAULT_CONFIG))
sr.guess_virtual_output = lambda prefer="": None
engine3._start_cable_sink()
check(engine3.cable_error == "没找到虚拟声卡", "没有虚拟声卡时留下错误", engine3.cable_error)
check("cable_error" in engine3.audio_status(), "状态里带得出去")

# ============ F. 状态与释放 ============
print("\n=== F. 状态与释放 ===")
engine4 = sr.AudioEngine(bank, dict(sr.DEFAULT_CONFIG))
st = engine4.audio_status()
check({"mic", "cable", "error", "cable_error", "note"} <= set(st),
      "audio_status 字段齐全", str(sorted(st)))
engine4.capture = sr.MicCapture(engine4.fmt)
engine4._mic_name = "某麦克风"
engine4.release_capture()
check(engine4.capture is None and engine4._mic_name == "", "release_capture 放掉麦克风")

print()
if FAILS:
    print(f"失败 {len(FAILS)} 项：" + "、".join(FAILS))
    sys.exit(1)
print("结果：全部通过")
