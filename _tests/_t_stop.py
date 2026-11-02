"""中空区域松手 = 停止播放（v0.5.3）。

三件事要验：
  1. 混音器 stop_all 是"短淡出"而不是硬切（硬切会有爆音）
  2. 轮盘开着、指针在中空区域松手 → 正在响的声音被停掉，且不播新的
  3. 指针在扇区上松手 → 照旧播放，不会误停
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np                                                # noqa: E402
from PySide6.QtWidgets import QApplication                        # noqa: E402

import sr_roulette as sr                                          # noqa: E402

FAILS: list[str] = []


def check(ok: bool, what: str, detail: str = "") -> None:
    print(f"  {'[OK]' if ok else '[XX]'} {what}" + (f"  ({detail})" if detail else ""))
    if not ok:
        FAILS.append(what)


class FakeRaw:
    registered = True

    def take(self):
        return 0, 0

    def drop(self) -> None:
        pass

    def button_down(self, name: str) -> bool:
        return False


def pcm(data: bytes, ch: int) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float32).reshape(-1, ch)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    fmt = sr._target_format()
    rate, ch = fmt.sampleRate(), fmt.channelCount()

    # ---------------------------------------------------------------
    print("=== 1. 停止是短淡出，不是硬切 ===")
    mixer = sr.Mixer(fmt)
    mixer.volume = 1.0
    clip = np.full((rate, ch), 0.5, dtype=np.float32)   # 1 秒恒定信号，方便看包络
    mixer.trigger(clip, 1.0)

    bpf = ch * 4
    first = pcm(mixer.readData(bpf * 480), ch)          # 先正常放 10ms
    check(np.abs(first).max() > 0.4, "停止前有声音", f"峰值 {np.abs(first).max():.2f}")

    mixer.stop_all()                                    # 默认 12ms 淡出
    heard = []
    for _ in range(40):                                 # 最多再读 40×128 帧
        seg = pcm(mixer.readData(bpf * 128), ch)
        heard.append(seg)
        if not mixer.playing:
            break
    tail = np.concatenate(heard, axis=0)
    nz = np.nonzero(np.abs(tail[:, 0]) > 1e-6)[0]
    total = int(nz[-1]) + 1 if len(nz) else 0
    want = max(1, int(rate * 0.012))
    check(total <= want + 128, "停止后 12ms 内收干净",
          f"{total} 帧 / 预期≈{want} 帧")
    check(np.abs(tail[0, 0] - 0.5) < 0.02, "第一帧是原幅度（说明是淡出不是一刀切）",
          f"{tail[0, 0]:.3f}")
    check(abs(float(tail[total - 1, 0])) < 0.02, "最后一帧接近 0（结尾没蹦台阶）",
          f"{tail[total - 1, 0]:.3f}")
    check(not mixer.playing, "停止后没有残留声部")

    print("\n=== 2. 没有声部时 stop_all 不该报错 ===")
    mixer.stop_all()
    mixer.stop_all()
    check(True, "空列表连调两次 stop_all 正常")

    # ---------------------------------------------------------------
    print("\n=== 3. 轮盘中空区域松手 → 停止播放 ===")
    cfg = dict(sr.DEFAULT_CONFIG)
    cfg["hotkey"] = "y"
    cfg["tap_action"] = "repeat_last"
    cfg["hold_ms"] = 120
    scfg = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
    scfg.load()
    bank = sr.SoundBank(16, scfg)
    check(len(bank) > 0, "音效库非空", f"{len(bank)} 个")
    audio = sr.AudioEngine(bank, cfg)
    wheel = sr.WheelController(cfg, bank, FakeRaw(), audio)
    poller = sr.InputPoller(cfg, wheel, audio)

    held = {"y": False}
    poller._down = lambda name: held.get(name, False)
    played: list = []
    audio.play = lambda idx: (played.append(idx), True)[1]

    def run(ms: int) -> None:
        t = time.monotonic()
        while (time.monotonic() - t) * 1000 < ms:
            poller.tick()
            time.sleep(0.005)

    def make_noise() -> None:
        """塞一个 5 秒的假声部到混音器里，代表"有个音效正在响"。"""
        audio.mixer.voices.append(
            [np.full((rate * 5, ch), 0.2, dtype=np.float32), 0, 1.0, 0]
        )

    make_noise()
    check(audio.playing and wheel.widget.playing is not None, "混音器里有声部")

    held["y"] = True
    run(250)                                   # 长按 → 弹轮盘
    check(wheel.active, "长按弹出轮盘")
    check(wheel.widget.playing, "轮盘知道现在有声音在响（提示文案会变成「停止播放」）")

    wheel.vx = wheel.vy = 0.0                  # 指针就在正中间
    wheel.poll_selection()
    check(wheel.selected is None, "中空区域 = 没选中任何扇区", str(wheel.selected))

    held["y"] = False
    run(40)
    check(not wheel.active, "松手后轮盘关闭")
    check(all(v[3] > 0 for v in audio.mixer.voices) or not audio.mixer.voices,
          "收到停止指令：声部进入淡出",
          str([v[3] for v in audio.mixer.voices]))
    # 淡出要 12ms 才走完，得有人拉数据（游戏里是声卡在拉）
    for _ in range(40):
        audio.mixer.readData(ch * 4 * 256)
        if not audio.playing:
            break
    check(not audio.playing, "正在响的声音被停掉了")
    check(played == [], "中空区域不会播放新音效", str(played))

    print("\n=== 4. 指针在扇区上松手 → 照旧播放，不误停 ===")
    make_noise()
    held["y"] = True
    run(250)
    wheel.vx = float(cfg["wheel_radius"]) * 0.6
    wheel.vy = 0.0
    wheel.poll_selection()
    check(wheel.selected is not None, "指针推出中空区域后有选中扇区",
          str(wheel.selected))
    held["y"] = False
    run(40)
    check(played != [], "播放了新音效", str(played))
    check(audio.playing, "没有顺手把音效掐掉")

    print("\n=== 5. 提示文案跟着状态走 ===")
    w = sr.WheelWidget(cfg)
    w.bank = bank
    w.playing = True
    src = Path(ROOT / "sr_roulette.py").read_text(encoding="utf-8")
    check('"松开停止播放" if self.playing else "松开取消"' in src,
          "中空区域文案分两态")

    print("\n" + ("全部通过" if not FAILS else f"{len(FAILS)} 项失败: {FAILS}"))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
