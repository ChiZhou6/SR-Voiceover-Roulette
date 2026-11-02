"""回归：中空判定口径 / 轮盘整体大小 / 暂停提示的位置与透明度。

跑法：python _t_hit_size.py

这次要钉死的是一个老 bug：
  选中判定用的是固定 24px 死区，画出来的中空却有 76px，
  于是"手还在白圈里，某一格已经亮了"，而且怎么调「中空比例」都不变。

四块：
  A 中空判定必须等于画出来的中空半径（调比例就跟着变）
  B 「整体大小」——几何、判定、限位、动画余量都吃同一个缩放
  C 暂停提示——位置落在屏幕 3/4，透明度跟轮盘的不透明度走
  D 设置页——有「整体大小」、没有「死区」
  E 像素级验证——画面上白圈的边界就是判定的边界
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from PySide6.QtCore import QPoint  # noqa: E402

import sr_roulette as sr  # noqa: E402

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


def near(a, b, tol=0.6):
    return abs(float(a) - float(b)) <= tol


class FakeBank:
    """最小的 bank 替身：绘制只需要长度、名字和外圈摆位表。"""

    def __init__(self, names):
        self.names = list(names)

    def __len__(self):
        return len(self.names)

    def name_at(self, i):
        return self.names[i] if 0 <= i < len(self.names) else ""

    def outer_index_map(self):
        extra = max(0, len(self.names) - 8)
        return [8 + p if p < extra else None for p in range(12)]


print("=== A 中空判定跟着中空比例走 ===")

cfg = dict(sr.DEFAULT_CONFIG)
cfg["wheel_radius"] = 180
cfg["inner_ratio"] = 0.42          # 中空半径 = 180 * 0.42 = 75.6

geo = sr.ring_layout(cfg, 6, sr.wheel_scale_of(cfg))
check(near(geo["hole"], 75.6), "中空半径按 直径×中空比例 算出", f"{geo['hole']:.1f}")

# 0 号在正上方：dx=0, dy 负值即朝上
check(sr.index_from_delta(0, -30, 6, 24, cfg) is None,
      "中空里 30px 不算选中（以前这里会亮 0 号格）")
check(sr.index_from_delta(0, -74, 6, 24, cfg) is None,
      "刚到中空边缘 74px 仍不算选中")
check(sr.index_from_delta(0, -80, 6, 24, cfg) == 0,
      "越过中空立刻选中最上面那一格")
check(sr.index_from_delta(80, 0, 6, 24, cfg) == 1,
      "右侧 80px 选中 1 号格（顺时针编号不变）")

# 关键回归：把中空比例调大，判定范围必须跟着变大
cfg_wide = dict(cfg)
cfg_wide["inner_ratio"] = 0.62     # 中空半径 = 111.6
check(sr.index_from_delta(0, -100, 6, 24, cfg_wide) is None,
      "中空比例调到 62% 后，100px 也不再算选中")
check(sr.index_from_delta(0, -120, 6, 24, cfg_wide) == 0,
      "同一个比例下越过 111.6px 才选中")

# 调小也要真的变小
cfg_narrow = dict(cfg)
cfg_narrow["inner_ratio"] = 0.25   # 中空半径 = 45
check(sr.index_from_delta(0, -50, 6, 24, cfg_narrow) == 0,
      "中空比例调到 25% 后，50px 已经算选中")

# 外圈：越过内圈外缘就换到外圈格子上
cfg20 = dict(cfg)
check(sr.index_from_delta(0, -200, 20, 24, cfg20) == 8,
      "20 个音效时，正上方外圈是 8 号槽（摆位不变）")
check(sr.index_from_delta(0, -75, 20, 24, cfg20) is None,
      "双环下中空判定同样成立")


print("=== B 整体大小（wheel_scale） ===")

check(near(sr.wheel_scale_of({}), 1.0), "缺省是 100%")
check(near(sr.wheel_scale_of({"wheel_scale": 5}), 2.0), "上限夹到 200%")
check(near(sr.wheel_scale_of({"wheel_scale": 0.01}), 0.5), "下限夹到 50%")
check(near(sr.wheel_scale_of({"wheel_scale": "坏值"}), 1.0), "坏值退回 100%")

cfg_big = dict(cfg)
cfg_big["wheel_scale"] = 1.4
g_big = sr.ring_layout(cfg_big, 6, sr.wheel_scale_of(cfg_big))
check(near(g_big["extent"], 252.0), "140% 时最外缘 = 180×1.4", f"{g_big['extent']:.1f}")
check(near(g_big["hole"], 105.84), "中空半径同步放大", f"{g_big['hole']:.2f}")
check(sr.index_from_delta(0, -100, 6, 0, cfg_big, sr.wheel_scale_of(cfg_big)) is None,
      "放大后判定范围也变大：100px 仍在白圈里")
check(sr.index_from_delta(0, -110, 6, 0, cfg_big, sr.wheel_scale_of(cfg_big)) == 0,
      "放大后越过 105.84px 才选中")

# 外圈厚度也要跟着整体缩放（不是只放大内圈）
cfg20_big = dict(cfg20)
cfg20_big["wheel_scale"] = 1.4
g20 = sr.ring_layout(cfg20_big, 20, sr.wheel_scale_of(cfg20_big))
check(near(g20["outer_r0"], 252.0), "外圈起点跟内圈一起缩放", f"{g20['outer_r0']:.1f}")
check(near(g20["outer_r1"] - g20["outer_r0"], 84.0),
      "外圈厚度 60px 也被放大成 84px", f"{g20['outer_r1'] - g20['outer_r0']:.1f}")

# 收缩
cfg_small = dict(cfg)
cfg_small["wheel_scale"] = 0.7
g_small = sr.ring_layout(cfg_small, 6, sr.wheel_scale_of(cfg_small))
check(near(g_small["extent"], 126.0), "70% 时最外缘 = 126", f"{g_small['extent']:.1f}")
check(sr.index_from_delta(0, -60, 6, 0, cfg_small, sr.wheel_scale_of(cfg_small)) == 0,
      "缩小时白圈也缩小：60px 已经越过 52.92 的边界，算选中")

# 动画的涨大幅度必须随半径自适应，否则大轮盘会被窗口裁边
from PySide6.QtWidgets import QWidget  # noqa: E402


class _A:
    """假音频引擎：只要 playing 属性。"""

    playing = False


w_big = sr.WheelWidget(dict(cfg_big))
w_big.bank = FakeBank([f"音效{i}" for i in range(6)])
extent_big = sr.ring_layout(cfg_big, 6, sr.wheel_scale_of(cfg_big))["extent"]
w_big.resize(int(extent_big * 2 + 48), int(extent_big * 2 + 48))
w_big.selected = 0
w_big.play_flash_anim(lambda: None)
peak = 1.0 + min(0.06, 18.0 / extent_big)
w_big.stop_anims()
check(peak * extent_big <= extent_big + 24.0,
      "释放动画的最大涨大幅度不会顶出窗口（余量 24px）",
      f"{peak:.4f}×{extent_big:.0f} = {peak * extent_big:.1f}")

w_close = sr.WheelWidget(dict(cfg_big))
w_close.bank = w_big.bank
w_close.play_close_anim(lambda: None)
peak_c = 1.0 + min(0.05, 16.0 / extent_big)
w_close.stop_anims()
check(peak_c * extent_big <= extent_big + 24.0,
      "收起动画的涨大幅度同样不会顶出窗口",
      f"{peak_c:.4f}×{extent_big:.0f} = {peak_c * extent_big:.1f}")

w_big.hide()
w_close.hide()


print("=== C 暂停提示：位置 3/4、透明度跟轮盘 ===")

cfg_toast = dict(cfg)
cfg_toast["animations"] = True
toast = sr.PauseToast(cfg_toast)
toast.flash(True)
scr = QApplication.primaryScreen().geometry()
want_y = scr.top() + int(scr.height() * 0.75)
got_y = toast.geometry().center().y()
check(abs(got_y - want_y) <= 2, "提示落在屏幕高度的 3/4 处", f"{got_y} vs {want_y}")
check(abs(toast.geometry().center().x() - scr.center().x()) <= 2, "水平仍然居中")
toast.hide()

# 提示的“旧病”：位置在正中偏上、底板几乎不透明。这两个都要挡住。
check(got_y > scr.center().y(), "已经离开屏幕正中区域（不再压准星）")


def pill_alpha(op: float) -> int:
    c = dict(cfg_toast)
    c["opacity"] = op
    w = sr.PauseToast(c)
    w.paused = True
    w.t = 0.5           # 停在“完全显示”那一段
    img = w.grab().toImage()
    col = img.pixelColor(w.width() // 2, 56)     # 胶囊底板中心
    a = col.alpha()
    w.hide()
    return a


a_full = pill_alpha(1.0)
a_mid = pill_alpha(0.94)      # 默认值，应当跟轮盘一样几乎不透明
a_low = pill_alpha(0.40)
check(a_full >= 230, "100% 时底板基本实心", str(a_full))
check(a_low + 40 <= a_full, "40% 时底板明显透过去", f"{a_low} vs {a_full}")
check(abs(a_mid - a_full) <= 14, "默认 94% 与轮盘观感一致", f"{a_mid} vs {a_full}")


print("=== D 设置页 ===")

import settings_window as sw  # noqa: E402

page_cfg = dict(sr.DEFAULT_CONFIG)
page = sw.WheelPage(page_cfg, None)
check(hasattr(page, "scale"), "外观里有「整体大小」滑块")
check(not hasattr(page, "deadzone"), "「中心死区」已从界面移除")
page.scale.slider.setValue(125)
check(near(page_cfg.get("wheel_scale"), 1.25, 1e-6),
      "拖动后写进 cfg['wheel_scale']", str(page_cfg.get("wheel_scale")))
page.scale.slider.setValue(70)
check(near(page_cfg.get("wheel_scale"), 0.70, 1e-6), "下限 70% 生效")
page.scale.slider.setValue(140)
check(near(page_cfg.get("wheel_scale"), 1.40, 1e-6), "上限 140% 生效")
check("deadzone_px" not in sr.DEFAULT_CONFIG, "默认配置里不再有 deadzone_px")
page.deleteLater()


print("=== E 画出来的白圈边界 = 判定边界 ===")

cfg_px = dict(sr.DEFAULT_CONFIG)
cfg_px["wheel_scale"] = 1.0
cfg_px["opacity"] = 1.0
cfg_px["show_names"] = False
w = sr.WheelWidget(cfg_px)
w.bank = FakeBank(["A", "B", "C", "D"])
w.selected = 0
extent = sr.ring_layout(cfg_px, 4, 1.0)["extent"]
size = int(extent * 2 + 48)
size += size % 2
w.resize(size, size)
img = w.grab().toImage()
cx = cy = size // 2
hole = sr.ring_layout(cfg_px, 4, 1.0)["hole"]


def px(dy: float):
    return img.pixelColor(int(cx), int(cy + dy))


inside = px(-(hole - 8))
outside = px(-(hole + 10))
check(inside.green() < 90,
      "中空内 (hole-8) 是深色底，不是高亮格", f"rgb={inside.red()},{inside.green()},{inside.blue()}")
check(outside.green() > inside.green() + 60,
      "越过 hole 之后正上方变成高亮色（0 号格）",
      f"rgb={outside.red()},{outside.green()},{outside.blue()}")

# 同一个位置交给判定函数，结论必须一致
check(sr.index_from_delta(0, -(hole - 8), 4, 0, cfg_px) is None,
      "判定：hole 内侧不选中")
check(sr.index_from_delta(0, -(hole + 10), 4, 0, cfg_px) == 0,
      "判定：hole 外侧选中 0 号")
w.hide()


print()
print(f"通过 {len(OK)} 项，失败 {len(BAD)} 项")
if BAD:
    for b in BAD:
        print("  XX", b)
    sys.exit(1)
