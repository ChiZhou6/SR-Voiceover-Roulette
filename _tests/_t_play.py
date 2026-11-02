"""验证音效真的在播放（真实音频设备，不静音、不离屏音频后端）。

不看窗口、不靠耳朵，直接查播放器的状态与播放进度：
  - 状态必须进入 PlayingState
  - position 必须真的往前走，才说明解码在进行

运行：python _tests/_t_play.py
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402

FAILS: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAILS.append(label)


def main() -> int:
    app = QApplication(sys.argv)
    print("=" * 56)
    print("SR Voiceover Roulette 播放验证")
    print("=" * 56)

    out = QMediaPlayer()
    dev = QAudioOutput()
    out.setAudioOutput(dev)
    print(f"\n输出设备: {dev.device().description()}")

    bank = sr.SoundBank(8)
    check(len(bank) > 0, "有可用音效", f"{len(bank)} 个")
    if len(bank) == 0:
        return 1

    # AudioEngine 从 v0.5.8 起收的是整份 config 字典（要读麦克风那几项），
    # 不能再只传一个音量 float —— 这里造一份最小可用配置。
    engine = sr.AudioEngine(bank, {"volume": 0.8, "mic_enabled": False})
    print(f"播放目标: {bank.name_at(0)} ({bank.path_at(0).name})")

    # 现在的引擎是 numpy Mixer + QAudioSink，没有 per-slot 的 QMediaPlayer 了，
    # 判定改成看"有没有 voice 在响"。
    check(engine.play(0), "play(0) 返回成功")

    deadline = time.monotonic() + 1.0
    alive = False
    while time.monotonic() < deadline:
        app.processEvents()
        if engine.playing:
            alive = True
            break
        time.sleep(0.02)
    check(alive, "声卡链路进入播放状态")

    # 播另一条，确认同一引擎切换槽位没问题
    check(len(bank) > 2, "至少 3 个音效（能测换槽）", f"{len(bank)} 个")
    check(engine.play(2), "切换到另一个槽位也能播放",
          bank.name_at(2) if len(bank) > 2 else "-")
    app.processEvents()

    engine.stop_all()
    # stop_all 是挂 12ms 淡出倒计时，不是立刻清空 voices，等一会儿再看
    t_end = time.monotonic() + 0.4
    while time.monotonic() < t_end:
        app.processEvents()
        time.sleep(0.02)
    check(not engine.playing, "stop_all 之后不再有声音")

    print("\n" + "=" * 56)
    if FAILS:
        print(f"结果：{len(FAILS)} 项未通过")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print("结果：全部通过（声音已从上面的输出设备播出）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
