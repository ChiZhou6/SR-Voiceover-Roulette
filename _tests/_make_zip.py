"""重打发布 zip（默认读 sr_roulette.APP_VERSION，可用参数覆盖）。

用法：python _tests/_make_zip.py [v0.9.2]

要点：
- **不再打包 sounds.json**（v0.9.2 起）。包里带默认配置的话，用户解压覆盖旧目录
  时会把人家攒的轮盘布局和参数一起盖掉，看着就像"音效全没了"——这正是要修的 bug。
  没有它，首次运行会自动把 sounds 里的文件全排上轮盘，效果一样。
- 先写临时 zip，全部校验通过再 shutil.move 覆盖目标，绝不直接往目标路径写。
"""

import hashlib
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sr_roulette as sr  # noqa: E402

VER = sys.argv[1] if len(sys.argv) > 1 else sr.APP_VERSION
TARGET = ROOT / f"SR Voiceover Roulette {VER}.zip"
FOLDER = f"SR Voiceover Roulette {VER}"
EXE = ROOT / "SR Voiceover Roulette_发布版" / "SR Voiceover Roulette.exe"
DOC = ROOT / "使用说明.txt"

WAVS = [
    "冰冰冰.wav", "呦吼吼.wav", "哇哦.wav", "哎呦我去.wav", "嗯？.wav",
    "嘶吼（魔了）.wav", "巴哈哈哈哈哈.wav", "怒.wav", "爱音唐哭.wav",
    "男人叹气声.wav", "真的很帅.wav", "饿啊.wav",
]


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def main() -> int:
    need = [EXE, DOC] + [ROOT / "sounds" / w for w in WAVS]
    missing = [str(p) for p in need if not p.exists()]
    if missing:
        print("缺文件，中止：")
        for m in missing:
            print("  ", m)
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="sr_zip_"))
    tmp_zip = tmp / "out.zip"
    entries = [(f"{FOLDER}/SR Voiceover Roulette.exe", EXE.read_bytes()),
               (f"{FOLDER}/使用说明.txt", DOC.read_bytes())]
    for w in WAVS:
        entries.append((f"{FOLDER}/sounds/{w}", (ROOT / "sounds" / w).read_bytes()))

    with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for name, blob in entries:
            z.writestr(name, blob)

    with zipfile.ZipFile(tmp_zip) as z:
        assert z.testzip() is None, "zip 损坏"
        names = z.namelist()
        assert len(names) == 14, f"条目数 {len(names)}，应为 14（exe + 说明书 + 12 个 wav）"
        assert not any(n.endswith("sounds.json") for n in names), "包里不该再有 sounds.json"
        got_exe = z.read(f"{FOLDER}/SR Voiceover Roulette.exe")
        got_doc = z.read(f"{FOLDER}/使用说明.txt")
        wav_ok = all(z.read(f"{FOLDER}/sounds/{w}") == (ROOT / "sounds" / w).read_bytes()
                     for w in WAVS)

    assert md5(got_exe) == md5(EXE.read_bytes()), "zip 里的 exe 和发布版不一致"
    assert wav_ok, "有 wav 内容对不上"
    assert "NumLock" in got_doc.decode("utf-8", "replace"), "说明书不是最新版"

    size = tmp_zip.stat().st_size
    print(f"zip 内 exe md5: {md5(got_exe)}")
    print(f"zip 大小: {size:,} B")
    shutil.move(str(tmp_zip), str(TARGET))
    print(f"已生成 {TARGET.name}")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
