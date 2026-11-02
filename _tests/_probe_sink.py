"""探针：验证「单一常驻 QAudioSink + 自绘 QIODevice 拉流」是否可用。

这是问题 2 的修法核心：整个程序只开一个音频输出，程序自己往里喂波形。
好处是设备只初始化一次，再也不会有"每次播放都重新开会话"的爆音。
"""

from __future__ import annotations

import sys

import numpy as np
from PySide6.QtCore import QIODevice, QTimer
from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSink, QMediaDevices
from PySide6.QtWidgets import QApplication

RATE = 48000
CH = 2


class Mixer(QIODevice):
    """拉模式：QAudioSink 需要数据时调 readData，我们自己现算波形。"""

    def __init__(self) -> None:
        super().__init__()
        self.frames_written = 0
        self.read_calls = 0
        self._phase = 0.0

    def readData(self, maxlen: int):  # noqa: N802
        self.read_calls += 1
        frames = max(1, maxlen // (CH * 4))
        t = (np.arange(frames) + self._phase) / RATE
        # 220Hz 正弦，幅度 0.2
        mono = (0.2 * np.sin(2 * np.pi * 220.0 * t)).astype("<f4")
        buf = np.column_stack([mono, mono])
        self._phase += frames
        self.frames_written += frames
        return buf.tobytes()

    def writeData(self, data) -> int:  # noqa: N802
        return 0

    def bytesAvailable(self) -> int:  # noqa: N802
        return (1 << 20) + super().bytesAvailable()


def main() -> int:
    app = QApplication(sys.argv)

    dev = QMediaDevices.defaultAudioOutput()
    fmt = QAudioFormat()
    fmt.setSampleRate(RATE)
    fmt.setChannelCount(CH)
    fmt.setSampleFormat(QAudioFormat.Float)

    supported = dev.isFormatSupported(fmt)
    print(f"设备: {dev.description()}")
    print(f"48k/2ch/Float 是否原生支持: {supported}")
    if not supported:
        fmt = dev.preferredFormat()
        print(f"  退回设备首选格式: {fmt.sampleRate()}Hz/{fmt.channelCount()}ch/{fmt.sampleFormat().name}")

    mixer = Mixer()
    mixer.open(QIODevice.ReadOnly)

    sink = QAudioSink(dev, fmt)
    sink.setBufferSize(int(RATE * 0.06) * CH * 4)  # 目标 60ms，越小越跟手
    print(f"sink 缓冲大小: {sink.bufferSize()} 字节 "
          f"（{sink.bufferSize() / (RATE * CH * 4) * 1000:.0f}ms）")

    sink.start(mixer)
    print("sink 已启动，播放 0.8 秒…")

    QTimer.singleShot(800, app.quit)
    app.exec()

    err = sink.error()
    print(f"\nreadData 调用次数: {mixer.read_calls}")
    print(f"已生成帧数: {mixer.frames_written}（理论 0.8s 约 {int(0.8 * RATE)} 帧）")
    print(f"sink 状态: {sink.state()}  错误: {err}")

    sink.stop()
    mixer.close()

    ok = mixer.read_calls > 0 and mixer.frames_written > 0 and err == QAudio.Error.NoError
    print("结论:", "拉流管线可用" if ok else "拉流未跑起来")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
