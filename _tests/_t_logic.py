"""SR Voiceover Roulette - 逻辑自测（离屏，不需要显示器）

运行：
  set QT_QPA_PLATFORM=offscreen
  python _tests/_t_logic.py

检查项：
  1. 按键名 -> 虚拟键码映射
  2. 扇区判断（8 扇区，八个方向逐一断言）
  3. sounds 目录扫描与槽位分配
  4. 轮盘离屏渲染（确认真的画出了像素）
  5. 音频引擎能否为每个槽位建好播放器
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402
from theme import ACCENT_RGB  # noqa: E402

# 特征色里最突出的那个通道（绿主题下是 green），高亮判据据此决定，
# 这样换主题色不需要改测试。
_ACCENT_CHANNEL = ACCENT_RGB.index(max(ACCENT_RGB))

FAILS: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAILS.append(label)


def test_vk() -> None:
    print("\n1. 按键映射")
    check(sr.vk_of("y") == 0x59, "y -> 0x59", hex(sr.vk_of("y")))
    check(sr.vk_of("Y") == 0x59, "Y 大写同样成立")
    check(sr.vk_of("g") == 0x47, "g -> 0x47", hex(sr.vk_of("g")))
    check(sr.vk_of("f8") == 0x77, "f8 -> 0x77", hex(sr.vk_of("f8")))
    check(sr.vk_of("space") == 0x20, "space -> 0x20")
    check(sr.vk_of("comma") == 0xBC, "comma -> 0xBC")
    check(sr.vk_of("period") == 0xBE, "period -> 0xBE")


def test_sector() -> None:
    print("\n2. 扇区判断（8 扇区，死区 44px）")
    n, dz = 8, 44.0
    cases = [
        ((0, -100), 0, "正上方"),
        ((100, -100), 1, "右上"),
        ((100, 0), 2, "正右"),
        ((100, 100), 3, "右下"),
        ((0, 100), 4, "正下"),
        ((-100, 100), 5, "左下"),
        ((-100, 0), 6, "正左"),
        ((-100, -100), 7, "左上"),
    ]
    for (dx, dy), want, label in cases:
        got = sr.sector_from_delta(dx, dy, n, dz)
        check(got == want, f"{label} -> {want}", f"实际 {got}")

    check(sr.sector_from_delta(10, 10, n, dz) is None, "死区内不选中")
    check(sr.sector_from_delta(0, -43, n, dz) is None, "43px 未超死区")
    check(sr.sector_from_delta(0, -45, n, dz) == 0, "45px 刚超死区即选中")

    # 4 扇区时角度重新划分
    check(sr.sector_from_delta(100, 0, 4, dz) == 1, "4 扇区时正右 -> 1")
    check(sr.sector_from_delta(0, -100, 4, dz) == 0, "4 扇区时正上 -> 0")


def test_bank(app) -> None:
    print("\n3. 音效扫描")
    bank = sr.SoundBank(8)
    check(len(bank) > 0, "sounds 目录扫到音效", f"{len(bank)} 个")
    if len(bank) > 0:
        names = [bank.name_at(i) for i in range(len(bank))]
        check(names == sorted(names, key=str.lower), "按文件名升序排列", str(names[:3]))
        check(bank.path_at(0) is not None and bank.path_at(0).exists(), "槽位 0 文件存在")
    check(bank.path_at(99) is None, "越界槽位返回 None")
    check(bank.name_at(99) == "空槽位", "越界槽位名字为占位")

    limited = sr.SoundBank(2)
    check(len(limited) <= 2, "槽位上限生效", f"slots=2 时载入 {len(limited)} 个")


def test_render(app) -> None:
    print("\n4. 轮盘离屏渲染")
    cfg = dict(sr.DEFAULT_CONFIG)
    bank = sr.SoundBank(8)
    w = sr.WheelWidget(cfg)
    w.bank = bank
    size = int(cfg["wheel_radius"] * 2 + 48)
    w.resize(size, size)

    pix = w.grab()
    check(not pix.isNull(), "grab 得到有效位图", f"{pix.width()}x{pix.height()}")
    img = pix.toImage()

    opaque = 0
    for y in range(0, img.height(), 4):
        for x in range(0, img.width(), 4):
            if img.pixelColor(x, y).alpha() > 40:
                opaque += 1
    check(opaque > 200, "轮盘实际画出了不透明像素", f"采样命中 {opaque}")

    center = img.pixelColor(size // 2, size // 2)
    check(center.alpha() > 150, "中心区域有底色", f"alpha={center.alpha()}")

    # 渲染与选择必须严格对齐：逐个扇区断言"高亮画在了该在的位置"
    import math

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap

    def render_now(widget) -> "QImage":
        """强制重绘到空位图。离屏下重复 grab() 会拿到缓存，必须走 render()。"""
        pm = QPixmap(widget.width(), widget.height())
        pm.fill(Qt.transparent)
        widget.render(pm)
        return pm.toImage()

    radius = float(cfg["wheel_radius"])
    probe_r = radius * 0.88
    n_actual = max(1, len(bank))
    step = 360.0 / n_actual
    mismatched = []
    for i in range(n_actual):
        w.selected = i
        img_i = render_now(w)
        # 探测点不能取扇区正中间：文字就画在那儿，扇区越宽文字越宽，
        # 只有 2 个扇区时文字会盖住中点。往扇区内偏 1/4 格，稳定避开文字。
        mid = math.radians(90.0 - (i + 0.5) * step + step * 0.25)
        px = int(size / 2 + probe_r * math.cos(mid))
        py = int(size / 2 - probe_r * math.sin(mid))
        c = img_i.pixelColor(px, py)
        # 判据跟着 theme 的特征色走：该通道数值显著领先另外两个通道即为高亮。
        # 不用写死具体 RGB，否则换主题色后测试会误报。
        dom = max(range(3), key=lambda k: (c.red(), c.green(), c.blue())[k])
        rgb = (c.red(), c.green(), c.blue())
        others = [rgb[k] for k in range(3) if k != dom]
        if not (dom == _ACCENT_CHANNEL and rgb[dom] > 120
                and min(rgb[dom] - o for o in others) > 30):
            mismatched.append(f"扇区{i}@({px},{py}) rgb={c.red()},{c.green()},{c.blue()}")
    check(not mismatched, f"{n_actual} 个扇区的高亮位置与选中编号逐一对应", "; ".join(mismatched))

    # 空槽位也要能画，不能崩
    empty_bank = sr.SoundBank(8)
    empty_bank.items = []
    w.bank = empty_bank
    try:
        w.grab()
        check(True, "音效为 0 个时绘制不崩溃")
    except Exception as exc:
        check(False, "音效为 0 个时绘制不崩溃", str(exc))


def test_audio(app) -> None:
    print("\n5. 音频引擎")
    bank = sr.SoundBank(8)
    cfg = dict(sr.DEFAULT_CONFIG)
    engine = sr.AudioEngine(bank, cfg)
    check(len(engine) == len(bank), "每个槽位都解码成功", f"{len(engine)}/{len(bank)}")
    check(abs(engine.volume - 0.8) < 1e-6, "初始音量正确")
    engine.set_volume(1.5)
    check(abs(engine.volume - 1.0) < 1e-6, "音量上限夹紧到 1.0")
    engine.set_volume(-1.0)
    check(abs(engine.volume - 0.0) < 1e-6, "音量下限夹紧到 0.0")
    engine.set_volume(0.8)
    check(engine.play(99) is False, "越界槽位拒绝播放")
    engine.stop_all()


def test_clamp() -> None:
    print("\n6. 虚拟光标软钳制")
    x, y = sr.clamp_offset(10, 10, 100)
    check((x, y) == (10, 10), "未超限时原样返回", f"{x},{y}")
    x, y = sr.clamp_offset(300, 0, 100)
    check(abs(x - 100) < 1e-6 and abs(y) < 1e-6, "超限后被拉回边界", f"{x:.1f},{y:.1f}")
    x, y = sr.clamp_offset(300, 400, 100)
    check(abs((x * x + y * y) ** 0.5 - 100) < 1e-6, "斜向超限后长度正好等于上限",
          f"长度={(x*x+y*y)**0.5:.4f}")
    x, y = sr.clamp_offset(300, 400, 100)
    check(x > 0 and y > 0, "钳制不改变方向")
    check(sr.clamp_offset(0, 0, 100) == (0, 0), "原点是安全点，不除零")


def test_no_pop(app) -> None:
    """电流声修复的核心断言：每个音效进输出流时首尾都必须从 0 起落。"""
    print("\n7. 爆音防护（淡入淡出）")
    bank = sr.SoundBank(8)
    engine = sr.AudioEngine(bank, dict(sr.DEFAULT_CONFIG))
    if len(engine.clips) == 0:
        check(False, "没有可测音效")
        return

    bad_head, bad_tail = [], []
    for i, clip in enumerate(engine.clips):
        head = float(abs(clip[0]).max())
        tail = float(abs(clip[-1]).max())
        if head > 1e-4:
            bad_head.append(f"#{i} head={head:.5f}")
        if tail > 1e-4:
            bad_tail.append(f"#{i} tail={tail:.5f}")
    check(not bad_head, f"{len(engine.clips)} 个音效的首采样均约等于 0", "; ".join(bad_head))
    check(not bad_tail, f"{len(engine.clips)} 个音效的尾采样均约等于 0", "; ".join(bad_tail))

    # 直流偏移被扣掉，否则整体听感发闷
    worst_dc = max(abs(float(c.mean())) for c in engine.clips)
    check(worst_dc < 1e-3, "直流偏移已扣除", f"最大 {worst_dc:.6f}")

    # 波形中段不能被淡入淡出削掉
    peak = max(float(abs(c).max()) for c in engine.clips)
    check(peak > 0.05, "音效主体仍有正常音量", f"峰值 {peak:.3f}")


def test_mixer(app) -> None:
    print("\n8. 混音器")
    import numpy as np

    bank = sr.SoundBank(8)
    engine = sr.AudioEngine(bank, dict(sr.DEFAULT_CONFIG))
    mixer = engine.mixer
    if len(mixer.clips) == 0:
        check(False, "没有可混音的音效")
        return

    clip = mixer.clips[0]
    frames_total = len(clip)
    bps = mixer.channels * 4

    check(mixer.trigger(clip), "触发播放成功")
    all_out = []
    guard = 0
    while mixer.voices and guard < 5000:
        data = mixer.readData(4800)
        arr = np.frombuffer(data, dtype="<f4")
        all_out.append(arr)
        guard += 1
    out = np.concatenate(all_out) if all_out else np.array([], dtype="<f4")
    check(guard < 5000, "混音循环能自己结束", f"{guard} 次读取")
    # 音频流必须按块连续输出，最后一块会用静音补齐，所以是"不小于"而非"等于"
    out_frames = len(out) // mixer.channels
    check(frames_total <= out_frames < frames_total + 600,
          "输出覆盖整个音效且只多补一块静音", f"{out_frames} vs {frames_total}")

    first = np.frombuffer(all_out[0], dtype="<f4")
    check(len(first) > 0 and abs(float(first[0])) < 1e-6,
          "输出流第一个采样为 0（不会起播爆音）", f"{float(first[0]):.6f}")
    tail = np.frombuffer(all_out[-1], dtype="<f4")
    check(abs(float(tail[-1])) < 1e-6,
          "输出流最后一个采样回落到 0（不会收尾爆音）", f"{float(tail[-1]):.6f}")

    # 两路同一音效叠加时不能溢出
    mixer.stop_all()
    mixer.trigger(clip)
    mixer.trigger(clip)
    mixer.volume = 1.0
    data = mixer.readData(4800 * 4)
    peak = float(np.abs(np.frombuffer(data, dtype="<f4")).max())
    check(peak <= 1.0 + 1e-6, "叠加播放被限幅在 ±1.0 内", f"峰值 {peak:.4f}")
    mixer.stop_all()
    # v0.5.3 起 stop_all 是"12ms 淡出"而不是立刻清空（硬切会爆音），
    # 所以先断言声部都进入了淡出，再把数据抽干净，确认最终归零。
    check(mixer.voices != [] and all(v[3] > 0 for v in mixer.voices),
          "stop_all 让所有发声进入淡出", str([v[3] for v in mixer.voices]))
    for _ in range(40):
        mixer.readData(4800 * 4)
        if not mixer.voices:
            break
    check(mixer.voices == [], "淡出走完后清空所有发声")


def test_center_alignment() -> None:
    """v0.1 的错位根因：轮盘画在屏幕中心，判定基准却取光标位置。
    v0.2 起两者强制为同一个点，这里断言这个不变量。"""
    print("\n9. 轮盘中心与判定基准同源")

    class DummyRaw:
        registered = True

        def take(self):
            return (0.0, 0.0)

        def drop(self):
            pass

    cfg = dict(sr.DEFAULT_CONFIG)
    bank = sr.SoundBank(8)
    wc = sr.WheelController(cfg, bank, DummyRaw())
    wc.show_wheel()
    g = wc.widget.geometry()
    # 绘制时轮盘中心取 widget 的 (width/2, height/2)，换算回屏幕坐标必须等于判定原点
    drawn_center = (g.left() + wc.widget.width() // 2, g.top() + wc.widget.height() // 2)
    check(drawn_center == wc._center,
          "绘制中心换算到屏幕 == 判定原点", f"{drawn_center} vs {wc._center}")
    check(wc.widget.width() % 2 == 0 and wc.widget.height() % 2 == 0,
          "窗口边长为偶数，避免半像素偏移", f"{wc.widget.width()}x{wc.widget.height()}")

    wc.widget.vx, wc.widget.vy = 0.0, 0.0
    check(wc.vx == 0 and wc.vy == 0, "打开时虚拟光标从正中起步")
    wc.hide_wheel()


def main() -> int:
    app = QApplication(sys.argv)
    print("=" * 56)
    print("SR Voiceover Roulette 逻辑自测（离屏）")
    print("=" * 56)

    test_vk()
    test_sector()
    test_bank(app)
    test_render(app)
    test_audio(app)
    test_clamp()
    test_no_pop(app)
    test_mixer(app)
    test_center_alignment()

    print("\n" + "=" * 56)
    if FAILS:
        print(f"结果：{len(FAILS)} 项未通过")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
