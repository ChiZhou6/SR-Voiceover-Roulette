import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PySide6.QtGui import QImage, QColor
img = QImage(str(ROOT / "_tests" / "_shot_combo_v072.png"))
print("img", img.width(), img.height())
# 找绿色条：逐行找 accent 色的水平连续段
for y in range(520, 610):
    runs = []
    start = None
    for x in range(img.width()):
        c = img.pixelColor(x, y)
        green = c.green() > 120 and c.green() > c.red() + 40 and c.green() > c.blue() + 40
        if green and start is None:
            start = x
        elif not green and start is not None:
            if x - start > 3:
                runs.append((start, x - start))
            start = None
    if start is not None:
        runs.append((start, img.width() - start))
    if runs:
        print(y, runs)
