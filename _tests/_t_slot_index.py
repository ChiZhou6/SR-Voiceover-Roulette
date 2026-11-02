"""槽位号 -> 音效下标 的换算测试。

背景（v0.5.8 修的回归）：v0.5.5 把拖放数据从"音效下标"改成了"槽位号"
（因为外圈要能留空，位置和序号必须分开）。内圈 8 格永远满员，所以内圈里
槽位号恰好等于音效下标——这让"没换算"的代码在内圈上看起来完全正常。
外圈槽位号是 8~19，一旦被直接当成 order 下标用，要么错位要么越界静默失败，
表现就是"外圈的音效怎么拖都从轮盘上取消不掉"。

这里只测纯函数，不依赖任何音频文件。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sr_roulette as sr  # noqa: E402

INNER_MAX = sr.INNER_MAX
OUTER_MAX = sr.OUTER_MAX

fails: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(label)


print("=== 1. 内圈：槽位号 == 音效下标 ===")
check(sr.index_of_slot(0, 12) == 0, "槽位 0 -> 下标 0")
check(sr.index_of_slot(7, 12) == 7, "槽位 7 -> 下标 7")
check(sr.index_of_slot(6, 5) is None, "只有 5 个音效时槽位 6 是空的")
check(sr.index_of_slot(0, 0) is None, "一个音效都没有时返回 None")
check(sr.index_of_slot(None, 12) is None, "没指任何槽位时返回 None")
check(sr.index_of_slot(-1, 12) is None, "负数槽位返回 None")

print("\n=== 2. 外圈：必须查摆位表 ===")
# 12 个音效、外圈 4 个：位置 0~3 有货（下标 8~11），位置 4~11 空
table = [INNER_MAX + p if p < 4 else None for p in range(OUTER_MAX)]
check(sr.index_of_slot(8, 12, table) == 8, "槽位 8（外圈第 0 格）-> 下标 8", str(sr.index_of_slot(8, 12, table)))
check(sr.index_of_slot(11, 12, table) == 11, "槽位 11（外圈第 3 格）-> 下标 11")
check(sr.index_of_slot(12, 12, table) is None, "槽位 12 空着 -> None")

# 关键回归：外圈靠后的位置有音效时，旧代码会拿槽位号 12 直接当 order 下标（越界）
sparse = [None] * OUTER_MAX
sparse[4] = 11          # 外圈第 4 格放着第 12 个音效
check(sr.index_of_slot(12, 12, sparse) == 11,
      "槽位 12 -> 下标 11（不是 12，也不是 None）", str(sr.index_of_slot(12, 12, sparse)))
check(sr.index_of_slot(8, 12, sparse) is None, "同一张表里槽位 8 是空的")

print("\n=== 3. 边界 ===")
check(sr.index_of_slot(19, 20, sparse) is None, "最后一个外圈位置空着 -> None")
check(sr.index_of_slot(25, 20, sparse) is None, "槽位号超过 19 -> None")
check(sr.index_of_slot(20, 20, sparse) is None, "槽位 20 不存在 -> None")

print("\n=== 4. 不给摆位表时按顺序兜底 ===")
check(sr.index_of_slot(8, 12, None) == 8, "9~12 个音效时外圈按顺序从第 0 格排")
check(sr.index_of_slot(11, 12, None) == 11, "第 4 个外圈格子 -> 下标 11")
check(sr.index_of_slot(12, 12, None) is None, "外圈排完之后的位置 -> None")
check(sr.index_of_slot(8, 8, None) is None, "只有 8 个音效时外圈整圈都是空的")

print("\n=== 5. 和轮盘上的真实结算对得上 ===")
# 用的还是上面那张 sparse 表：只有外圈第 4 格有音效（下标 11）
for sid, expect in ((0, 0), (3, 3), (8, None), (12, 11)):
    got = sr.index_of_slot(sid, 12, sparse if sid >= 8 else None)
    check(got == expect, f"槽位 {sid} 换算结果一致", f"got={got} expect={expect}")

print()
if fails:
    print(f"[XX] 有 {len(fails)} 项不通过：")
    for f in fails:
        print("   -", f)
    sys.exit(1)
print("[OK] 全部通过")
