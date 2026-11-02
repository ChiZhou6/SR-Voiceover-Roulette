"""生成 5 个测试用 wav 音效，放进 sounds/ 目录。

只是为了验证轮盘能出声，正式用的时候把它们删掉换成真正的音效素材。
"""

import math
import struct
import wave
from pathlib import Path

SOUNDS = Path(__file__).resolve().parent / "sounds"
RATE = 44100
DUR = 0.45

# (文件名, 频率Hz, 说明)
TONES = [
    ("01_do.wav", 523.25),
    ("02_re.wav", 587.33),
    ("03_mi.wav", 659.25),
    ("04_fa.wav", 698.46),
    ("05_sol.wav", 783.99),
]


def make_wav(path: Path, freq: float) -> None:
    n = int(RATE * DUR)
    frames = bytearray()
    for i in range(n):
        t = i / RATE
        # 淡入淡出，避免爆音
        env = min(1.0, i / (RATE * 0.01), (n - i) / (RATE * 0.06))
        # 基频 + 一点二次谐波，听起来更像"音效"而不是纯测试音
        val = math.sin(2 * math.pi * freq * t) * 0.7
        val += math.sin(2 * math.pi * freq * 2 * t) * 0.18
        sample = int(max(-1.0, min(1.0, val * env)) * 30000)
        frames += struct.pack("<h", sample)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(bytes(frames))


def main() -> int:
    SOUNDS.mkdir(parents=True, exist_ok=True)
    for name, freq in TONES:
        path = SOUNDS / name
        make_wav(path, freq)
        print(f"  生成 {name}  ({freq:.2f} Hz, {DUR}s, {path.stat().st_size} bytes)")
    print(f"\n完成，共 {len(TONES)} 个测试音效 -> {SOUNDS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
