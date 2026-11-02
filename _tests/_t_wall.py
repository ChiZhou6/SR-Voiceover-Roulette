"""外圈空位"撞墙"的回归测试（v0.5.6）。

要验的规则：
  1. 单环（<=8 个音效）没有外圈，光标原样放行
  2. 外圈排满时也没有墙，光标原样放行
  3. 落在内圈半径带内一律放行（内圈整圈都有音效）
  4. 站在有音效的外圈格里推向旁边空白 -> 只滑到**这一格自己的边界**就停住
  5. 落点隔着好几格空白 -> 依然只停在本格边界，绝不"瞬移"到远处的格子
  6. 人在内圈、方向冲着空白 -> 外圈整块过不去，半径顶在分界处、角度不动
  7. 逐帧推进时每帧角度变化都很小（看着是滑过去，不是跳过去）
  8. 夹过之后，index_from_delta 一定能选中一个真实存在的音效
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sr_roulette as sr                            # noqa: E402
from sounds_config import INNER_MAX, OUTER_MAX      # noqa: E402

fails: list[str] = []


def check(ok: bool, label: str, extra: str = "") -> None:
    print(f"  [{'OK' if ok else 'XX'}] {label}" + (f"  ({extra})" if extra else ""))
    if not ok:
        fails.append(label)


cfg = dict(sr.DEFAULT_CONFIG)
cfg.update({"wheel_radius": 170, "inner_ratio": 0.42, "outer_thickness": 60,
            "deadzone_px": 24})

count9 = INNER_MAX + 1
geo = sr.ring_layout(cfg, count9, 1.0)
mid_o = (geo["outer_r0"] + geo["outer_r1"]) / 2.0
mid_i = (geo["inner_r0"] + geo["inner_r1"]) / 2.0
SPAN = 360.0 / OUTER_MAX
EPS = SPAN * 0.02


def at(deg: float, r: float) -> tuple[float, float]:
    """轮盘角度（0 = 正上方，顺时针为正）+ 半径 -> 控件坐标位移。"""
    rad = math.radians(deg)
    return r * math.sin(rad), -r * math.cos(rad)


def ang_of(dx: float, dy: float) -> float:
    return sr.wheel_angle(dx, dy)


def near(a: float, b: float, tol: float = 0.6) -> bool:
    return min((a - b) % 360.0, (b - a) % 360.0) < tol


def only_first(n: int) -> list[int | None]:
    """只有前 n 个外圈位置有音效，其余空着。"""
    return [INNER_MAX + p if p < n else None for p in range(OUTER_MAX)]


print("=== 1. 单环没有墙 ===")
m1 = only_first(1)
for deg in (10, 90, 200):
    dx, dy = at(deg, mid_i)
    got = sr.clamp_to_filled(dx, dy, cfg, INNER_MAX, outer_map=m1, prev=(0.0, 0.0))
    check(got == (dx, dy), f"8 个音效时 {deg}° 方向不做任何夹取")

print("\n=== 2. 外圈排满也没墙 ===")
full = only_first(OUTER_MAX)
for deg in (5, 45, 175, 265, 355):
    dx, dy = at(deg, mid_o)
    got = sr.clamp_to_filled(dx, dy, cfg, INNER_MAX + OUTER_MAX,
                             outer_map=full, prev=at(deg, mid_i))
    check(abs(got[0] - dx) < 1e-9 and abs(got[1] - dy) < 1e-9,
          f"外圈 12 格排满时 {deg}° 不做夹取")

print("\n=== 3. 内圈带内一律放行 ===")
for deg in (5, 100, 190, 280):
    dx, dy = at(deg, mid_i)
    got = sr.clamp_to_filled(dx, dy, cfg, count9, outer_map=m1,
                             prev=at(deg, mid_i))
    check(abs(got[0] - dx) < 1e-9 and abs(got[1] - dy) < 1e-9,
          f"内圈 {deg}° 方向放行（内圈是满的）")

print("\n=== 4. 站在外圈格里推向旁边空白：只停在本格边界 ===")
# 外圈只有第 0 格有音效（0~30°），人站在这一格中间
for deg, want, why in (
    (20, 20, "还在本格内，不夹"),
    (45, SPAN - EPS, "越过本格顺时针边界 -> 贴边停"),
    (100, SPAN - EPS, "推进更深的空白 -> 依然贴本格边界，不跨格"),
):
    prev = at(15, mid_o)
    dx, dy = at(deg, mid_o)
    got = sr.clamp_to_filled(dx, dy, cfg, count9, outer_map=m1, prev=prev)
    a = ang_of(*got)
    check(near(a, want), f"{deg}° -> {a:.2f}°（{why}）", f"期望 {want:.2f}")
    check(abs(math.hypot(*got) - math.hypot(dx, dy)) < 1e-6, f"{deg}° 半径不变")

# 反过来（逆时针绕到 0° 前面）
prev = at(15, mid_o)
dx, dy = at(350, mid_o)
a = ang_of(*sr.clamp_to_filled(dx, dy, cfg, count9, outer_map=m1, prev=prev))
check(near(a, EPS), "350° -> 贴本格逆时针边界", f"{a:.2f}°")

print("\n=== 5. 隔好几格空白也不会瞬移到远处那格 ===")
# 第 0 格和第 6 格有音效，人站在第 0 格，落点扎进 140°（离第 6 格更近的空白）
# 旧规则会"贴最近的边界"，于是被吸到 180.6°（第 6 格）——正是用户抱怨的瞬移
sparse = [None] * OUTER_MAX
sparse[0] = INNER_MAX
sparse[6] = INNER_MAX + 1
prev = at(15, mid_o)
dx, dy = at(140, mid_o)
a = ang_of(*sr.clamp_to_filled(dx, dy, cfg, INNER_MAX + 2, outer_map=sparse, prev=prev))
check(near(a, SPAN - EPS), "落点扎进远处空白 -> 仍停在第 0 格边界", f"{a:.2f}°")
check(not near(a, 6 * SPAN + EPS, 1.0), "没有被吸到第 6 格上去", f"{a:.2f}°")

print("\n=== 6. 人在内圈、方向冲着空白：外圈整块过不去 ===")
prev = at(150, mid_i)
dx, dy = at(150, mid_o)
vx, vy = sr.clamp_to_filled(dx, dy, cfg, count9, outer_map=m1, prev=prev)
check(near(ang_of(vx, vy), 150.0), "角度一点没动", f"{ang_of(vx, vy):.2f}°")
r = math.hypot(vx, vy)
check(abs(r - (geo["outer_r0"] - 1.0)) < 1e-6, "半径顶在内外圈分界处", f"{r:.1f}")
check(r < geo["outer_r0"], "仍然算内圈（松手有音效，不是空指）")
idx = sr.index_from_delta(vx, vy, count9, float(cfg["deadzone_px"]), cfg, outer_map=m1)
check(idx is not None, "被挡住时仍然选中内圈的音效", str(idx))

print("\n=== 7. 逐帧推进：每帧角度变化都很小 ===")
prev = at(15, mid_o)
max_step = 0.0
for step in range(1, 40):
    deg = 15 + step * 2.0          # 每帧往外推 2°
    dx, dy = at(deg, mid_o)
    vx, vy = sr.clamp_to_filled(dx, dy, cfg, count9, outer_map=m1, prev=prev)
    d = abs(((ang_of(vx, vy) - ang_of(*prev)) + 180.0) % 360.0 - 180.0)
    max_step = max(max_step, d)
    prev = (vx, vy)
check(max_step <= 2.5, "单帧角度变化不超过一格推进量", f"最大 {max_step:.2f}°")
check(near(ang_of(*prev), SPAN - EPS), "推到底后停在边界上", f"{ang_of(*prev):.2f}°")

print("\n=== 8. 夹过之后一定选得到东西 ===")
bad = []
for n in (1, 2, 5, 11):
    tab = only_first(n)
    for deg in range(0, 360, 3):
        p = at(deg, mid_i)                 # 从内圈同一方向推出去
        dx, dy = at(deg, mid_o)
        vx, vy = sr.clamp_to_filled(dx, dy, cfg, INNER_MAX + n, outer_map=tab, prev=p)
        idx = sr.index_from_delta(vx, vy, INNER_MAX + n,
                                  float(cfg["deadzone_px"]), cfg, outer_map=tab)
        if idx is None:
            bad.append((n, deg))
check(not bad, "任意方向被夹之后都能选中一个音效", str(bad[:4]))

print("\n=== 9. 没有历史位置时退回旧规则 ===")
dx, dy = at(75, mid_o)     # 9 个音效、按顺序排 -> 只有第 0 格有货
vx, vy = sr.clamp_to_filled(dx, dy, cfg, count9, outer_map=None, prev=None)
idx = sr.index_from_delta(vx, vy, count9, float(cfg["deadzone_px"]), cfg)
check(idx == INNER_MAX, "不给摆位表 / 没有 prev 时也夹到第 0 格", str(idx))

print()
if fails:
    print(f"[XX] 有 {len(fails)} 项不通过：")
    for f in fails:
        print("   -", f)
    sys.exit(1)
print("[OK] 全部通过")
