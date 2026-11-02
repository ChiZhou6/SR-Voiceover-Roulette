"""把必剪导出的 mp4 音效转成程序能直接用的 wav，并挂到轮盘上。

用法：
  python _tests/import_clips.py <源目录> <目标 sounds 目录> [更多目标...]

每个目标目录如果有 sounds.json，就把新文件名追加到 order 末尾
（已经存在的不会重复加，已有音效的顺序和参数一律不动）。

输出规格与库内现有一致：48kHz / 立体声 / 16bit PCM。
不归一化、不裁切，保留用户剪好的原始长度与音量；只做两件事：
  · 扣直流偏移（播放时听感不发闷）
  · 峰值超过 1.0 时压回满刻度（避免削波）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402

SRC_EXTS = (".mp4", ".mov", ".m4a", ".wav", ".mp3", ".flac", ".ogg")


def write_wav(path: Path, data: np.ndarray, sr_hz: int) -> None:
    import struct

    pcm = np.clip(data, -1.0, 1.0)
    ints = (pcm * 32767.0).astype("<i2")
    raw = ints.tobytes()
    ch = data.shape[1]
    header = b"RIFF" + struct.pack("<I", 36 + len(raw)) + b"WAVE"
    header += b"fmt " + struct.pack(
        "<IHHIIHH", 16, 1, ch, sr_hz, sr_hz * ch * 2, ch * 2, 16
    )
    header += b"data" + struct.pack("<I", len(raw))
    path.write_bytes(header + raw)


def add_to_order(json_path: Path, names: list[str]) -> bool:
    if not json_path.exists():
        return False
    data = json.loads(json_path.read_text(encoding="utf-8"))
    order = list(data.get("order") or [])
    for name in names:
        if name not in order:
            order.append(name)
    data["order"] = order
    data.setdefault("version", 1)
    data.setdefault("items", {})
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return True


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1

    src_dir = Path(sys.argv[1])
    dests = [Path(p) for p in sys.argv[2:]]
    if not src_dir.is_dir():
        print(f"源目录不存在：{src_dir}")
        return 1

    srcs = sorted(
        (p for p in src_dir.iterdir() if p.suffix.lower() in SRC_EXTS),
        key=lambda p: p.stat().st_mtime,
    )
    if not srcs:
        print(f"{src_dir} 里没有音频/视频文件")
        return 1

    _app = QApplication.instance() or QApplication(sys.argv[:1])
    fmt = sr._target_format()

    made: list[str] = []
    print(f"源目录：{src_dir}（{len(srcs)} 个文件）\n")
    for src in srcs:
        clip = sr.decode_clip(src, fmt, 0.0)   # 不裁切、不加淡入淡出
        if clip is None:
            print(f"  [XX] {src.name}: 解不出音频（可能没有音轨）")
            continue
        peak = float(np.abs(clip).max())
        clip = np.clip(clip, -1.0, 1.0)
        name = src.stem + ".wav"
        for dest in dests:
            dest.mkdir(parents=True, exist_ok=True)
            write_wav(dest / name, clip, fmt.sampleRate())
        made.append(name)
        flag = "  ← 峰值超了，已压回满刻度" if peak > 1.0 else ""
        print(f"  [OK] {src.name} → {name}  "
              f"{len(clip) / fmt.sampleRate():.2f}s  峰值 {peak:.2f}{flag}")

    if made:
        print()
        for dest in dests:
            # sounds.json 在程序根目录（和 exe 同级），不在 sounds 目录里面
            json_path = (dest.parent if dest.name.lower() == "sounds" else dest) / "sounds.json"
            if add_to_order(json_path, made):
                print(f"  已挂到轮盘：{json_path}")
            else:
                print(f"  [XX] 找不到 {json_path}，只拷贝了文件，没挂上轮盘")

    print(f"\n共导入 {len(made)} 个")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
