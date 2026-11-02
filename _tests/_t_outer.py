"""外圈摆位（允许留空）+ 中心同色 + 两圈无缝隙 的回归测试。

要验的规则：
  1. sounds.json 能存/读 outer_slots（含 null），老配置没有这个字段也能自动补齐
  2. 外圈格子可以拖到空位：挪过去、原位变空
  3. 两个有内容的格子互换；内圈和外圈之间也能互换，但内圈拖到外圈空位仍拒绝
  4. 绘制只画有内容的位置（空位真的什么都不画）
  5. 指向空位 = 没指任何东西；指向有内容的位置 = 正确的音效下标
  6. 中心圆和普通格子同色同描边
  7. 内圈外圈之间没有缝隙
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, Qt               # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication          # noqa: E402

app = QApplication(sys.argv[:1])

import sr_roulette as sr                            # noqa: E402
from sounds_config import OUTER_MAX, INNER_MAX, SoundsConfig  # noqa: E402

fails: list[str] = []


def check(ok: bool, label: str, extra: str = "") -> None:
    print(f"  [{'OK' if ok else 'XX'}] {label}" + (f"  ({extra})" if extra else ""))
    if not ok:
        fails.append(label)


def names(n: int) -> list[str]:
    return [f"{i:02d}.wav" for i in range(1, n + 1)]


class FakeBank:
    """只提供预览需要的几个接口，不去碰真实 sounds 目录。"""

    def __init__(self, cfg: SoundsConfig) -> None:
        self.scfg = cfg
        self.items = [Path(n) for n in cfg.order]

    def __len__(self) -> int:
        return len(self.items)

    def name_at(self, i: int) -> str:
        return self.items[i].stem

    def full_at(self, i: int) -> str:
        return self.items[i].name

    def path_at(self, i: int):
        return None

    def outer_index_map(self):
        return self.scfg.outer_index_map()


def tmp_cfg(n: int, slots=None) -> SoundsConfig:
    f = Path(tempfile.mkdtemp()) / "sounds.json"
    data = {"version": 1, "order": names(n), "items": {}}
    if slots is not None:
        data["outer_slots"] = slots
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    c = SoundsConfig(f)
    c.load()
    return c


print("=== 1. 摆位表存取 ===")
c = tmp_cfg(12)
check(c.outer_slots[:4] == names(12)[8:], "老配置（没有 outer_slots）自动按顺序补位",
      str(c.outer_slots[:4]))
check(len(c.outer_slots) == OUTER_MAX, "摆位表固定 12 格", str(len(c.outer_slots)))
check(all(x is None for x in c.outer_slots[4:]), "没音效的位置是空的")

c.outer_slots[5] = c.outer_slots[0]
c.outer_slots[0] = None
c.save()
c2 = SoundsConfig(c.path)
c2.load()
check(c2.outer_slots[5] == names(12)[8] and c2.outer_slots[0] is None,
      "空格子（null）能存进 json 再读回来", str(c2.outer_slots[:6]))

c3 = tmp_cfg(12, slots=[None] * OUTER_MAX)
check(c3.outer_slots[:4] == names(12)[8:], "摆位表全空也会按 order 补齐，不会丢音效")

c4 = tmp_cfg(12, slots=[names(12)[0], names(12)[9]] + [None] * 10)
check(c4.outer_slots[1] == names(12)[9],
      "摆位表里的内圈音效被忽略、外圈的保留", str(c4.outer_slots[:3]))
check(names(12)[0] not in c4.outer_slots, "内圈音效不会被塞进外圈")

print("\n=== 2. 外圈拖到空位 ===")
c = tmp_cfg(12)
first = c.outer_slots[0]
check(first is not None, "第 0 格有音效", str(first))
check(c.swap_slots(INNER_MAX + 0, INNER_MAX + 6), "外圈 0 号拖到空着的 6 号")
check(c.outer_slots[6] == first, "东西到了 6 号格", str(c.outer_slots[6]))
check(c.outer_slots[0] is None, "原来的 0 号格空出来了")
check(len(c.order) == 12, "音效总数不变", str(len(c.order)))
check(c.outer_index_map()[6] == 8, "6 号格对应第 8 个音效", str(c.outer_index_map()[6]))
check(c.outer_index_map()[0] is None, "0 号格是空的")

print("\n=== 3. 两个有内容的格子互换 ===")
c = tmp_cfg(12)
a, b = c.outer_slots[0], c.outer_slots[1]
check(c.swap_slots(INNER_MAX + 0, INNER_MAX + 1), "外圈 0 <-> 1")
check(c.outer_slots[0] == b and c.outer_slots[1] == a, "两格互换成功",
      f"{c.outer_slots[0]} / {c.outer_slots[1]}")
check(c.outer_index_map()[1] == 8, "位置换了，order 不动（order 只管先后）",
      str(c.outer_index_map()[:3]))

print("\n=== 4. 内圈互换 / 跨圈互换（v0.5.7 放开）===")
c = tmp_cfg(12)
n0, n3 = c.order[0], c.order[3]
check(c.swap_slots(0, 3), "内圈 0 <-> 3")
check(c.order[0] == n3 and c.order[3] == n0, "内圈两格互换成功")

outer_name, inner_name = c.outer_slots[0], c.order[0]
check(outer_name is not None and inner_name is not None, "换之前两边都有音效")
check(c.swap_slots(0, INNER_MAX), "内圈 0 <-> 外圈 0 号位")
check(c.order[0] == outer_name, "内圈 0 换成了外圈那个音效", c.order[0])
check(c.outer_slots[0] == inner_name, "外圈 0 号位换成了内圈那个音效", str(c.outer_slots[0]))
check(len(c.order) == 12, "音效总数不变", str(len(c.order)))
check(all(x is not None for x in c.order[:INNER_MAX]), "内圈 8 格仍然是满的")
check(sorted(c.order) == sorted(names(12)), "没有音效被 normalize 清掉")
c.save()
c2 = SoundsConfig(c.path)
c2.load()
check(c2.order[0] == outer_name and c2.outer_slots[0] == inner_name,
      "跨圈互换的结果能存盘读回", f"{c2.order[0]} / {c2.outer_slots[0]}")

check(not c.swap_slots(0, INNER_MAX + 6), "内圈拖到外圈空位仍然拒绝（否则内圈缺一格）")
check(not c.swap_slots(INNER_MAX + 6, 0), "外圈空位拖到内圈同样拒绝")
check(c.order[0] == outer_name, "被拒绝时什么都没变")

# 反方向（从外圈拖到内圈）走同一条路径，再验一次
c3 = tmp_cfg(12)
i_name, o_name = c3.order[2], c3.outer_slots[1]
check(c3.swap_slots(INNER_MAX + 1, 2), "外圈 1 号位 <-> 内圈 2")
check(c3.order[2] == o_name and c3.outer_slots[1] == i_name,
      "反方向互换结果一致", f"{c3.order[2]} / {c3.outer_slots[1]}")

print("\n=== 5. 音效库拖进外圈 ===")
c = tmp_cfg(9)          # 9 个：内 8 + 外 1（第 0 格）
check(c.outer_slots[0] is not None and c.outer_slots[5] is None, "初始只有第 0 格有内容")
check(c.put_at_slot(INNER_MAX + 5, "新音效.wav"), "把新音效放进空着的 5 号格")
check(c.outer_slots[5] == "新音效.wav", "新音效占住 5 号格", str(c.outer_slots[5]))
check(len(c.order) == 10, "音效总数 +1", str(len(c.order)))
check(c.put_at_slot(INNER_MAX + 0, "又一个.wav"), "往有内容的 0 号格放 = 替换")
check(c.outer_slots[0] == "又一个.wav", "0 号格被换掉", str(c.outer_slots[0]))
check(len(c.order) == 10, "替换不会让格子变多")

print("\n=== 6. 绘制：空位真的不画 ===")
cfg = dict(sr.DEFAULT_CONFIG)
cfg.update({"wheel_radius": 170, "inner_ratio": 0.42, "outer_thickness": 60})
c = tmp_cfg(12)
c.swap_slots(INNER_MAX + 0, INNER_MAX + 9)      # 制造一个大空当
bank = FakeBank(c)
geo = sr.ring_layout(cfg, len(bank), 1.0)
w = sr.WheelWidget(cfg)
w.bank = bank
pairs = w.slot_pairs(geo)
sids = [sid for sid, _ in pairs]
check(len(pairs) == 12, "12 个音效 -> 12 个格子", str(len(pairs)))
check(INNER_MAX + 0 not in sids, "空出来的位置不画")
check(INNER_MAX + 9 in sids, "挪过去的位置要画")
check(len(set(sids)) == len(sids), "没有两个音效画在同一格")
check(all(sr.slot_geometry(geo, s) is not None for s in sids), "每个位置都算得出几何")

print("\n=== 7. 指向空位 = 没指任何东西 ===")
size = int(geo["extent"] * 2 + 48)
w.resize(size, size)
mid_o = (geo["outer_r0"] + geo["outer_r1"]) / 2.0


def pt(deg: float, r: float) -> tuple[float, float]:
    rad = math.radians(deg)
    return r * math.cos(rad), -r * math.sin(rad)


omap = bank.outer_index_map()
dx, dy = pt(83, mid_o)      # 外圈第 0 格：被空出来了
check(sr.index_from_delta(dx, dy, len(bank), 0.0, cfg, outer_map=omap) is None,
      "指向空着的外圈格 -> 不选中")
dx, dy = pt(83, mid_o)
check(sr.index_from_delta(dx, dy, len(bank), 0.0, cfg) == INNER_MAX,
      "不给摆位表时退回老规则（按顺序排）")
dx, dy = pt(-15, mid_o)     # 外圈第 3 格附近
idx = sr.index_from_delta(dx, dy, len(bank), 0.0, cfg, outer_map=omap)
check(idx is not None and bank.outer_index_map()[3] == idx,
      "指向有内容的格 -> 下标对得上", str(idx))

print("\n=== 8. 中心同色 + 两圈无缝隙 ===")
check(abs(geo["outer_r0"] - geo["inner_r1"]) < 1e-9,
      "外圈内缘 == 内圈外缘（没有缝）",
      f"{geo['outer_r0']:.1f}")
w.bank = FakeBank(tmp_cfg(12))
w.resize(size, size)
w.selected = None
img = QImage(size, size, QImage.Format_ARGB32)
img.fill(Qt.transparent)
w.render(img)
cx = cy = size // 2
# 取中心圆里的一个点：避开中间那个光标圆点（半径 7）和两行提示文字
center_px = QColor(img.pixel(int(cx + geo["hole"] * 0.6), cy))
# 内圈第 1 格的中线上取一点（避开中心文字和光标）
t = (geo["inner_r0"] + geo["inner_r1"]) / 2.0
sx, sy = pt(67, t)
sector_px = QColor(img.pixel(int(cx + sx), int(cy + sy)))
check(center_px.alpha() > 0, "中心是画了东西的（不是纯透明）")
check(abs(center_px.lightness() - sector_px.lightness()) <= 6,
      "中心亮度与普通格子一致",
      f"中心 {center_px.lightness()} vs 格子 {sector_px.lightness()}")
check(center_px.lightness() > 15,
      "中心不再是接近纯黑（>15）", str(center_px.lightness()))

print()
if fails:
    print(f"{len(fails)} 项失败: {fails}")
    sys.exit(1)
print("全部通过")
