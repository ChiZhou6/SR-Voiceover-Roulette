"""探针：验证 QAudioDecoder 能否把音效解码成指定格式的 float32 波形。

问题 2 的修法依赖"启动时把音效全部解成 PCM 存内存"。
需要确认三件事：
  1. 能不能指定输出格式（统一成 48k / 2ch / float32），省掉运行时重采样
  2. 拿到的字节能不能转成 numpy 数组
  3. 文件开头 / 结尾的采样值是不是非零（这直接决定有没有"咔"声）
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtMultimedia import (
    QAudioFormat,
    QAudioDecoder,
    QMediaDevices,
)
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
SOUNDS = ROOT / "sounds"


def target_format() -> QAudioFormat:
    dev = QMediaDevices.defaultAudioOutput()
    fmt = dev.preferredFormat()
    fmt.setSampleFormat(QAudioFormat.Float)
    fmt.setChannelCount(2)
    fmt.setSampleRate(48000)
    return fmt


def decode(path: Path, fmt: QAudioFormat, timeout_ms: int = 8000):
    dec = QAudioDecoder()
    dec.setAudioFormat(fmt)
    chunks: list[np.ndarray] = []
    errors: list[str] = []

    def on_buffer() -> None:
        buf = dec.read()
        if not buf.isValid():
            return
        bfmt = buf.format()
        mv = buf.constData()
        raw = bytes(mv)
        arr = np.frombuffer(raw, dtype="<f4")
        if bfmt.channelCount() == 2:
            arr = arr.reshape(-1, 2)
        else:
            arr = np.repeat(arr.reshape(-1, 1), 2, axis=1)
        chunks.append(arr.copy())

    dec.bufferReady.connect(on_buffer)
    dec.error.connect(lambda: errors.append(dec.errorString()))

    loop = QEventLoop()
    dec.finished.connect(loop.quit)
    dec.error.connect(loop.quit)
    QTimer.singleShot(timeout_ms, loop.quit)

    dec.setSource(QUrl.fromLocalFile(str(path)))
    dec.start()
    loop.exec()
    dec.stop()

    if not chunks:
        return None, errors, fmt
    return np.concatenate(chunks, axis=0), errors, dec.audioFormat()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841  QAudioDecoder 需要事件循环
    files = sorted(p for p in SOUNDS.glob("*") if p.suffix.lower() in (".wav", ".mp3", ".ogg", ".flac"))
    print(f"sounds 目录: {SOUNDS}  找到 {len(files)} 个文件")
    if not files:
        return 1

    tgt = target_format()
    print(f"目标格式: {tgt.sampleRate()}Hz {tgt.channelCount()}ch {tgt.sampleFormat()}\n")

    ok = 0
    for p in files:
        arr, errs, got = decode(p, tgt)
        if arr is None:
            print(f"[失败] {p.name}  errors={errs}")
            continue
        ok += 1
        dur = len(arr) / max(1, got.sampleRate())
        head = float(np.abs(arr[:64]).max()) if len(arr) else 0.0
        tail = float(np.abs(arr[-64:]).max()) if len(arr) else 0.0
        peak = float(np.abs(arr).max())
        dc = float(arr.mean())
        print(f"[OK] {p.name:22s} 形状={arr.shape} {dur:.2f}s "
              f"实际={got.sampleRate()}Hz/{got.channelCount()}ch/{got.sampleFormat().name}")
        print(f"     峰值={peak:.3f} 开头64样本={head:.4f} 结尾64样本={tail:.4f} 直流={dc:+.5f}")

    print(f"\n解码成功 {ok}/{len(files)}")
    return 0 if ok == len(files) else 2


if __name__ == "__main__":
    raise SystemExit(main())
