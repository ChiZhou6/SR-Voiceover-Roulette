"""鼠标按键绑定：结构体布局 + 录入 + 轮询判定 + 单击/长按区分 + 随机变调。"""

from __future__ import annotations

import ctypes
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt                                    # noqa: E402
from PySide6.QtTest import QTest                                 # noqa: E402
from PySide6.QtWidgets import QApplication                       # noqa: E402

import sr_roulette as sr                                         # noqa: E402

FAILS: list[str] = []


def check(ok: bool, what: str, detail: str = "") -> None:
    print(f"  {'[OK]' if ok else '[XX]'} {what}" + (f"  ({detail})" if detail else ""))
    if not ok:
        FAILS.append(what)


class FakeRaw:
    """替代 RawMouse：手工喂按键状态。"""

    registered = True

    def __init__(self) -> None:
        self.state = {k: False for k in sr.MOUSE_KEYS}

    def take(self):
        return 0, 0

    def drop(self) -> None:
        pass

    def button_down(self, name: str) -> bool:
        return self.state.get(name, False)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])

    # ---------------------------------------------------------------
    print("=== 1. RAWMOUSE 字节布局（v0.5.1 这里错了，鼠标键全是死的）===")
    check(sr.RAWMOUSE.usButtonFlags.offset == 4,
          "usButtonFlags 在偏移 4", str(sr.RAWMOUSE.usButtonFlags.offset))
    check(sr.RAWMOUSE.usButtonData.offset == 6,
          "usButtonData 在偏移 6", str(sr.RAWMOUSE.usButtonData.offset))
    check(sr.RAWMOUSE.lLastX.offset == 12,
          "lLastX 在偏移 12", str(sr.RAWMOUSE.lLastX.offset))
    check(ctypes.sizeof(sr.RAWMOUSE) == 24,
          "结构体 24 字节", str(ctypes.sizeof(sr.RAWMOUSE)))

    # 造一段按 C 布局排好的字节，再用程序里的结构体解析回来：
    # 左键按下(0x0001)、usButtonData=0、位移 (17, -9)
    blob = struct.pack("<H2xHHiiiI", 0, 0x0001, 0, 0, 17, -9, 0)
    parsed = ctypes.cast(blob, ctypes.POINTER(sr.RAWMOUSE)).contents
    check(parsed.usButtonFlags == 0x0001, "从真实字节里读出了左键按下",
          hex(parsed.usButtonFlags))
    check(parsed.lLastX == 17 and parsed.lLastY == -9, "位移没读错",
          f"{parsed.lLastX},{parsed.lLastY}")

    print("\n=== 2. 按键框能录入鼠标键 ===")
    from settings_window import KeyBox

    box = KeyBox("y")
    box.show()
    app.processEvents()
    box.edit.setFocus()
    app.processEvents()
    QTest.mouseClick(box.edit, Qt.RightButton)
    check(box.key_name == "mouse_right", "右键录入", box.key_name)
    check(box.text() == "鼠标右键", "显示名友好", box.text())
    QTest.mouseClick(box.edit, Qt.MiddleButton)
    check(box.key_name == "mouse_middle", "中键录入", box.key_name)
    QTest.mouseClick(box.edit, Qt.BackButton)
    check(box.key_name == "mouse_4", "侧键1 录入", box.key_name)
    QTest.mouseClick(box.edit, Qt.ForwardButton)
    check(box.key_name == "mouse_5", "侧键2 录入", box.key_name)
    QTest.mouseClick(box.edit, Qt.LeftButton)
    check(box.key_name == "mouse_5", "单击左键只聚焦，不改绑定", box.key_name)
    QTest.mouseDClick(box.edit, Qt.LeftButton)
    check(box.key_name == "mouse_left", "双击左键才录入", box.key_name)

    print("\n=== 3. 取消绑定（Delete + 可见的 ✕ 按钮）===")
    QTest.keyClick(box.edit, Qt.Key_Delete)
    check(box.key_name == "", "Delete 解除绑定", repr(box.key_name))
    check(not box.btn_clear.isEnabled(), "空着时 ✕ 是灰的")
    box.edit._apply("mouse_4")
    check(box.btn_clear.isEnabled(), "绑上键后 ✕ 亮起")
    box.btn_clear.click()
    check(box.key_name == "", "点 ✕ 解除绑定", repr(box.key_name))

    print("\n=== 4. Raw Input 按键位解析 ===")
    raw = sr.RawMouse()
    ev = sr.RAWMOUSE()
    ev.usButtonFlags = sr.RI_MOUSE_BUTTON_DOWN["mouse_4"]
    raw._on_raw(ev)
    check(raw.button_down("mouse_4"), "侧键1 按下")
    check(not raw.button_down("mouse_5"), "侧键2 没被误触")
    ev2 = sr.RAWMOUSE()
    ev2.usButtonFlags = sr.RI_MOUSE_BUTTON_DOWN["mouse_4"] << 1
    raw._on_raw(ev2)
    check(not raw.button_down("mouse_4"), "侧键1 松开")
    ev3 = sr.RAWMOUSE()
    ev3.usButtonFlags = sr.RI_MOUSE_BUTTON_DOWN["mouse_left"]
    raw._on_raw(ev3)
    check(raw.button_down("mouse_left"), "左键按下")

    print("\n=== 5. 呼出键绑成鼠标侧键，单击/长按 ===")
    cfg = dict(sr.DEFAULT_CONFIG)
    cfg["hotkey"] = "mouse_4"          # 侧键1
    cfg["tap_action"] = "repeat_last"
    cfg["hold_ms"] = 180
    scfg = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
    scfg.load()
    bank = sr.SoundBank(16, scfg)
    check(len(bank) > 0, "音效库非空（否则后面的播放测试没意义）", f"{len(bank)} 个")
    audio = sr.AudioEngine(bank, cfg)
    wheel = sr.WheelController(cfg, bank, FakeRaw())
    poller = sr.InputPoller(cfg, wheel, audio)
    poller.hotkey_name = "mouse_4"
    audio.last_idx = 2

    state = {"v": False}
    fake = wheel.raw
    fake.state["mouse_4"] = False
    orig_down = poller._down
    poller._down = lambda name: fake.state.get(name, False) if name in sr.MOUSE_KEYS else orig_down(name)

    def run(ms: int, step: int = 10) -> None:
        t = time.monotonic()
        while (time.monotonic() - t) * 1000 < ms:
            poller.tick()
            time.sleep(step / 1000)

    state["n"] = 0
    audio.play = lambda idx, token=0: state.__setitem__("n", state["n"] + 1) or True

    fake.state["mouse_4"] = True
    run(60)
    fake.state["mouse_4"] = False
    run(40)
    check(state["n"] == 1 and not wheel.active, "短按侧键 = 重播上一个", f"播放 {state['n']} 次")

    fake.state["mouse_4"] = True
    run(400)
    check(wheel.active, "长按侧键 = 弹轮盘")
    fake.state["mouse_4"] = False
    run(60)
    check(state["n"] == 1, "长按不额外触发轻按动作", f"播放 {state['n']} 次")

    print("\n=== 6. 默认配置就是「长按弹轮盘 / 单击重复」 ===")
    check(sr.DEFAULT_CONFIG["tap_action"] == "repeat_last", "默认 tap_action",
          sr.DEFAULT_CONFIG["tap_action"])
    check(sr.DEFAULT_CONFIG["hotkey"] == "y", "默认呼出键 Y")

    print("\n=== 7. 随机变调 ===")
    from sounds_config import PITCH_RANDOM, SoundSetting, PITCH_MODES
    check(PITCH_RANDOM in PITCH_MODES, "random 是合法模式")
    check(SoundSetting(pitch_mode="random").clamped().pitch_mode == "random",
          "手写 json 里的 random 不会被清成 none")

    audio2 = sr.AudioEngine(bank, dict(sr.DEFAULT_CONFIG))
    rolls = [audio2._roll_random(0, 3.0) for _ in range(60)]
    check(all(v == int(v) for v in rolls), "只抽整数半音", str(rolls[:8]))
    check(all(-3 <= v <= 3 for v in rolls), "范围不超出 ±3")
    pairs_ok = all(a != b for a, b in zip(rolls, rolls[1:]))
    check(pairs_ok, "相邻两次不重复")
    check(len(set(rolls)) >= 5, "取值够散", f"出现过 {len(set(rolls))} 种")

    st0 = bank.setting_at(0)
    st0.pitch_mode = PITCH_RANDOM
    st0.pitch_step = 2.0
    lengths: list[int] = []
    # slot 是 v0.9.0 条件停止用的：这里只是量波形长度，多收一个关键字就行
    audio2.mixer.trigger = (lambda clip, gain=1.0, token=0, **kw:
                            lengths.append(len(clip)) or True)
    for _ in range(6):
        audio2.play(0)
    check(len(set(lengths)) >= 2, "随机变调真的改变了波形长度（=音高）",
          str(lengths))

    st0.pitch_step = 0.0
    audio2._rnd_pitch.clear()
    lengths.clear()
    for _ in range(3):
        audio2.play(0)
    check(len(set(lengths)) == 1, "幅度 0 时不变调", str(lengths))
    st0.pitch_mode = "none"
    st0.pitch_step = 1.0

    print("\n结果:", "全部通过" if not FAILS else f"{len(FAILS)} 项失败")
    for f in FAILS:
        print("  -", f)
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
