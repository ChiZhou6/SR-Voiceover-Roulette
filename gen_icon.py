"""生成程序图标 icon.ico（多尺寸），供 exe 使用。

图形与托盘图标一致：特征色圆环 + 深色内圆 + 播放三角。
颜色取自 theme.py，与轮盘界面共用同一份来源。
ICO 直接内嵌 PNG 数据（Vista 以后都支持），避免依赖 BMP 转换。
"""

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QColor, QPainter, QPen, QPixmap  # noqa: E402
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from theme import accent, accent_light  # noqa: E402

SIZES = [16, 24, 32, 48, 64, 128, 256]


def render(size: int) -> bytes:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    pad = size * 0.09
    ring_w = max(1.5, size * 0.10)
    p.setBrush(accent(255))
    p.setPen(QPen(accent_light(255), ring_w))
    p.drawEllipse(QRectF(pad, pad, size - pad * 2, size - pad * 2))

    inner = size * 0.34
    p.setBrush(QColor(20, 22, 28, 255))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QRectF(size / 2 - inner / 2, size / 2 - inner / 2, inner, inner))

    # 内部一个小三角，暗示"播放"
    p.setBrush(accent_light(255))
    tri_w = inner * 0.42
    tri_h = inner * 0.5
    cx, cy = size / 2, size / 2
    from PySide6.QtGui import QPolygonF
    from PySide6.QtCore import QPointF

    poly = QPolygonF([
        QPointF(cx - tri_w * 0.45, cy - tri_h / 2),
        QPointF(cx - tri_w * 0.45, cy + tri_h / 2),
        QPointF(cx + tri_w * 0.55, cy),
    ])
    p.drawPolygon(poly)
    p.end()

    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    pm.save(buf, "PNG")
    buf.close()
    return bytes(ba.data())


def build_ico(path: Path) -> None:
    blobs = [(s, render(s)) for s in SIZES]
    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries = b""
    for size, data in blobs:
        dim = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset
        )
        offset += len(data)
    path.write_bytes(header + entries + b"".join(d for _, d in blobs))


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841
    out = ROOT / "icon.ico"
    build_ico(out)
    print(f"已生成 {out}  ({out.stat().st_size} bytes, {len(SIZES)} 个尺寸)")

    # 顺便存一张大图给人看
    pm = QPixmap(256, 256)
    pm.loadFromData(render(256), "PNG")
    pm.save(str(ROOT / "icon_preview.png"))
    print(f"已生成 {ROOT / 'icon_preview.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
