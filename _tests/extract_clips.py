"""从下载的视频音轨里切出指定时间段，导出成程序能直接用的 wav。

用法：
  python _tests/extract_clips.py <源文件> <名称>=<起> - <止> [更多...]
  时间单位秒，可写小数

例：
  python _tests/extract_clips.py _tmp_audio/x.m4a 冰冰冰=0.30-1.45

输出到 _tmp_audio/clips/<名称>.wav，48kHz 立体声，
首尾加 5ms 淡入淡出、峰值归一化到 -1.5 dBFS，避免起播咔哒声。
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "_tests"))

import numpy as np  # noqa: E402
from PySide6.QtCore import QEventLoop, QTimer, QUrl  # noqa: E402
from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

TARGET_SR = 48000
TARGET_CH = 2
FADE_MS = 5.0
PEAK_DBFS = -1.5


def decode(path: Path) -> tuple[np.ndarray, int]:
    """解码成 int16 交织多声道。QAudioDecoder 只按源格式解，重采样自己做。"""
    fmt = QAudioFormat()
    fmt.setSampleRate(TARGET_SR)
    fmt.setChannelCount(TARGET_CH)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)

    dec = QAudioDecoder()
    dec.setAudioFormat(fmt)
    dec.setSource(QUrl.fromLocalFile(str(path)))

    chunks: list[np.ndarray] = []
    err = {"msg": ""}
    loop = QEventLoop()

    def on_buf() -> None:
        b = dec.read()
        if b.isValid():
            chunks.append(np.frombuffer(b.constData(), dtype=np.float32).copy())

    dec.bufferReady.connect(on_buf)
    dec.finished.connect(loop.quit)
    dec.error.connect(lambda: (err.__setitem__("msg", dec.errorString()), loop.quit()))
    QTimer.singleShot(60000, loop.quit)
    dec.start()
    loop.exec()

    if err["msg"]:
        raise RuntimeError(err["msg"])
    if not chunks:
        raise RuntimeError("没有解出音频")
    pcm = np.concatenate(chunks)
    usable = len(pcm) - len(pcm) % TARGET_CH
    return pcm[:usable].reshape(-1, TARGET_CH), TARGET_SR


def write_wav(path: Path, data: np.ndarray, sr: int) -> None:
    import struct

    pcm = np.clip(data, -1.0, 1.0)
    ints = (pcm * 32767.0).astype("<i2")
    raw = ints.tobytes()
    ch = data.shape[1]
    byte_rate = sr * ch * 2
    header = b"RIFF" + struct.pack("<I", 36 + len(raw)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, ch, sr, byte_rate, ch * 2, 16)
    header += b"data" + struct.pack("<I", len(raw))
    path.write_bytes(header + raw)


def make_clip(src: np.ndarray, sr: int, start: float, end: float) -> np.ndarray:
    a = max(0, int(start * sr))
    b = min(len(src), int(end * sr))
    clip = src[a:b].astype(np.float64).copy()
    if len(clip) == 0:
        raise ValueError(f"时间段 {start}-{end}s 超出音频范围")

    fade = max(1, int(sr * FADE_MS / 1000))
    if len(clip) > fade * 2:
        clip[:fade] *= np.linspace(0.0, 1.0, fade)[:, None]
        clip[-fade:] *= np.linspace(1.0, 0.0, fade)[:, None]

    peak = float(np.abs(clip).max())
    if peak > 1e-6:
        clip *= (10 ** (PEAK_DBFS / 20)) / peak
    return clip


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1

    src_path = Path(sys.argv[1])
    if not src_path.is_absolute():
        src_path = (Path.cwd() / src_path).resolve()

    app = QApplication(sys.argv[:1])  # noqa: F841
    print(f"解码 {src_path.name} ...")
    src, sr = decode(src_path)
    print(f"  {len(src)/sr:.2f}s  {src.shape[1]}ch  {sr}Hz")

    out_dir = ROOT / "_tmp_audio" / "clips"
    out_dir.mkdir(parents=True, exist_ok=True)

    ok = 0
    for spec in sys.argv[2:]:
        m = re.match(r"^(.+?)=([\d.]+)\s*-\s*([\d.]+)$", spec)
        if not m:
            print(f"  跳过（格式不对）: {spec}")
            continue
        name, s, e = m.group(1), float(m.group(2)), float(m.group(3))
        try:
            clip = make_clip(src, sr, s, e)
        except ValueError as exc:
            print(f"  {name}: {exc}")
            continue
        dst = out_dir / f"{name}.wav"
        write_wav(dst, clip, sr)
        print(f"  [OK] {name}: {s:.2f}-{e:.2f}s -> {dst.name} "
              f"({len(clip)/sr:.2f}s, {dst.stat().st_size // 1024}KB)")
        ok += 1

    print(f"\n共导出 {ok} 个到 {out_dir}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
