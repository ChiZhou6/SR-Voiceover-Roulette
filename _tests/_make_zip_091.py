"""一次性：重打发布 zip。

要点（踩过的坑都在这儿）：
- 默认 sounds.json 不能直接用仓库里那份（上面是用户自己的 12 个音效 + 私人设置），
  用上一版 zip 里的默认配置过一遍 SoundsConfig，新字段自动补默认值。
- 先写临时 zip，全部校验通过再 shutil.move 覆盖目标 —— 绝不直接往目标路径写。
"""

import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sounds_config import SoundsConfig  # noqa: E402

VER = "v0.9.1"
PREV_ZIP = ROOT / "SR Voiceover Roulette v0.9.0.zip"
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
    # ---- 1. 输入检查：全都得在，缺一个就停 ----
    need = [PREV_ZIP, EXE, DOC] + [ROOT / "sounds" / w for w in WAVS]
    missing = [str(p) for p in need if not p.exists()]
    if missing:
        print("缺文件，中止：")
        for m in missing:
            print("  ", m)
        return 1

    # ---- 2. 默认 sounds.json：以上一版为底，走一遍配置类补新字段 ----
    tmp = Path(tempfile.mkdtemp(prefix="sr_zip_"))
    base = tmp / "sounds.json"
    with zipfile.ZipFile(PREV_ZIP) as z:
        prev_name = next(n for n in z.namelist() if n.endswith("/sounds.json"))
        base.write_bytes(z.read(prev_name))

    scfg = SoundsConfig(base)
    scfg.load()
    scfg.save()
    data = json.loads(base.read_text(encoding="utf-8"))

    items = data.get("items", {})
    print(f"默认配置：version={data.get('version')} 音效 {len(items)} 个 "
          f"轮盘 {[w.get('name') for w in data.get('wheels', [])]}")
    assert len(items) == 12, f"默认配置音效数量不对：{len(items)}"
    assert all(not v.get("hotkey") for v in items.values()), "默认配置里不该有快捷键"
    assert "stop_prev" in next(iter(items.values())), "新字段 stop_prev 没写进去"
    assert not data.get("combos"), "默认配置不该有组合"

    # ---- 3. 往临时 zip 里写 ----
    tmp_zip = tmp / "out.zip"
    entries = [(f"{FOLDER}/sounds.json", base.read_bytes()),
               (f"{FOLDER}/SR Voiceover Roulette.exe", EXE.read_bytes()),
               (f"{FOLDER}/使用说明.txt", DOC.read_bytes())]
    for w in WAVS:
        entries.append((f"{FOLDER}/sounds/{w}", (ROOT / "sounds" / w).read_bytes()))

    with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for name, blob in entries:
            z.writestr(name, blob)

    # ---- 4. 读回来校验 ----
    with zipfile.ZipFile(tmp_zip) as z:
        bad = z.testzip()
        assert bad is None, f"zip 损坏：{bad}"
        names = z.namelist()
        assert len(names) == 15, f"条目数 {len(names)}，应为 15"
        got_exe = z.read(f"{FOLDER}/SR Voiceover Roulette.exe")
        got_json = json.loads(z.read(f"{FOLDER}/sounds.json"))
        got_doc = z.read(f"{FOLDER}/使用说明.txt")
        wav_ok = all(z.read(f"{FOLDER}/sounds/{w}") == (ROOT / "sounds" / w).read_bytes()
                     for w in WAVS)

    assert md5(got_exe) == md5(EXE.read_bytes()), "zip 里的 exe 和发布版不一致"
    assert wav_ok, "有 wav 内容对不上"
    assert b"NumLock" in got_doc, "说明书不是最新版"
    assert len(got_json.get("items", {})) == 12

    print(f"zip 内 exe md5: {md5(got_exe)}")
    print(f"zip 大小: {tmp_zip.stat().st_size:,} B")

    # ---- 5. 覆盖目标 ----
    shutil.move(str(tmp_zip), str(TARGET))
    print(f"已生成 {TARGET.name}  ({TARGET.stat().st_size:,} B)")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
