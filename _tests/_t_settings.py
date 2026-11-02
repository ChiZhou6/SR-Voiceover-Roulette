"""配置窗口的数据逻辑测试（不碰用户真实的 sounds.json）。

覆盖：
  1. 首次运行把磁盘文件全数上盘
  2. 之后新文件不自动上盘（手动挑选语义）
  3. place / move / remove 的边界行为
  4. 窗口里的拖放回调能正确改写顺序并刷新
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402
from sounds_config import SoundsConfig  # noqa: E402

FAILS: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAILS.append(label)


def test_sync_semantics() -> None:
    print("\n1. 上盘语义（首次全上，之后手动）")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "sounds.json"

        a = SoundsConfig(p)
        a.load()
        order = a.sync(["a.wav", "b.wav"])
        check(order == ["a.wav", "b.wav"], "首次运行：磁盘文件全部上盘", str(order))
        a.save()

        b = SoundsConfig(p)
        b.load()
        order = b.sync(["a.wav", "b.wav", "c.wav"])
        check(order == ["a.wav", "b.wav"], "再次运行：新文件不会自动上盘", str(order))

        order = b.sync(["a.wav"])
        check(order == ["a.wav"], "磁盘上删掉的文件自动下盘", str(order))


def test_place_move_remove(real_files: list[str]) -> None:
    print("\n2. 放置 / 移动 / 移除")
    with tempfile.TemporaryDirectory() as td:
        scfg = SoundsConfig(Path(td) / "sounds.json")
        scfg.load()
        scfg.sync(real_files)          # 全部上盘
        names = list(real_files)

        first, second = names[0], names[1]
        check(scfg.place(second, 0) is True, "已在盘上的音效可以挪位置")
        check(scfg.order[0] == second, "挪到了第 0 位", scfg.order[0])

        check(scfg.remove(first) is None, "移除不报错")
        check(first not in scfg.order, "移除后不再出现在轮盘")

        check(scfg.add(first, 1) is True, "可以重新添加")
        check(scfg.order[1] == first, "加到了指定位置", scfg.order[1])

        check(scfg.add(first) is False, "重复添加不会产生副本")
        check(scfg.order.count(first) == 1, "轮盘里该音效只有一份")

        n = len(scfg.order)
        check(scfg.move(0, n - 1) is True, "内部拖动可以移动")
        check(scfg.order[-1] == second, "移动结果正确", scfg.order[-1])

        check(scfg.move(0, 0) is False, "拖到自己身上不算变化")
        check(scfg.move(99, 0) is False, "越界索引被拒绝")

        check(scfg.place("不存在.wav", 0) is True, "未上盘的名字也能放置（配置层不校验文件）")


def test_window_ops(real_files: list[str]) -> None:
    print("\n3. 窗口拖放回调")
    app = QApplication.instance() or QApplication(sys.argv[:1])  # noqa: F841

    with tempfile.TemporaryDirectory() as td:
        scfg = SoundsConfig(Path(td) / "sounds.json")
        scfg.load()
        scfg.sync(real_files)

        bank = sr.SoundBank(16, scfg)
        from settings_window import SettingsWindow

        w = SettingsWindow(dict(sr.load_config()), scfg, bank)
        w.setAttribute(Qt.WA_DontShowOnScreen, True)
        w.show()
        app.processEvents()

        before = len(w.bank)

        # v0.5.8 回归：外圈格拖回音效库曾经完全没反应。
        # 用户场景是 12 个音效、外圈有音效落在靠后的位置（槽位 12）：
        # 旧代码把这个槽位号直接当 order 下标（0 <= 12 < 12 不成立）就被挡掉，
        # 一格都删不动。这里先把外圈第 0 格挪到第 4 格，再按槽位 12 删。
        if len(w.bank) > sr.INNER_MAX:
            w._on_slot_dropped(sr.INNER_MAX, sr.INNER_MAX + 4)
            app.processEvents()
            table = sr.outer_index_map_of(w.bank)
            if table[4] is not None:
                victim_outer = scfg.order[table[4]]
                n_outer = len(w.bank)
                w._on_slot_removed(sr.INNER_MAX + 4)
                app.processEvents()
                check(
                    len(w.bank) == n_outer - 1,
                    "外圈靠后的格子（槽位 12）拖回音效库 -> 下盘成功",
                    f"{n_outer} -> {len(w.bank)}",
                )
                check(
                    victim_outer not in scfg.order,
                    "下盘的是那一格原本的音效",
                    victim_outer,
                )
                before = len(w.bank)
            else:
                check(False, "外圈摆位准备失败，后面的移除用例不可信")

        # 从库里拖一个已经不在盘上的名字？这里用移除再放回来模拟
        victim = w.bank.items[0].name
        w._on_slot_removed(0)
        app.processEvents()
        check(len(w.bank) == before - 1, "拖回音效库 -> 槽位减少", f"{len(w.bank)}")
        check(victim not in scfg.order, "该音效已下盘", victim)

        # v0.5.4 起：拖到格子上是"替换"，拖到中心才是"追加"
        displaced = scfg.order[0]
        w._on_lib_dropped(victim, 0)
        app.processEvents()
        check(len(w.bank) == before - 1, "拖到格子 = 替换，槽位数不变", f"{len(w.bank)}")
        check(scfg.order[0] == victim, "被拖入的音效占住第 0 位", scfg.order[0])
        check(displaced not in scfg.order, "原来那一格被换下场", displaced)

        from settings_window import ADD_TO_END
        w._on_lib_dropped(displaced, ADD_TO_END)
        app.processEvents()
        check(len(w.bank) == before, "拖到中心 = 追加", f"{len(w.bank)}")
        check(scfg.order[-1] == displaced, "追加到末尾", scfg.order[-1])

        if len(w.bank) >= 3:
            n0, n1, n2 = scfg.order[0], scfg.order[1], scfg.order[2]
            w._on_slot_dropped(0, 2)
            app.processEvents()
            # v0.5.5 起是"两格互换"，不是"整体挪动一格"
            check(scfg.order[2] == n0, "轮盘内拖动交换位置生效", scfg.order[2])
            check(scfg.order[0] == n2, "被换过来的音效落在原位置", scfg.order[0])
            check(scfg.order[1] == n1, "中间那一格不受影响", scfg.order[1])

        check(w.lbl_count.text().startswith(str(len(w.bank))),
              "槽位计数跟随变化", w.lbl_count.text())

        w.hide()


def test_speed_ui(real_files: list[str]) -> None:
    print("\n4. 变速控件（v0.6.1）")
    app = QApplication.instance() or QApplication(sys.argv[:1])

    with tempfile.TemporaryDirectory() as td:
        scfg = SoundsConfig(Path(td) / "sounds.json")
        scfg.load()
        scfg.sync(real_files)
        bank = sr.SoundBank(16, scfg)
        from settings_window import SettingsWindow

        w = SettingsWindow(dict(sr.load_config()), scfg, bank)
        w.setAttribute(Qt.WA_DontShowOnScreen, True)
        w.show()
        app.processEvents()

        d = w.detail
        d.set_sound(scfg.order[0])
        app.processEvents()

        check(
            [d.speed_mode.itemText(i) for i in range(d.speed_mode.count())]
            == ["不改变速度", "连续播放时加快", "连续播放时变慢"],
            "速度下拉有三个选项",
        )
        check(d.speed_mode.currentText() == "不改变速度", "新音效默认不改速度")

        # 选"加快 + 每次 10%"，配置里要立刻写上
        name = scfg.order[0]
        d.speed_mode.setCurrentIndex(1)
        d.speed_step.setCurrentIndex(2)
        app.processEvents()
        st = scfg.setting(name)
        check(st.speed_mode == "up", "选中加快写回配置", st.speed_mode)
        check(abs(st.speed_step - 0.10) < 1e-9, "每次 10% 写回配置", str(st.speed_step))

        # 换一个音效再换回来，控件要显示存下来的值（不是默认值）
        d.set_sound(scfg.order[1])
        app.processEvents()
        d.set_sound(name)
        app.processEvents()
        check(d.speed_mode.currentData() == "up", "重新选中后回显加快")
        check(abs(float(d.speed_step.currentData()) - 0.10) < 1e-9, "重新选中后回显 10%")

        # 降速方向也要能存
        d.speed_mode.setCurrentIndex(2)
        app.processEvents()
        check(scfg.setting(name).speed_mode == "down", "选中变慢写回配置")

        # 连击窗口的显隐：随机变调 + 速度关 -> 藏起来；速度开 -> 留着（速度要用）
        d.pitch_mode.setCurrentIndex(d.pitch_mode.findData("random"))
        d.speed_mode.setCurrentIndex(0)
        app.processEvents()
        check(not d.pitch_window.isVisible(), "随机变调且不开速度 -> 连击窗口隐藏")
        check(d.lbl_rand_hint.isVisible(), "此时显示随机变调的说明文字")
        d.speed_mode.setCurrentIndex(1)
        app.processEvents()
        check(d.pitch_window.isVisible(), "开了速度 -> 连击窗口必须留着（速度共用它）")
        check(not d.lbl_rand_hint.isVisible(), "说明文字让位给窗口")

        # 面板高度要够：加了这一行之后曾经被压扁过
        d.set_sound(name)
        app.processEvents()
        check(
            d.height() >= d.sizeHint().height(),
            "详情面板高度够（没被压扁）",
            f"{d.height()} >= {d.sizeHint().height()}",
        )


def main() -> int:
    print("=" * 56)
    print("配置窗口数据逻辑测试")
    print("=" * 56)

    # 取前 16 个：库里文件可以比轮盘多（27 个文件、20 个格子是常态），
    # 而这些用例假设"还能再摆几个上去"，整整取满 20 会让 add() 一直被上限挡住。
    # 16 既够用到外圈第 12 格，又留了 4 个空位给"添加"类断言。
    files = sorted(
        p.name for p in sr.SOUNDS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in sr.AUDIO_EXTS
    )[: sr.MAX_SLOTS - 4] if sr.SOUNDS_DIR.exists() else []
    if len(files) < 3:
        print(f"sounds 里只有 {len(files)} 个音效，测试需要至少 3 个")
        return 1
    print(f"使用 {len(files)} 个真实音效做样本")

    test_sync_semantics()
    test_place_move_remove(files)
    test_window_ops(files)
    test_speed_ui(files)

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
