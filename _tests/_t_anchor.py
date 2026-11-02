"""验证轮盘弹出位置（真实平台，不显示窗口）。

两种 anchor 模式各测一次：
  screen -> 窗口中心必须等于屏幕中心（与鼠标停在哪无关）
  cursor -> 窗口中心必须等于光标坐标（保留的旧行为）
"""

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402

FAILS: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAILS.append(label)


class DummyRaw:
    registered = True

    def drop(self) -> None:
        pass

    def take(self) -> tuple[float, float]:
        return 0.0, 0.0


def set_cursor(x: int, y: int) -> None:
    ctypes.windll.user32.SetCursorPos(int(x), int(y))


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841

    screen = QApplication.primaryScreen()
    geo = screen.geometry()
    print(f"主屏 geometry: {geo.left()},{geo.top()} {geo.width()}x{geo.height()}")
    want = (geo.center().x(), geo.center().y())
    print(f"屏幕中心: {want}")

    def window_center(g) -> tuple[int, int]:
        """窗口的真实几何中心。
        不能用 QRect.center()：它对偶数宽度会少算 1 像素（half-open 特性），
        408 宽的窗口会报 left+203，而实际中心是 left+204。"""
        return (g.left() + g.width() // 2, g.top() + g.height() // 2)

    # 离屏幕边足够远，避免窗口被夹紧，这样才能测出"是否居中"本身
    off = (want[0] + 220, want[1] + 160)

    for anchor in ("screen", "cursor"):
        print(f"\nwheel_anchor = {anchor}")
        # 真实鼠标可能正在被移动，设定完再确认一次，别让抖动算成程序的问题
        for _ in range(5):
            set_cursor(*off)
            if sr.cursor_pos() == off:
                break

        cfg = dict(sr.DEFAULT_CONFIG)
        cfg["wheel_anchor"] = anchor
        cfg["wheel_radius"] = 180
        bank = sr.SoundBank(8)
        wc = sr.WheelController(cfg, bank, DummyRaw())
        wc.show_wheel()
        g = wc.widget.geometry()
        ctr = window_center(g)
        wc.hide_wheel()

        if anchor == "screen":
            check(ctr == want, "弹出中心 == 屏幕中心（与光标位置无关）",
                  f"{ctr} vs {want}")
            check(abs(ctr[0] - off[0]) > 100,
                  "不是跟着光标跑", f"光标 {off} 中心 {ctr}")
        else:
            # 期望值 = 光标坐标被"夹进屏幕"之后的结果：
            # 窗口必须整个落在屏内，光标太靠边时中心会被夹回来（正确行为）。
            # offscreen 虚拟屏幕很小，不夹期望值的话这个用例永远过不了。
            half = g.width() // 2
            ex = min(max(off[0], geo.left() + half), geo.right() - half)
            ey = min(max(off[1], geo.top() + half), geo.bottom() - half)
            near = abs(ctr[0] - ex) <= 2 and abs(ctr[1] - ey) <= 2
            check(near, "cursor 模式跟随光标（必要时夹进屏幕）",
                  f"{ctr} vs 期望({ex},{ey})")

    # 光标贴到屏幕右下角时，screen 模式也不该被夹到边上
    print("\n极端情况：光标顶到右下角")
    cfg = dict(sr.DEFAULT_CONFIG)
    cfg["wheel_anchor"] = "screen"
    cfg["wheel_radius"] = 180
    set_cursor(geo.right() - 2, geo.bottom() - 2)
    wc = sr.WheelController(cfg, sr.SoundBank(8), DummyRaw())
    wc.show_wheel()
    g = wc.widget.geometry()
    ctr = window_center(g)
    wc.hide_wheel()
    check(ctr == want, "屏幕中心不受光标影响", f"{ctr} vs {want}")

    # 恢复光标到屏幕中心，免得用户回来找不到鼠标
    set_cursor(*want)

    print("\n" + "=" * 52)
    if FAILS:
        print(f"结果：{len(FAILS)} 项未通过")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
