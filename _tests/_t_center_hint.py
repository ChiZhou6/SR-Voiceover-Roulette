"""回归：拖音效到轮盘中心时的提示文案与高亮。

跑法：python _t_center_hint.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QMimeData, QPoint, Qt  # noqa: E402
from PySide6.QtGui import QDragEnterEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="sr_center_"))
(TMP / "sounds").mkdir()
for name in ("冰冰冰.wav",):
    src = ROOT / "sounds" / name
    if src.exists():
        shutil.copy2(src, TMP / "sounds" / name)
sr.SOUNDS_DIR = TMP / "sounds"
sr.SOUNDS_CONFIG_PATH = TMP / "sounds.json"
sr.CONFIG_PATH = TMP / "config.json"
shutil.copy2(ROOT / "config.json", sr.CONFIG_PATH)

from settings_window import (  # noqa: E402
    ADD_TO_END,
    MIME_LIB,
    MIME_SLOT,
    SettingsWindow,
)

app = QApplication.instance() or QApplication([])

OK = []
BAD = []


def check(cond, name, detail=""):
    if cond:
        OK.append(name)
        print(f"PASS  {name}")
    else:
        BAD.append(name)
        print(f"FAIL  {name}   {detail}")
    return bool(cond)


cfg = sr.load_config()
scfg = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
scfg.load()
bank = sr.SoundBank(int(cfg["slots"]), scfg)
win = SettingsWindow(cfg, scfg, bank)
win.setAttribute(Qt.WA_DontShowOnScreen, True)
win.show()
app.processEvents()

preview = win.preview
print(f"轮盘音效数 = {preview.count()}")

print()
print("=== A. 一抓起音效就亮（不看鼠标在哪）===")
check(preview.center_hint == "", "没在拖的时候不显示提示", repr(preview.center_hint))

preview.begin_lib_drag()
check(
    preview.center_hint == "拖到此处添加音效",
    "刚抓起音效、鼠标还在音效库上 -> 中心已经提示",
    repr(preview.center_hint),
)
check(
    preview.center_sub_hint == "",
    "还没到中心时不写「追加到末尾」（那时松手是放进这一格）",
    repr(preview.center_sub_hint),
)

preview.drop_target = 0          # 鼠标停在某个扇区上，没到中心
check(
    preview.center_hint == "拖到此处添加音效",
    "鼠标停在扇区上 -> 中心仍然提示",
    repr(preview.center_hint),
)

preview.drop_target = ADD_TO_END
check(
    preview.center_sub_hint == "松手追加到末尾",
    "到了中心才说追加",
    repr(preview.center_sub_hint),
)

# 关键：鼠标退出轮盘范围（比如拖回左边的库）不能把灯熄了
preview.drop_target = None
preview.dragLeaveEvent(None)
check(
    preview.center_hint == "拖到此处添加音效",
    "鼠标移出轮盘范围 -> 中心还亮着（拖拽没结束）",
    repr(preview.center_hint),
)

preview._drag_from_lib = False
check(
    preview.center_hint == "",
    "轮盘内拖动不提示（中心不接受那种拖法）",
    repr(preview.center_hint),
)
preview._drag_from_lib = True

preview.end_lib_drag()
check(preview.center_hint == "", "松手 / 取消后提示消失", repr(preview.center_hint))

print()
print("=== A1. 音效库的拖拽信号真的连到了预览 ===")
win.page_lib.drag_began.emit()
check(
    preview.center_hint == "拖到此处添加音效",
    "音效库发出「开始拖」-> 预览中心亮起",
    repr(preview.center_hint),
)
win.page_lib.drag_ended.emit()
check(
    preview.center_hint == "",
    "音效库发出「拖完」-> 预览中心熄灭",
    repr(preview.center_hint),
)

print()
print("=== A2. 中心只接受从音效库拖来的 ===")
cx, cy = preview._center()
center_pos = QPoint(int(cx), int(cy))
check(
    preview._target_at(center_pos, True) == ADD_TO_END,
    "从音效库拖到中心 -> 接受（追加到末尾）",
    str(preview._target_at(center_pos, True)),
)
check(
    preview._target_at(center_pos, False) is None,
    "轮盘内拖到中心 -> 明确不接受（不给假提示）",
    str(preview._target_at(center_pos, False)),
)

print()
print("=== B. 拖拽来源识别 ===")
preview.drop_target = None

mime_lib = QMimeData()
mime_lib.setData(MIME_LIB, "冰冰冰.wav".encode("utf-8"))
mime_lib.setText("冰冰冰.wav")
ev = QDragEnterEvent(QPoint(50, 50), Qt.CopyAction, mime_lib, Qt.LeftButton, Qt.NoModifier)
preview.dragEnterEvent(ev)
check(preview._drag_from_lib is True, "带音效库标记 -> 认成从库拖", str(preview._drag_from_lib))

mime_slot = QMimeData()
mime_slot.setData(MIME_SLOT, b"3")
mime_slot.setText("冰冰冰.wav")
ev2 = QDragEnterEvent(QPoint(50, 50), Qt.MoveAction, mime_slot, Qt.LeftButton, Qt.NoModifier)
preview.dragEnterEvent(ev2)
check(preview._drag_from_lib is False, "带槽位标记 -> 认成轮盘内拖动", str(preview._drag_from_lib))

mime_bad = QMimeData()
mime_bad.setText("随便什么东西")
ev3 = QDragEnterEvent(QPoint(50, 50), Qt.CopyAction, mime_bad, Qt.LeftButton, Qt.NoModifier)
before = preview._drag_from_lib
preview.dragEnterEvent(ev3)
check(preview._drag_from_lib == before, "无关内容不改变来源标记", str(preview._drag_from_lib))

print()
print("=== C. 高亮不会画崩 ===")
cx, cy = preview._center()
geo, _ = preview.ring_geometry()
# 模拟"正拖着东西停在中心"
preview.begin_lib_drag()
preview.drop_target = ADD_TO_END
preview.update()
app.processEvents()
pm = preview.grab()
check(not pm.isNull() and pm.width() > 0, "中心高亮能正常渲染", f"{pm.width()}x{pm.height()}")
check(geo["hole"] > 0, "中心圆半径有效", str(geo["hole"]))

# 停在扇区上时中心也应该亮着（只是暗一点）
preview.drop_target = 0
preview.update()
app.processEvents()
pm_mid = preview.grab()
check(not pm_mid.isNull(), "还没到中心时也能渲染中心提示",
      f"{pm_mid.width()}x{pm_mid.height()}")

# 停下来之后不该留残影
preview.drop_target = None
preview.end_lib_drag()
app.processEvents()
pm2 = preview.grab()
check(not pm2.isNull(), "清掉拖放状态后能重绘", f"{pm2.width()}x{pm2.height()}")
check(preview.center_hint == "", "状态清掉后提示也消失", repr(preview.center_hint))

print()
print("=== D. 真的从格子上按住拖，预览就会亮 ===")

import settings_window as sw  # noqa: E402
from PySide6.QtCore import QEvent, QPointF  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402

during = []


class _FakeDrag:
    """替掉 QDrag：不真的阻塞拖拽，但保持同样的调用顺序。"""

    count = 0

    def __init__(self, parent):
        self.parent = parent
        _FakeDrag.count += 1

    def setMimeData(self, md):
        self.md = md

    def setPixmap(self, pm):
        self.pixmap = pm

    def exec(self, action):
        # 拖拽"进行中"读一次：这一刻中心必须已经亮着了
        during.append(preview.center_hint)
        return action


real_qdrag = sw.QDrag
sw.QDrag = _FakeDrag
try:
    cells = win.page_lib.findChildren(sw._SoundCell)
    check(bool(cells), "音效库里至少有一个可拖的格子", str(len(cells)))
    cell = cells[0]
    cell._press = QPoint(10, 10)
    mv = QMouseEvent(
        QEvent.MouseMove,
        QPointF(40, 40),
        QPointF(cell.mapToGlobal(QPoint(40, 40))),
        Qt.NoButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    cell.mouseMoveEvent(mv)
finally:
    sw.QDrag = real_qdrag

check(
    bool(during) and during[0] == "拖到此处添加音效",
    "按住格子拖动 -> 进 exec 那一刻中心已亮",
    repr(during),
)
check(_FakeDrag.count == 1, "确实发起了一次拖拽", str(_FakeDrag.count))
check(preview.center_hint == "", "exec 返回后中心熄灭", repr(preview.center_hint))

win.hide()
shutil.rmtree(TMP, ignore_errors=True)

print()
print("=" * 56)
if BAD:
    print(f"结果：{len(BAD)} 项失败 / 共 {len(OK) + len(BAD)} 项")
    for n in BAD:
        print("  FAIL", n)
    raise SystemExit(1)
print(f"结果：全部通过（{len(OK)} 项）")
