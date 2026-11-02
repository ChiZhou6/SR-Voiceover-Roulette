"""sounds.json 与磁盘的同步规则测试（改名 / 清空 / 首次运行 / 参数迁移）。"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sounds_config import SoundsConfig  # noqa: E402

FAILS: list[str] = []


def check(ok: bool, what: str, detail: str = "") -> None:
    print(f"  {'[OK]' if ok else '[XX]'} {what}" + (f"  ({detail})" if detail else ""))
    if not ok:
        FAILS.append(what)


def make(order, items, names, initialized=True):
    tmp = Path(tempfile.mkdtemp())
    p = tmp / "sounds.json"
    if initialized:
        p.write_text(json.dumps({"version": 1, "order": order, "items": items},
                                ensure_ascii=False), encoding="utf-8")
    c = SoundsConfig(p)
    c.load()
    got = c.sync(names)
    return c, got, p


on_disk = ["01 冰冰冰.wav", "02 饿啊.wav", "03 真的很帅.wav",
           "04 男人叹气声2.wav", "05 哇哦.wav"]

print("=== 1. 用户在文件夹里加了序号前缀 ===")
old_order = ["冰冰冰.wav", "男人叹气声.wav", "哇哦.wav", "饿啊.wav", "真的很帅.wav"]
c, got, _ = make(old_order, {}, on_disk)
check(len(got) == 5, "五个都被认回来", str(got))
check(got[0] == "01 冰冰冰.wav", "位置保持：第一个还是冰冰冰", got[0])
check(got[1] == "04 男人叹气声2.wav", "位置保持：第二个还是叹气（名字带 2 也认）", got[1])
check(got[4] == "03 真的很帅.wav", "位置保持：最后一个还是很帅", got[4])

print("\n=== 2. 名字完全对不上，不应把轮盘清空 ===")
c, got, _ = make(["完全不存在A.wav", "完全不存在B.wav"], {}, on_disk)
check(len(got) == 5, "回落为全量上盘", str(len(got)))

print("\n=== 3. 用户主动清空轮盘，要保持空 ===")
c1, got1, p = make(on_disk, {}, on_disk)
check(len(got1) == 5, "先正常上盘", str(len(got1)))
c1.remove(on_disk[0]); c1.remove(on_disk[1]); c1.remove(on_disk[2])
c1.remove(on_disk[3]); c1.remove(on_disk[4])
c1.save()
c2 = SoundsConfig(p)
c2.load()
got2 = c2.sync(on_disk)
check(got2 == [], "重新载入后仍然是空", str(got2))

print("\n=== 4. 删掉其中几个文件 ===")
c, got, _ = make(on_disk, {}, ["01 冰冰冰.wav", "05 哇哦.wav"])
check(got == ["01 冰冰冰.wav", "05 哇哦.wav"], "只剩存在的那两个", str(got))

print("\n=== 5. 新文件不自动上盘 ===")
c, got, _ = make(["01 冰冰冰.wav"], {}, on_disk)
check(got == ["01 冰冰冰.wav"], "只有老的那个，其余不动", str(got))

print("\n=== 6. 首次运行（没有 sounds.json）全量上盘 ===")
c, got, _ = make([], {}, on_disk, initialized=False)
check(len(got) == 5, "全量上盘", str(len(got)))

print("\n=== 7. 参数字典的键跟着改名一起迁移 ===")
items = {
    "冰冰冰.wav": {"volume": 0.6, "hotkey": "v"},
    "冰冰冰": {"volume": 0.7},   # 老版本写成去扩展名的键
}
c, got, _ = make(["冰冰冰.wav"], items, on_disk)
check("01 冰冰冰.wav" in c.items, "参数挂到了新文件名下", str(list(c.items)))
check(abs(c.setting("01 冰冰冰.wav").volume - 0.6) < 1e-6,
      "参数值保留", str(c.setting("01 冰冰冰.wav").volume))
check(c.setting("01 冰冰冰.wav").hotkey == "v", "快捷键保留")
# 用去扩展名的名字也能取到同一份
check(c.setting("01 冰冰冰") is c.setting("01 冰冰冰.wav"), "stem 和全名指向同一份参数")

print("\n=== 8. canon：大小写/前缀混用都能找到 ===")
check(c.canon("01 冰冰冰.wav") == "01 冰冰冰.wav", "全名直接命中")
check(c.canon("01 冰冰冰") == "01 冰冰冰.wav", "去扩展名命中")

print("\n结果:", "全部通过" if not FAILS else f"{len(FAILS)} 项失败")
for f in FAILS:
    print("  -", f)
raise SystemExit(0 if not FAILS else 1)
