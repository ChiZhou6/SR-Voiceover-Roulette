"""离屏渲染三种提示条，确认观感和文字没溢出。

跑法：python _shot_hint_toast.py
输出：_tests/_shot_hint_*.png
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402

app = QApplication.instance() or QApplication([])
# 字体必须在 QApplication 之后加载，否则 offscreen 平台下会段错误
from PySide6.QtGui import QFontDatabase  # noqa: E402
QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
cfg = dict(sr.DEFAULT_CONFIG)

cases = [
    ("info", "已切换到「默认轮盘」"),
    ("info", "已就绪，长按 Y 打开轮盘（14 个音效）"),
    ("warn", "音频：麦克风和虚拟声卡都没有起来，请检查设备"),
    ("error", "鼠标原始输入注册失败，轮盘将无法选择音效（详情见日志）"),
]

out_dir = Path(__file__).resolve().parent
for i, (level, text) in enumerate(cases):
    t = sr.HintToast(cfg)
    t.show_hint(text, level)
    app.processEvents()
    # 停住那一段（不透明、无缩放）才好目检
    t.t = 0.5
    t.update()
    app.processEvents()
    p = out_dir / f"_shot_hint_{i}_{level}.png"
    t.grab().save(str(p))
    print(f"saved {p.name}  size={t.width()}x{t.height()}")
    t.hide()

print("done")
