"""确认：删掉的音效 / 下盘的音效不会被自动补回来。"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sounds_config import SoundsConfig  # noqa: E402

FAILS = []


def check(ok, what, detail=""):
    print(("PASS  " if ok else "FAIL  ") + what + (f"   [{detail}]" if detail and not ok else ""))
    if not ok:
        FAILS.append(what)


with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "sounds.json"
    disk = ["a.wav", "b.wav", "c.wav"]

    # 首次运行：全量上盘
    cfg = SoundsConfig(p)
    cfg.load()
    check(cfg.sync(disk) == disk, "首次运行：磁盘文件全部上盘")
    cfg.save()

    # 删掉一个文件（模拟用户在资源管理器里删除）
    cfg2 = SoundsConfig(p)
    cfg2.load()
    left = cfg2.sync(["a.wav", "c.wav"])
    check(left == ["a.wav", "c.wav"], "删掉文件后：轮盘只剩剩下的两个", str(left))
    cfg2.save()

    # 重启后再同步：绝不能把 b.wav 补回来
    cfg3 = SoundsConfig(p)
    cfg3.load()
    check(cfg3.sync(disk) == ["a.wav", "c.wav"],
          "重启后：被删的音效不会自动补回来", str(cfg3.order))

    # 手动下盘（文件还在）
    cfg3.remove("a.wav")
    cfg3.save()
    cfg4 = SoundsConfig(p)
    cfg4.load()
    check(cfg4.sync(disk) == ["c.wav"], "下盘的音效不会被补回", str(cfg4.order))

    # 新放进来的文件：也不会自动上盘
    check("d.wav" not in cfg4.sync(disk + ["d.wav"]),
          "新丢进目录的文件不会自动上盘", str(cfg4.order))
    cfg4.save()

    # 全清空之后再放文件：仍然不自动补
    cfg5 = SoundsConfig(p)
    cfg5.load()
    cfg5.sync(disk + ["d.wav"])
    for n in list(cfg5.order):
        cfg5.remove(n)
    cfg5.save()
    cfg6 = SoundsConfig(p)
    cfg6.load()
    check(cfg6.sync(disk + ["d.wav"]) == [], "轮盘清空后再启动也不会自动填满",
          str(cfg6.order))

    # 删掉 sounds.json = 重置：这时才恢复"全量上盘"
    p.unlink()
    cfg7 = SoundsConfig(p)
    cfg7.load()
    check(sorted(cfg7.sync(disk + ["d.wav"])) == sorted(disk + ["d.wav"]),
          "删掉 sounds.json 后才会全量重建（重置行为）", str(cfg7.order))

print()
if FAILS:
    print(f"失败 {len(FAILS)} 项：")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("全部通过")
