"""把整段音效合集解码成 PCM，按静音间隔切出候选片段。

我无法试听，只能靠能量包络判断"哪里断开"，
再配合转写文本对号入座。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PySide6.QtCore import QEventLoop, QTimer, QUrl  # noqa: E402
from PySide6.QtMultimedia import QAudioFormat, QAudioDecoder  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def decode(path: Path, app) -> tuple[np.ndarray, int]:
    fmt = QAudioFormat()
    fmt.setSampleRate(16000)
    fmt.setChannelCount(1)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)

    dec = QAudioDecoder()
    dec.setAudioFormat(fmt)
    dec.setSource(QUrl.fromLocalFile(str(path)))

    chunks: list[np.ndarray] = []
    state = {"done": False, "err": ""}

    def on_buf():
        b = dec.read()
        if b.isValid():
            arr = np.frombuffer(b.constData(), dtype=np.float32).copy()
            chunks.append(arr)

    loop = QEventLoop()

    def finish(ok: bool, msg: str = "") -> None:
        state["done"] = True
        state["err"] = msg
        loop.quit()

    dec.bufferReady.connect(on_buf)
    dec.finished.connect(lambda: finish(True))
    dec.error.connect(lambda: finish(False, dec.errorString()))
    QTimer.singleShot(30000, lambda: finish(False, "解码超时"))
    dec.start()
    loop.exec()

    if not state["done"] or state["err"]:
        raise RuntimeError(state["err"] or "解码失败")
    if not chunks:
        raise RuntimeError("没有解出任何音频")
    return np.concatenate(chunks), 16000


def segments(pcm: np.ndarray, sr: int, thresh_db: float = -32.0,
             min_gap_ms: int = 120, min_len_ms: int = 120) -> list[tuple[int, int]]:
    """返回 [(起始ms, 结束ms)]，按静音间隔切分。"""
    win = int(sr * 0.02)  # 20ms 一帧
    n = len(pcm) // win
    if n == 0:
        return []
    frames = pcm[: n * win].reshape(n, win)
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-12)
    active = db > thresh_db

    out: list[tuple[int, int]] = []
    start = None
    gap = 0
    for i, a in enumerate(active):
        t = int(i * win / sr * 1000)
        if a:
            if start is None:
                start = t
            gap = 0
        else:
            if start is not None:
                gap += win
                if gap >= int(sr * min_gap_ms / 1000):
                    end = t
                    if end - start >= min_len_ms:
                        out.append((start, end))
                    start = None
                    gap = 0
    if start is not None:
        end = int(len(pcm) / sr * 1000)
        if end - start >= min_len_ms:
            out.append((start, end))
    return out


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841
    files = sorted(Path(ROOT / "_tmp_audio").glob("*.m4a"))
    if not files:
        print("_tmp_audio 里没有 m4a")
        return 1

    for f in files:
        print(f"\n{'=' * 60}\n{f.name}")
        try:
            pcm, sr = decode(f, app)
        except Exception as exc:
            print(f"  解码失败: {exc}")
            continue
        dur = len(pcm) / sr
        peak = float(np.abs(pcm).max())
        print(f"  时长 {dur:.1f}s  峰值 {peak:.3f}  采样点 {len(pcm)}")
        segs = segments(pcm, sr)
        print(f"  切出 {len(segs)} 段（静音阈值 -32dB，最短 120ms）")
        for i, (a, b) in enumerate(segs[:60]):
            sub = pcm[int(a * sr / 1000): int(b * sr / 1000)]
            lvl = float(np.abs(sub).max()) if len(sub) else 0.0
            print(f"    #{i:02d} {a/1000:6.2f}s - {b/1000:6.2f}s  ({(b-a)/1000:.2f}s)  峰值 {lvl:.2f}")
        if len(segs) > 60:
            print(f"    ... 还有 {len(segs) - 60} 段")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
