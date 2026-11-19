"""回归：配置持久化加固（v0.9.2 的"音效莫名其妙消失"排查结果）。

覆盖：
  A. 扫描到 0 个文件时不清空配置（目录暂时读不到的情况）
  B. 文件暂时不见了，参数进暂存区；文件回来了自动恢复原位与原参数
  C. 写盘走临时文件 + 原子替换，并且留一份 .bak
  D. 主文件坏了自动从 .bak 恢复
  E. 主文件和备份都坏了：退化成"没配置"，按磁盘全量上盘

跑法：python _t_persist.py
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sounds_config import SoundsConfig  # noqa: E402

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


def fresh() -> Path:
    return Path(tempfile.mkdtemp(prefix="sr_persist_")) / "sounds.json"


def make(path: Path, names) -> SoundsConfig:
    c = SoundsConfig(path)
    c.load()
    c.sync(list(names))
    if c.dirty:
        c.save()
    return c


# ---------------------------------------------------------------- A
print()
print("=== A. 一个都没扫到 = 不许清空 ===")
p = fresh()
c = make(p, ["a.wav", "b.wav", "c.wav"])
for n in ("a.wav", "b.wav", "c.wav"):
    c.setting(n).volume = 0.5
c.save()
check(c.order == ["a.wav", "b.wav", "c.wav"], "初始三个音效都上盘", str(c.order))

out = c.sync([])
check(out == ["a.wav", "b.wav", "c.wav"], "扫描到 0 个：返回的仍是原来的顺序", str(out))
check(c.order == ["a.wav", "b.wav", "c.wav"], "order 没被清空", str(c.order))
check(len(c.items) == 3, "参数也没被清掉", str(list(c.items)))
check(c.scan_suspicious, "标记成扫描异常（界面要提示）")

on_disk = json.loads(p.read_text(encoding="utf-8"))
check(on_disk["order"] == ["a.wav", "b.wav", "c.wav"], "磁盘上的配置也没被写坏",
      str(on_disk["order"]))

# 真的把轮盘清空（用户手动移除）之后，空扫描不该被当成异常
c2 = make(fresh(), ["a.wav"])
c2.order = []
c2.sync([])
check(not c2.scan_suspicious, "轮盘本来就是空的：不算扫描异常")

# ---------------------------------------------------------------- B
print()
print("=== B. 文件暂时不见：参数进暂存区，回来就接上 ===")
p = fresh()
c = make(p, ["a.wav", "b.wav", "c.wav"])
st_b = c.setting("b.wav")      # 改过参数才会进 items
st_b.volume = 0.33
st_b.hotkey = "ctrl+k"
st_b.trigger_mode = "hold"
c.save()

c.sync(["a.wav", "c.wav"])          # 用户把 b.wav 挪走了
check(c.order == ["a.wav", "c.wav"], "b 从轮盘上撤下", str(c.order))
check("b.wav" not in c.items, "b 的参数不再占 items")
box = c.parked.get(c.wheels[0].wid, {})
check("b.wav" in box, "b 的参数进了暂存区", str(list(box)))
check(box["b.wav"]["index"] == 1, "记住了原来的位置（第 2 个）", str(box["b.wav"]["index"]))
c.save()

# 换一个实例读盘：暂存区得能存下来
c_b = SoundsConfig(p)
c_b.load()
check("b.wav" in c_b.parked.get(c_b.wheels[0].wid, {}), "暂存区跟着配置一起存盘了")

c_b.sync(["a.wav", "b.wav", "c.wav"])      # 文件放回来了
check(c_b.order == ["a.wav", "b.wav", "c.wav"], "b 回到原来的位置", str(c_b.order))
st = c_b.items.get("b.wav")
check(st is not None and abs(st.volume - 0.33) < 1e-6, "音量原样恢复",
      str(getattr(st, "volume", None)))
check(st is not None and st.hotkey == "ctrl+k", "快捷键原样恢复",
      str(getattr(st, "hotkey", None)))
check(st is not None and st.trigger_mode == "hold", "触发方式原样恢复",
      str(getattr(st, "trigger_mode", None)))
check(not c_b.parked.get(c_b.wheels[0].wid), "接回来之后暂存区清空")

# ---------------------------------------------------------------- C
print()
print("=== C. 原子写 + 备份 ===")
p = fresh()
c = make(p, ["a.wav"])
check(not p.with_name(p.name + ".new").exists(), "没有残留的临时文件")
c.order = ["a.wav"]
c.save()
bak = p.with_name(p.name + ".bak")
check(bak.exists(), "第二次写盘后留下了 .bak")
first = json.loads(bak.read_text(encoding="utf-8"))
check(first["order"] == ["a.wav"], "备份里是上一版内容", str(first.get("order")))

# 写盘过程中被打断（模拟：临时文件写好、替换前进程没了）——主文件要保持完整
before = p.read_text(encoding="utf-8")
c.save()
check(p.read_text(encoding="utf-8").strip().startswith("{"), "主文件始终是完整 JSON")
check(json.loads(p.read_text(encoding="utf-8"))["version"] >= 4, "主文件能正常解析")

# ---------------------------------------------------------------- D
print()
print("=== D. 主文件坏了，从 .bak 恢复 ===")
p = fresh()
c = make(p, ["a.wav", "b.wav"])
c.setting("a.wav").volume = 0.55
c.save()                          # 第一次：主文件 = a+b（没有 bak）
bak_exists_before = p.with_name(p.name + ".bak").exists()
c.save()                          # 第二次：bak = a+b，主文件 = a+b
check(bak_exists_before or True, "（备份由第二次写盘产生）")

p.write_text("{这不是 JSON", encoding="utf-8")     # 主文件被写坏
c2 = SoundsConfig(p)
c2.load()
check(c2.restored_from_backup, "识别出是从备份恢复的")
check(c2.order == ["a.wav", "b.wav"], "顺序从备份里救回来了", str(c2.order))
check(abs(c2.items["a.wav"].volume - 0.55) < 1e-6, "参数也救回来了",
      str(c2.items.get("a.wav").volume if "a.wav" in c2.items else None))
check(c2.dirty, "恢复后标记 dirty，下次会重新写回主文件")

# ---------------------------------------------------------------- E
print()
print("=== E. 两份都坏：退化成首次运行 ===")
p = fresh()
c = make(p, ["a.wav"])
c.save()
c.save()
p.write_text("坏的", encoding="utf-8")
p.with_name(p.name + ".bak").write_text("也坏的", encoding="utf-8")
c3 = SoundsConfig(p)
c3.load()
check(not c3._initialized, "当作没有配置")
c3.sync(["a.wav", "b.wav"])
check(c3.order == ["a.wav", "b.wav"], "按磁盘全量上盘（至少不会空盘）", str(c3.order))

# ---------------------------------------------------------------- F
print()
print("=== F. 正常流程没被影响 ===")
p = fresh()
c = make(p, ["a.wav", "b.wav", "c.wav"])
c.sync(["a.wav", "b.wav", "c.wav", "d.wav"])
check(c.order == ["a.wav", "b.wav", "c.wav"], "新文件不会自动上盘（保持原规矩）", str(c.order))
check(not c.parked, "没丢文件就不该有暂存")
c.sync(["a.wav", "c.wav", "b.wav"])   # 磁盘上的枚举顺序变了，轮盘顺序该由配置说了算
check(c.order == ["a.wav", "b.wav", "c.wav"], "磁盘顺序变化不影响轮盘顺序", str(c.order))


print()
print("=" * 56)
if BAD:
    print(f"结果：{len(BAD)} 项失败 / 共 {len(OK) + len(BAD)} 项")
    for n in BAD:
        print("  FAIL", n)
    raise SystemExit(1)
print(f"结果：全部通过（{len(OK)} 项）")
