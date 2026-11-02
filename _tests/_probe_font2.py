import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase, QImage, QPainter, QColor
app = QApplication.instance() or QApplication([])
for path in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf"):
    fid = QFontDatabase.addApplicationFont(path)
    fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
    print(path, "-> id", fid, fams[:3])
print("全部族:", QFontDatabase.families()[:8])
img = QImage(520, 90, QImage.Format_RGB32)
img.fill(QColor("#12141a"))
p = QPainter(img)
p.setPen(QColor("#ffffff"))
p.setFont(QFont("Microsoft YaHei", 26))
p.drawText(img.rect(), 0x1284, "音效轮盘 中文测试 ABC")
p.end()
img.save("_tests/_font_probe2.png")
