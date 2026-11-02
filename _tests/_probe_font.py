import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase, QImage, QPainter, QColor
app = QApplication.instance() or QApplication([])
fams = QFontDatabase.families()
print("字体族数:", len(fams))
print("含中文族:", [f for f in fams if any(k in f for k in ("YaHei", "雅黑", "SimSun", "宋", "Deng", "Hei"))][:8])
img = QImage(320, 80, QImage.Format_RGB32)
img.fill(QColor("#12141a"))
p = QPainter(img)
p.setPen(QColor("#ffffff"))
p.setFont(QFont("Microsoft YaHei", 22))
p.drawText(img.rect(), 0x1284, "音效轮盘测试中文")
p.end()
# 统计非背景像素，肉眼判断是否方块
img.save("_tests/_font_probe.png")
bg = QColor("#12141a").rgb()
px = sum(1 for y in range(80) for x in range(320)
         if img.pixel(x, y) != bg)
print("有字像素数:", px)
