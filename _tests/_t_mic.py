"""麦克风注入链路的离线测试（不需要真的开声卡）。

覆盖：
1. MicCapture 预热：攒够余量之前不吐数据（否则一开机就狂补零，全是咔哒声）
2. 稳态水位：采多少取多少时，余量稳定在 target 附近
3. 时钟漂移：采集比播放快时自动丢帧，水位不会无限涨
4. 断档：采集停了就补零，不崩、不越界
5. Mixer 混音：麦克风真的进了输出，"音效音量"不影响麦克风、"麦克风音量"不影响音效
6. 双出口互不干扰：两个 Mixer 各走各的进度，不共用游标
7. 配置项齐全（缺一项会在 AudioEngine 里 KeyError）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QCoreApplication, QIODevice
from PySide6.QtMultimedia import QAudioFormat

import sr_roulette as sr

app = QCoreApplication([])

RATE = 48000
CH = 2
FMT = QAudioFormat()
FMT.setSampleRate(RATE)
FMT.setChannelCount(CH)
FMT.setSampleFormat(QAudioFormat.Float)

FAILS: list[str] = []


def check(ok: bool, title: str, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + title + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(title)


def push(cap: sr.MicCapture, frames: int, value: float = 0.5) -> None:
    """往采集缓冲区灌 frames 帧（模拟从 QAudioSource 读到的数据）。"""
    arr = np.full((frames, CH), value, dtype=np.float32)
    cap.push(arr.tobytes())


# ------------------------------------------------------------------ 1
print("=== 1. MicCapture 预热 ===")
cap = sr.MicCapture(FMT)
target = 2880                      # 60ms
push(cap, 480)
first = cap.pull(480, target)
check(float(np.abs(first).max()) == 0.0, "余量不够时不吐数据（预热等待）")
check(cap.underruns == 1, "记录了一次 underrun")
push(cap, 480 * 9)
got = 0
for _ in range(20):
    out = cap.pull(480, target)
    got += int(np.count_nonzero(out))
check(got > 0, "攒够余量后开始正常出数据", f"非零样本 {got}")

# ------------------------------------------------------------------ 2
print("\n=== 2. 稳态水位 ===")
cap = sr.MicCapture(FMT)
cap.push(np.full((480 * 20, CH), 0.3, dtype=np.float32).tobytes())
peaks = []
for _ in range(30):
    cap.pull(480, target)
    peaks.append(len(cap._buf))       # noqa: SLF001  （测试才看内部水位）
check(all(p >= 0 for p in peaks), "水位不为负")
check(max(peaks) <= target + 480, "水位不会超过 target+一次取量", f"max={max(peaks)}")
check(cap.dropped > 0, "多余的帧被丢掉了（这是漂移纠正）", f"dropped={cap.dropped}")

# ------------------------------------------------------------------ 3
print("\n=== 3. 时钟漂移 ===")
cap = sr.MicCapture(FMT)
push(cap, 480 * 50)                    # 一次灌 0.5 秒
for _ in range(200):
    cap.pull(480, target)              # 只取 480 × 200 = 2 秒量级里的 0.05 秒…不对，见下
# 上面取走的比灌进去的少得多，缓冲应该一直顶着上限
check(len(cap._buf) <= RATE * 2, "缓冲不会无限增长（2 秒上限兜底）", f"len={len(cap._buf)}")

# 真正测漂移：采集快 5%，跑 100 轮，水位应该被压在 target 附近
cap = sr.MicCapture(FMT)
push(cap, 480 * 12)
levels = []
for _ in range(100):
    push(cap, int(480 * 1.05))         # 采集比播放多 5%
    cap.pull(480, target)
    levels.append(len(cap._buf))
check(max(levels) <= target + int(480 * 1.05) + 8,
      "采集偏快时水位被压在 target 附近", f"max={max(levels)} target={target}")

# ------------------------------------------------------------------ 4
print("\n=== 4. 采集断档 ===")
cap = sr.MicCapture(FMT)
push(cap, 480 * 8)
cap.pull(480, target)                  # 预热完成
out = cap.pull(4800, target)           # 要的比存的多
check(out.shape == (4800, CH), "缺数据时补足返回长度", str(out.shape))
check(cap.underruns >= 1, "记到了 underrun")
cap._buf = cap._buf[:0]                # noqa: SLF001
cap._primed = False                    # noqa: SLF001
out = cap.pull(480, target)
check(float(np.abs(out).max()) == 0.0 and out.shape == (480, CH), "空缓冲拉取不崩，返回静音")

# ------------------------------------------------------------------ 5
print("\n=== 5. Mixer 混音：麦 + 音效 ===")
mix = sr.Mixer(FMT)
mix.open(QIODevice.ReadOnly)
clip = np.full((4800, CH), 0.4, dtype=np.float32)   # 100ms 音效
mix.volume = 1.0
mix.mic = sr.MicCapture(FMT)
mix.mic_target = target
mix.mic_gain = 1.0
push(mix.mic, 480 * 30, 0.2)           # 灌 300ms 麦克风

mix.trigger(clip, 1.0)
raw = np.frombuffer(mix.readData(4800 * 4 * CH), dtype="<f4").reshape(-1, CH)
check(raw.shape[0] == 4800, "取到 100ms 数据", str(raw.shape))
check(abs(float(raw[-1, 0]) - 0.6) < 0.02, "音效 0.4 + 麦克风 0.2 = 0.6",
      f"{float(raw[-1, 0]):.3f}")

# 音效音量只压音效，不该动麦克风
mix2 = sr.Mixer(FMT)
mix2.open(QIODevice.ReadOnly)
mix2.volume = 0.5                      # 平方律 -> 0.25
mix2.mic = sr.MicCapture(FMT)
mix2.mic_target = target
push(mix2.mic, 480 * 30, 0.2)
mix2.trigger(clip, 1.0)
raw2 = np.frombuffer(mix2.readData(4800 * 4 * CH), dtype="<f4").reshape(-1, CH)
expect = 0.4 * 0.25 + 0.2
check(abs(float(raw2[-1, 0]) - expect) < 0.02,
      "调小音效音量不影响麦克风原声", f"{float(raw2[-1, 0]):.3f} vs {expect:.3f}")

# 麦克风音量独立
mix3 = sr.Mixer(FMT)
mix3.open(QIODevice.ReadOnly)
mix3.volume = 1.0
mix3.mic = sr.MicCapture(FMT)
mix3.mic_target = target
mix3.mic_gain = 0.5
push(mix3.mic, 480 * 30, 0.2)
mix3.trigger(clip, 1.0)
raw3 = np.frombuffer(mix3.readData(4800 * 4 * CH), dtype="<f4").reshape(-1, CH)
check(abs(float(raw3[-1, 0]) - (0.4 + 0.1)) < 0.02, "调麦音量不影响音效",
      f"{float(raw3[-1, 0]):.3f}")

# 没有麦克风时行为不变
mix4 = sr.Mixer(FMT)
mix4.open(QIODevice.ReadOnly)
mix4.volume = 1.0                       # 默认 0.8 -> 平方律 0.64，这里先拉满才好比
mix4.trigger(clip, 1.0)
raw4 = np.frombuffer(mix4.readData(4800 * 4 * CH), dtype="<f4").reshape(-1, CH)
check(abs(float(raw4[-1, 0]) - 0.4) < 0.02, "没开麦克风时输出和以前一样",
      f"{float(raw4[-1, 0]):.3f}")

# 限幅：两路都很大时不能超过 1.0
mix5 = sr.Mixer(FMT)
mix5.open(QIODevice.ReadOnly)
mix5.volume = 1.0
mix5.mic = sr.MicCapture(FMT)
mix5.mic_target = target
push(mix5.mic, 480 * 30, 0.9)
mix5.trigger(np.full((4800, CH), 0.9, dtype=np.float32), 1.0)
raw5 = np.frombuffer(mix5.readData(4800 * 4 * CH), dtype="<f4").reshape(-1, CH)
check(float(np.abs(raw5).max()) <= 1.0, "叠加后限幅在 ±1.0 以内",
      f"max={float(np.abs(raw5).max()):.3f}")

# ------------------------------------------------------------------ 6
print("\n=== 6. 双出口互不干扰 ===")
head = sr.Mixer(FMT)      # 耳机
cable = sr.Mixer(FMT)     # 虚拟声卡
head.open(QIODevice.ReadOnly)
cable.open(QIODevice.ReadOnly)
cable.mic = sr.MicCapture(FMT)
cable.mic_target = target
push(cable.mic, 480 * 30, 0.0)
clip2 = np.full((RATE * 2, CH), 0.3, dtype=np.float32)   # 2 秒
head.trigger(clip2, 1.0)
cable.trigger(clip2, 1.0)
# 耳机每次取 1024 帧、虚拟声卡每次取 480 帧，节奏不同
for _ in range(10):
    head.readData(1024 * 4 * CH)
for _ in range(5):
    cable.readData(480 * 4 * CH)
h_pos = head.voices[0][1] if head.voices else 0
c_pos = cable.voices[0][1] if cable.voices else 0
check(h_pos == 10240 and c_pos == 2400, "两路进度各自推进，没有互相抢",
      f"耳机={h_pos} 声卡={c_pos}")
check(head.mic is None and cable.mic is not None, "麦克风只挂在虚拟声卡那一路")

# stop_all 要能同时掐两路（淡出 12ms = 576 帧，取满一帧数才真正静音）
head.stop_all()
cable.stop_all()
head.readData(1024 * 4 * CH)
cable.readData(1024 * 4 * CH)
check(not head.playing and not cable.playing, "stop_all 两路都停")

# ------------------------------------------------------------------ 7
print("\n=== 7. 配置项齐全 ===")
for key, want in (
    ("mic_enabled", bool),
    ("mic_device", str),
    ("cable_device", str),
    ("mic_gain", float),
    ("cable_effect_gain", float),
    ("monitor_enabled", bool),
    ("mic_latency_ms", int),
):
    ok = key in sr.DEFAULT_CONFIG and isinstance(sr.DEFAULT_CONFIG[key], want)
    check(ok, f"DEFAULT_CONFIG['{key}'] 存在且类型对",
          f"{sr.DEFAULT_CONFIG.get(key)!r}")

check(sr.DEFAULT_CONFIG["mic_enabled"] is False, "默认不开麦克风注入（行为与旧版一致）")

# ------------------------------------------------------------------ 8
print("\n=== 8. 设备识别 ===")
check(sr.is_virtual_name("CABLE Input (VB-Audio Virtual Cable)"), "CABLE 被判为虚拟设备")
check(sr.is_virtual_name("VoiceMeeter Input"), "VoiceMeeter 被判为虚拟设备")
check(not sr.is_virtual_name("耳机 (USB Audio Device)"), "耳机不被误判")
check(not sr.is_virtual_name("麦克风 (K3)"), "K3 不被误判")
names = [d.description() for d in sr.client_inputs()] if hasattr(sr, "client_inputs") else []
real = sr.real_inputs()
check(all(not sr.is_virtual_name(d.description()) for d in real),
      "真实麦克风列表里没有虚拟设备")
vo = sr.virtual_outputs()
check(all(sr.is_virtual_name(d.description()) for d in vo), "虚拟输出列表里全是虚拟设备")

print()
if FAILS:
    print(f"FAILED {len(FAILS)}:")
    for f in FAILS:
        print("   -", f)
    sys.exit(1)
print("ALL PASS")
