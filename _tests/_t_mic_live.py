"""真实声卡链路测试：真的开采集、真的开两个出口，跑几秒看数据有没有流动。

不依赖人说话，只看"帧数有没有被消费掉"——链路通的话，虚拟声卡那一路会持续
从采集缓冲区取数据，consumed 会随时间线性增长；链路断了的话 consumed 是 0，
缓冲区会涨到 2 秒上限。

用法：python _tests/_t_mic_live.py [秒数]
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import sr_roulette as sr

SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
FAILS: list[str] = []


def check(ok: bool, title: str, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + title + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(title)


class FakeBank:
    """只提供 AudioEngine 要用的两个方法。"""

    def __len__(self) -> int:
        return 0

    def path_at(self, idx: int):
        return None

    def setting_at(self, idx: int):
        return None

    def index_of_name(self, name: str) -> int:
        return -1


app = QApplication([])

print("== 可用设备 ==")
for d in sr.real_inputs():
    print("   麦克风候选:", d.description())
for d in sr.virtual_outputs():
    print("   虚拟输出候选:", d.description())
print()

cfg = dict(sr.DEFAULT_CONFIG)
cfg["mic_enabled"] = True
cfg["monitor_enabled"] = True
cfg["mic_device"] = ""            # 让程序自己挑
cfg["cable_device"] = ""          # 让程序自己挑
cfg["mic_latency_ms"] = 60

engine = sr.AudioEngine(FakeBank(), cfg)
engine.start()

state: dict = {"t": time.monotonic(), "levels": []}
timer = QTimer()


def sample() -> None:
    state["levels"].append(engine.mic_level())


timer.timeout.connect(sample)
timer.start(50)

QTimer.singleShot(int(SECONDS * 1000), app.quit)
app.exec()

print("\n== 运行结果 ==")
st = engine.audio_status()
print(f"   采集设备 : {st['mic'] or '（无）'}")
print(f"   虚拟声卡 : {st['cable'] or '（无）'}")
print(f"   错误信息 : {st['error'] or '无'}")
cap = engine.capture
print(f"   采集帧数 : {cap.consumed if cap else 0:,}")
print(f"   掉帧/补零: {st['dropped']} / {st['underruns']}")
buf = len(cap._buf) if cap else -1      # noqa: SLF001
print(f"   剩余缓冲 : {buf} 帧（{buf / 48000 * 1000:.0f}ms）")
print(f"   电平采样 : min={min(state['levels'] or [0]):.3f} max={max(state['levels'] or [0]):.3f}")
print()

check(st["mic"] != "", "采集设备打开了", st["mic"])
check(st["cable"] != "", "虚拟声卡输出打开了", st["cable"])
check(engine.cable is not None, "虚拟声卡那一路混音器存在")
check(engine.cable is not None and engine.cable.mic is not None,
      "麦克风接进了虚拟声卡那一路")
check(engine._sink is not None, "耳机那一路也在跑")          # noqa: SLF001

if cap is not None:
    want = int(SECONDS * 48000 * 0.6)     # 只要求达到理论值的 60%，给启动留余量
    check(cap.consumed > want, "采集数据真的被消费掉了（链路在流动）",
          f"{cap.consumed:,} 帧 > {want:,}")
    check(len(cap._buf) < 48000, "缓冲区没有积压", f"{len(cap._buf)} 帧")
    rate = st["underruns"] / max(1.0, SECONDS)
    check(rate < 200, "补零次数没有爆表（延迟够用）", f"{st['underruns']} 次/{SECONDS:.0f}s")

engine.stop_outputs()
print()
if FAILS:
    print(f"FAILED {len(FAILS)}:")
    for f in FAILS:
        print("   -", f)
    sys.exit(1)
print("ALL PASS")
