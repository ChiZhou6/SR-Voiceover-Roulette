"""双环轮盘 + 拖放替换语义（v0.5.4）。

要验的是规则本身，不靠肉眼看图：
  1. ≤8 个：单环，跟以前一样均匀等分
  2. 第 9 个：外圈出现，内圈固定 8 格，外圈 30° 一格
  3. 空的外圈格不参与选中，但可以拖东西进去（外圈允许留空）
  4. 拖到格子 = 替换（格子数不变），拖到中心 = 追加
  5. 内 8 + 外 12 = 20 封顶
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, Qt                             # noqa: E402
from PySide6.QtWidgets import QApplication                        # noqa: E402

import sr_roulette as sr                                          # noqa: E402
from sounds_config import INNER_MAX, MAX_SLOTS, OUTER_MAX         # noqa: E402

FAILS: list[str] = []


def check(ok: bool, what: str, detail: str = "") -> None:
    print(f"  {'[OK]' if ok else '[XX]'} {what}" + (f"  ({detail})" if detail else ""))
    if not ok:
        FAILS.append(what)


def pt(deg: float, r: float) -> tuple[float, float]:
    """极坐标转屏幕坐标：0° = 正上方，顺时针。"""
    rad = math.radians(90.0 - deg)
    return r * math.cos(rad), -r * math.sin(rad)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])

    cfg = dict(sr.DEFAULT_CONFIG)
    cfg["wheel_radius"] = 170
    cfg["inner_ratio"] = 0.42
    cfg["outer_thickness"] = 60
    R = float(cfg["wheel_radius"])

    print("=== 1. 分环规则 ===")
    for n in (1, 5, 8):
        geo = sr.ring_layout(cfg, n, 1.0)
        check(not geo["two_ring"] and geo["inner_n"] == n and geo["outer_n"] == 0,
              f"{n} 个：单环 {n} 格", str(geo["inner_n"]))
    check(abs(sr.ring_layout(cfg, 5, 1.0)["extent"] - R) < 1e-6,
          "单环时轮盘外缘 = 内圈半径")

    geo9 = sr.ring_layout(cfg, 9, 1.0)
    check(geo9["two_ring"], "9 个：出现外圈")
    check(geo9["inner_n"] == INNER_MAX, "内圈固定 8 格", str(geo9["inner_n"]))
    check(geo9["outer_n"] == 1, "外圈占用 1 格", str(geo9["outer_n"]))
    check(abs(geo9["inner_r1"] - R) < 1e-6,
          "内圈半径没变（还是 wheel_radius）", f"{geo9['inner_r1']:.1f}")
    # v0.5.5 起两圈之间不再留缝：outer_r0 == inner_r1，连成一整块
    check(abs(geo9["outer_r0"] - geo9["inner_r1"]) < 1e-6,
          "外圈紧贴内圈外缘（无缝隙）",
          f"{geo9['outer_r0']:.1f} == {geo9['inner_r1']:.1f}")
    check(abs(geo9["extent"] - (R + sr.OUTER_GAP + 60)) < 1e-6,
          "外缘 = 半径 + 缝 + 外圈厚度", f"{geo9['extent']:.1f}")

    geo20 = sr.ring_layout(cfg, 20, 1.0)
    check(geo20["outer_n"] == OUTER_MAX, "20 个：外圈满 12 格", str(geo20["outer_n"]))
    geo21 = sr.ring_layout(cfg, 21, 1.0)
    check(geo21["outer_n"] == OUTER_MAX, "超过 20 也只画 12 格", str(geo21["outer_n"]))

    print("\n=== 2. 命中判定：距离决定环，角度决定格 ===")
    mid_inner = (sr.ring_layout(cfg, 9, 1.0)["inner_r0"] + R) / 2.0
    mid_outer = (geo9["outer_r0"] + geo9["outer_r1"]) / 2.0

    dx, dy = pt(0, mid_inner)
    check(sr.index_from_delta(dx, dy, 9, 0.0, cfg) == 0, "正上方、内圈 -> 第 0 格")
    dx, dy = pt(45, mid_inner)
    check(sr.index_from_delta(dx, dy, 9, 0.0, cfg) == 1, "45°、内圈 -> 第 1 格（8 等分）")
    dx, dy = pt(350, mid_inner)
    check(sr.index_from_delta(dx, dy, 9, 0.0, cfg) == 7,
          "350° -> 第 7 格（8 等分里 0 号只占 0~45°）")
    dx, dy = pt(20, mid_inner)
    check(sr.index_from_delta(dx, dy, 9, 0.0, cfg) == 0, "20° 仍属第 0 格")

    dx, dy = pt(0, mid_outer)
    check(sr.index_from_delta(dx, dy, 9, 0.0, cfg) == INNER_MAX,
          "正上方、外圈 -> 第 9 格（下标 8）")
    dx, dy = pt(35, mid_outer)   # 外圈第 2 格，但只有 1 个音效
    check(sr.index_from_delta(dx, dy, 9, 0.0, cfg) is None,
          "指向空的外圈格 -> 不选中")
    dx, dy = pt(35, mid_outer)
    check(sr.index_from_delta(dx, dy, 11, 0.0, cfg) == INNER_MAX + 1,
          "有 3 个外圈音效时同一角度 -> 下标 9")

    dx, dy = pt(0, 10)
    check(sr.index_from_delta(dx, dy, 9, 24.0, cfg) is None, "中心死区内不选中")

    print("\n=== 3. 指针能推到外圈 ===")
    limit = geo9["extent"] * float(cfg["max_offset_ratio"])
    check(limit > geo9["outer_r0"], "限位半径伸进了外圈",
          f"limit {limit:.0f} > outer_r0 {geo9['outer_r0']:.0f}")

    print("\n=== 4. 拖放：替换 vs 追加 ===")
    from sounds_config import SoundsConfig

    names = [f"{i:02d}.wav" for i in range(1, 9)]
    sc = SoundsConfig(ROOT / "_tmp_rings.json")
    sc.order = list(names[:5])
    sc.items = {}
    check(sc.replace_at(0, "07.wav") and sc.order[0] == "07.wav"
          and len(sc.order) == 5, "替换：格子数不变", str(sc.order))
    before = list(sc.order)
    sc.replace_at(1, before[0])
    check(sc.order[0] == before[1] and sc.order[1] == before[0],
          "把盘上已有的音效拖到另一格 -> 两格互换位置", str(sc.order[:3]))
    check(len(sc.order) == len(set(sc.order)), "不会出现重复条目", str(sc.order))

    sc.order = list(names[:5])
    sc.add("06.wav")
    check(len(sc.order) == 6 and sc.order[-1] == "06.wav", "追加到末尾")
    sc.order = list(names[:8]) + list(names)   # 16 个
    for i in range(4):
        sc.add(f"x{i}.wav")
    check(len(sc.order) == MAX_SLOTS, "封顶 20", str(len(sc.order)))
    check(sc.add("y.wav") is False and len(sc.order) == MAX_SLOTS, "第 21 个被拒绝")

    print("\n=== 5. 配置窗口预览的落点 ===")
    from settings_window import ADD_TO_END, WheelPreview

    class FakeBank:
        """只提供预览需要的三个东西，免得真去扫 sounds 目录。"""

        def __init__(self, n: int) -> None:
            self.names = [f"{i:02d}.wav" for i in range(1, n + 1)]
            self.items = [Path(x) for x in self.names]

        def __len__(self) -> int:
            return len(self.names)

        def name_at(self, i: int) -> str:
            return Path(self.names[i]).stem

        def full_at(self, i: int) -> str:
            return self.names[i]

        def path_at(self, i: int):
            return None

    bank = FakeBank(9)   # 9 个 -> 内 8 + 外 1
    pv = WheelPreview(cfg, bank)
    pv.resize(int(cfg["wheel_radius"] * 2 + 48), int(cfg["wheel_radius"] * 2 + 48))
    pv.show()
    app.processEvents()
    geo, scale = pv.ring_geometry()
    cx, cy = pv.width() / 2.0, pv.height() / 2.0

    def at(deg: float, r: float) -> QPoint:
        # geo 里的半径已经按 scale 缩过了，这里直接换成控件坐标，别再乘一次
        dx, dy = pt(deg, r)
        return QPoint(int(cx + dx), int(cy + dy))

    check(scale < 1.0, "外圈出现时预览整体缩小", f"scale {scale:.2f}")
    check(pv._target_at(QPoint(int(cx), int(cy))) == ADD_TO_END, "中心 -> 追加")
    mid_i = (geo["inner_r0"] + geo["inner_r1"]) / 2.0
    mid_o = (geo["outer_r0"] + geo["outer_r1"]) / 2.0
    check(pv._target_at(at(0, mid_i)) == 0, "内圈第 0 格 -> 替换该格")
    check(pv._target_at(at(0, mid_o)) == 8, "外圈第 1 格 -> 替换该格")
    # v0.5.5 起外圈可以留空：空位也接受，拖过去就放在那儿
    check(pv._target_at(at(35, mid_o)) == sr.INNER_MAX + 1,
          "空的外圈格 -> 接受（放进去）", str(pv._target_at(at(35, mid_o))))
    check(pv._target_at(at(0, geo["extent"] + 40)) is None, "轮盘外 -> 不接受")

    Path(ROOT / "_tmp_rings.json").unlink(missing_ok=True)

    print("\n" + ("全部通过" if not FAILS else f"{len(FAILS)} 项失败: {FAILS}"))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
