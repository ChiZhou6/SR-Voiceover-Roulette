"""回归：v0.9.2 设置窗口可缩放 + 记住大小。

跑法：python _t_winresize.py
"""

import ctypes
import ctypes.wintypes
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="sr_win_"))
(TMP / "sounds").mkdir()
shutil.copy2(ROOT / "sounds" / "冰冰冰.wav", TMP / "sounds" / "冰冰冰.wav")
sr.SOUNDS_DIR = TMP / "sounds"
sr.SOUNDS_CONFIG_PATH = TMP / "sounds.json"
sr.CONFIG_PATH = TMP / "config.json"
shutil.copy2(ROOT / "config.json", sr.CONFIG_PATH)

from settings_window import SettingsWindow  # noqa: E402
from settings_window import _RESIZE_BORDER as _RB  # noqa: E402

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


def make_window():
    cfg = sr.load_config()
    scfg = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
    scfg.load()
    bank = sr.SoundBank(int(cfg["slots"]), scfg)
    w = SettingsWindow(cfg, scfg, bank)
    # 走真实平台（离屏平台的虚拟屏幕只有 800x800，会把尺寸全部夹到最小值），
    # 但别真的弹到桌面上
    w.setAttribute(Qt.WA_DontShowOnScreen, True)
    w.show()
    app.processEvents()
    return w


def hit_test(w, x, y):
    """真的拼一条 WM_NCHITTEST 消息喂给 nativeEvent，看它回哪个区域码。"""
    g = w.geometry()
    dpr = w.devicePixelRatioF() or 1.0
    msg = ctypes.wintypes.MSG()
    msg.hwnd = int(w.winId())
    msg.message = 0x0084
    msg.wParam = 0
    msg.lParam = ((int(y * dpr) & 0xFFFF) << 16) | (int(x * dpr) & 0xFFFF)
    msg.pt.x = int((g.x() + x) * dpr)
    msg.pt.y = int((g.y() + y) * dpr)
    ok, code = w.nativeEvent(b"windows_generic_MSG", int(ctypes.addressof(msg)))
    return ok, int(code) if ok else 0


print("=== A. 窗口不再抢系统边框消息（边缘必须是客户区）===")
w = make_window()
w.setGeometry(w.geometry().x(), w.geometry().y(), 1120, 900)
app.processEvents()
W, H = w.width(), w.height()

# 关键：以前让窗口回 WM_NCHITTEST 缩放码，系统就把边缘算成"非客户区"，
# Qt 从此不再产生普通鼠标按下事件 —— 拖不动就是这么来的。
check(
    "nativeEvent" not in type(w).__dict__,
    "窗口没有自定义 nativeEvent（边缘才留得住鼠标事件）",
    str("nativeEvent" in type(w).__dict__),
)

border_points = [
    (2, 2), (W - 2, 2), (2, H - 2), (W - 2, H - 2),
    (2, H // 2), (W - 2, H // 2), (W // 2, 2), (W // 2, H - 2),
]
stolen = {}
for (x, y) in border_points:
    try:
        ok, code = hit_test(w, x, y)
    except (ValueError, TypeError):
        ok, code = False, 0
    if ok:
        stolen[(x, y)] = code
check(not stolen, "八个边缘点都不被当成非客户区", str(stolen))

try:
    ok, code = hit_test(w, W // 2, H // 2)
except (ValueError, TypeError):
    ok, code = False, 0
check(not ok, "窗口中间也不抢鼠标事件", f"ok={ok} code={code}")

print()
print("=== A2. Qt 层边缘命中（决定按下时能不能拖）===")
# 光有 WM_NCHITTEST 只能让光标变箭头，真正拖起来靠 _edges_at + startSystemResize
ALL_EDGES = (Qt.LeftEdge, Qt.RightEdge, Qt.TopEdge, Qt.BottomEdge)


def edge_flags(x, y):
    return w._edges_at(QPoint(x, y))


qt_cases = {
    (2, H // 2): ([Qt.LeftEdge], "左边"),
    (W - 2, H // 2): ([Qt.RightEdge], "右边"),
    (W // 2, 2): ([Qt.TopEdge], "上边"),
    (W // 2, H - 2): ([Qt.BottomEdge], "下边"),
    (2, 2): ([Qt.LeftEdge, Qt.TopEdge], "左上角"),
    (W - 2, 2): ([Qt.RightEdge, Qt.TopEdge], "右上角"),
    (2, H - 2): ([Qt.LeftEdge, Qt.BottomEdge], "左下角"),
    (W - 2, H - 2): ([Qt.RightEdge, Qt.BottomEdge], "右下角"),
}
bad2 = {}
for (x, y), (want, label) in qt_cases.items():
    got = edge_flags(x, y)
    hit = [e for e in ALL_EDGES if got & e]
    if sorted(e.value for e in hit) != sorted(e.value for e in want):
        bad2[label] = (repr(got), [str(e) for e in want])
check(not bad2, "八条边/四个角都识别成缩放边", str(bad2))

for label, pos in [
    ("正中间", QPoint(W // 2, H // 2)),
    ("内容区", QPoint(400, 400)),
    ("贴着但还差一点", QPoint(_RB + 20, _RB + 20)),
]:
    check(not edge_flags(pos.x(), pos.y()), f"{label}不算边缘", repr(edge_flags(pos.x(), pos.y())))

print()
print("=== A3. 按下边缘要真的启动缩放 ===")
called = []


def _fake_resize(edges):
    called.append(edges)
    return True


real_start_resize = w.start_resize


def press_on(widget, pos, target=None):
    gpos = widget.mapToGlobal(pos)
    return QMouseEvent(
        QEvent.MouseButtonPress,
        QPointF(pos),
        QPointF(gpos),
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )


w.start_resize = _fake_resize
called.clear()
w.mousePressEvent(press_on(w, QPoint(2, H // 2)))
check(bool(called) and bool(called[-1] & Qt.LeftEdge), "左边按下 -> 启动缩放", repr(called))
called.clear()
w.mousePressEvent(press_on(w, QPoint(W // 2, H // 2)))
check(not called, "中间按下 -> 不启动缩放", repr(called))

print()
print("=== A4. 标题栏顶边让位给缩放 ===")
tb = w.titlebar
called.clear()
tb.mousePressEvent(press_on(tb, QPoint(10, 2)))
check(bool(called) and bool(called[-1] & Qt.TopEdge),
      "标题栏顶边按下 -> 缩放而不是拖窗口", repr(called))
check(tb._drag_from is None, "没有误当成拖动窗口", str(tb._drag_from))

called.clear()
tb.mousePressEvent(press_on(tb, QPoint(300, 23)))
check(not called and tb._drag_from is not None,
      "标题栏中间按下 -> 正常拖窗口", f"called={called} drag={tb._drag_from}")
tb.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, QPointF(300, 23),
                                 QPointF(tb.mapToGlobal(QPoint(300, 23))),
                                 Qt.LeftButton, Qt.NoButton, Qt.NoModifier))

w.start_resize = real_start_resize
check(w.start_resize(Qt.Edges()) is False, "空边缘不启动缩放", "")
check(w.start_resize(Qt.LeftEdge | Qt.TopEdge) in (True, False), "非空边缘会去问窗口要缩放", "")

print()
print("=== A6. 点边缘空白区能不能冒泡上来（真实 Qt 事件投递）===")
from PySide6.QtTest import QTest  # noqa: E402

w.setGeometry(120, 80, 1120, 900)
app.processEvents()
w.start_resize = _fake_resize

called.clear()
QTest.mousePress(w.root, Qt.LeftButton, Qt.NoModifier, QPoint(2, 400))
app.processEvents()
QTest.mouseRelease(w.root, Qt.LeftButton, Qt.NoModifier, QPoint(2, 400))
app.processEvents()
check(
    bool(called) and bool(called[-1] & Qt.LeftEdge),
    "点 root 左边缘 -> 冒泡到窗口并启动缩放",
    repr(called),
)

called.clear()
QTest.mousePress(w.root, Qt.LeftButton, Qt.NoModifier, QPoint(560, 400))
app.processEvents()
QTest.mouseRelease(w.root, Qt.LeftButton, Qt.NoModifier, QPoint(560, 400))
app.processEvents()
check(not called, "点 root 中间 -> 不启动缩放", repr(called))

w.start_resize = real_start_resize

print()
print("=== A5. 系统不接手时也要能拖（手动兜底）===")
# 真实环境里 startSystemResize 一般会成功；这里强行让它失败，验证退路
w.setGeometry(120, 80, 1120, 900)
app.processEvents()
g0 = QRect(w.geometry())
w.start_resize = lambda edges: False

w.begin_resize(Qt.LeftEdge, QPoint(g0.x() + 2, g0.y() + 400))
check(w._rs_active, "系统不接时进入手动缩放", str(w._rs_active))
w._apply_manual_resize(QPoint(g0.x() + 2 - 120, g0.y() + 400))
check(
    w.width() == g0.width() + 120 and w.x() == g0.x() - 120,
    "往左拖 120 -> 左边界跟着走",
    f"{w.geometry()} 起点 {g0}",
)
w._apply_manual_resize(QPoint(g0.x() + 2 + 9000, g0.y() + 400))
check(
    w.width() == 980 and w.x() == g0.x() + g0.width() - 980,
    "往右拖到头 -> 停在最小宽度 980",
    f"{w.geometry()}",
)
w.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, QPointF(5, 400),
                                QPointF(w.mapToGlobal(QPoint(5, 400))),
                                Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
check(not w._rs_active, "松手后结束手动缩放", str(w._rs_active))

w.setGeometry(g0)
app.processEvents()
w.begin_resize(Qt.RightEdge | Qt.BottomEdge,
               QPoint(g0.x() + g0.width() - 2, g0.y() + g0.height() - 2))
w._apply_manual_resize(
    QPoint(g0.x() + g0.width() - 2 + 80, g0.y() + g0.height() - 2 + 60)
)
check(
    w.width() == g0.width() + 80 and w.height() == g0.height() + 60,
    "右下角一次改宽和高",
    f"{w.width()}x{w.height()}",
)
w.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, QPointF(5, 400),
                                QPointF(w.mapToGlobal(QPoint(5, 400))),
                                Qt.LeftButton, Qt.NoButton, Qt.NoModifier))

w.setGeometry(120, 80, 1120, 900)
app.processEvents()
w.start_resize = real_start_resize

print()
print("=== B. 左边栏跟着窗口变宽 ===")
for width, want in [(980, 470), (1120, 470), (1400, 588), (1900, 760), (2600, 760)]:
    w.resize(width, 900)
    app.processEvents()
    got = w.left_panel.width()
    check(got == want, f"窗口 {width} → 左栏 {want}", f"实际 {got}")

print()
print("=== C. 记住大小/位置 ===")
w.setGeometry(120, 80, 1366, 940)
app.processEvents()
w._save_geometry()
saved = w.cfg.get("settings_geom")
check(saved == [120, 80, 1366, 940], "几何写进 config", str(saved))
on_disk = json.loads(sr.CONFIG_PATH.read_text(encoding="utf-8"))
check(on_disk.get("settings_geom") == [120, 80, 1366, 940], "几何真的落盘了", str(on_disk.get("settings_geom")))

w2 = make_window()
check((w2.width(), w2.height()) == (1366, 940), "重开窗口还原到上次大小",
      f"{w2.width()}x{w2.height()}")
check((w2.geometry().x(), w2.geometry().y()) == (120, 80), "位置也还原",
      f"{w2.geometry().x()},{w2.geometry().y()}")

print()
print("=== D. 异常的存档不会把窗口弄丢 ===")
w2.cfg["settings_geom"] = [9000, 9000, 200, 100]
w3 = make_window()
check(w3.width() >= 980 and w3.height() >= 860, "太小的尺寸被抬回最小值",
      f"{w3.width()}x{w3.height()}")
scr = QApplication.primaryScreen().availableGeometry()
inside = scr.contains(QPoint(w3.geometry().x() + 4, w3.geometry().y() + 4))
check(inside, "位置被拉回屏幕内", f"{w3.geometry()} / 屏幕 {scr}")

# 存一个类型不对的值（比如手改 json 改坏了），不该让窗口打不开
data = json.loads(sr.CONFIG_PATH.read_text(encoding="utf-8"))
data["settings_geom"] = "垃圾数据"
sr.CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
w4 = make_window()
check((w4.width(), w4.height()) == (1120, 900), "存档坏了就用默认尺寸",
      f"{w4.width()}x{w4.height()}")

for win in (w, w2, w3, w4):
    win.hide()

print()
print("=" * 56)
if BAD:
    print(f"结果：{len(BAD)} 项失败 / 共 {len(OK) + len(BAD)} 项")
    for n in BAD:
        print("  FAIL", n)
    raise SystemExit(1)
print(f"结果：全部通过（{len(OK)} 项）")
