"""回归：音效快捷键的「全局通用」。

跑法：python _t_global_key.py

要钉住的是这一条：勾了「全局通用」的音效，切换到别的轮盘之后
按快捷键照样要响，而且音量/变调/长按方式还是它自己那套，不能退回默认。

五块：
  A 数据层——字段存在、老配置兼容、跨轮盘收集不串味
  B setting_any——当前轮盘优先，其次用"开全局那套"的原始参数
  C 音频引擎——不在当前轮盘上的全局音效要有一份可播放的副本
  D 按键绑定——全局键进得了 _by_key，撞上呼出轮盘键要让路
  E 设置页——勾选写盘、组合不显示、切换音效时跟着变
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import sr_roulette as sr  # noqa: E402
import sounds_config as sc  # noqa: E402

app = QApplication.instance() or QApplication([])

OK = []
BAD = []


def check(cond, name, detail=""):
    if cond:
        OK.append(name)
        print(f"PASS  {name}")
    else:
        BAD.append(name)
        print(f"FAIL  {name}   {detail}")


# ---------------------------------------------------------------- 沙箱
# SettingsWindow 里任何控件改动都会立刻写盘（见项目 MEMORY 里的教训），
# 所以配置路径必须先指到临时目录，再把真实文件复制进去。
TMP = Path(tempfile.mkdtemp(prefix="sr_gk_"))
shutil.copy2(ROOT / "config.json", TMP / "config.json")
shutil.copy2(ROOT / "sounds.json", TMP / "sounds.json")
sr.CONFIG_PATH = TMP / "config.json"
sr.SOUNDS_CONFIG_PATH = TMP / "sounds.json"
# 音效文件仍用真实的（只读，不需要复制）
print(f"沙箱: {TMP}")

all_keys = [k for k, _p in sr.scan_sound_files()]
print(f"磁盘上共有 {len(all_keys)} 个音效")


def fresh_scfg():
    """每次拿一份干净的两套轮盘配置。"""
    cfg = sr.SoundsConfig(TMP / "sounds.json")
    cfg.load()
    w1 = cfg.cur_wheel()
    w1.order = all_keys[:3]
    w1.outer_slots = [None] * sc.OUTER_MAX
    w1.items = {}
    # 第二套轮盘：放另一批音效，和第一套不重叠
    w2 = sc.WheelDef(wid="w2", name="轮盘 2")
    w2.order = all_keys[3:5]
    w2.items = {}
    cfg.wheels = [w1, w2]
    cfg._cur = "w1"
    return cfg


print("\n=== A. 数据层 ===")
st = sc.SoundSetting()
check(st.global_hotkey is False, "默认关（和以前行为一致）")

cfg = fresh_scfg()
a, b = cfg.order[0], cfg.order[1]
other = all_keys[4]          # 只在轮盘 2 上的音效
print(f"  轮盘1: {cfg.order}   轮盘2: {[all_keys[3], other]}")

# 老配置里没有这个字段，读出来必须是 False
old = sc.SoundSetting(volume=1.0, hotkey="f5")
check(old.clamped().global_hotkey is False, "老配置缺字段 -> 默认 False")

cfg.setting(a).hotkey = "f5"
cfg.setting(a).global_hotkey = True
cfg.setting(b).hotkey = "f6"          # 没开全局

g = cfg.global_hotkey_groups()
check(g.get("f5") == [a], "开了全局的音效进 global_hotkey_groups", str(g))
check("f6" not in g, "没开全局的不进跨轮盘表", str(g))

cfg.setting(a).hotkey = ""
check(cfg.global_hotkey_groups() == {}, "勾了全局却没绑键 -> 不收集（没键可按）")
cfg.setting(a).hotkey = "f5"

# 切到轮盘 2：轮盘内的绑定只剩 w2 的，全局的还在
cfg.switch_wheel("w2")
check(cfg.current == "w2", "已切到轮盘 2")
inside = cfg.hotkey_groups()
check("f5" not in inside, "hotkey_groups 只看当前轮盘（没被全局污染）", str(inside))
check(cfg.global_hotkey_groups().get("f5") == [a], "切换轮盘后全局键仍在", str(cfg.global_hotkey_groups()))

print("\n=== B. setting_any ===")
# 轮盘 1 里 a 的参数
cfg.switch_wheel("w1")
cfg.setting(a).volume = 0.37
cfg.setting(a).pitch_fixed = 3.5
cfg.setting(a).trigger_mode = sc.TRIGGER_HOLD
cfg.switch_wheel("w2")
got = cfg.setting_any(a)
check(abs(got.volume - 0.37) < 1e-6, "跨轮盘取到它自己那套音量", str(got.volume))
check(abs(got.pitch_fixed - 3.5) < 1e-6, "跨轮盘取到它自己那套变调", str(got.pitch_fixed))
check(got.trigger_mode == sc.TRIGGER_HOLD, "跨轮盘取到它自己那套触发方式", got.trigger_mode)

# 当前轮盘里也有这个音效时，用当前轮盘的
cfg.switch_wheel("w1")
cfg.setting(a).volume = 0.5
check(abs(cfg.setting_any(a).volume - 0.5) < 1e-6, "当前轮盘有就用当前轮盘的参数")

# 谁都没开全局的陌生键：给默认值，不能炸
stray = cfg.setting_any("不存在的音效.wav")
check(stray.volume == 1.0, "找不到的音效给默认参数，不抛异常")

print("\n=== C. 音频引擎 ===")
cfg = fresh_scfg()
a = cfg.order[0]
other = all_keys[4]
cfg.setting(a).hotkey = "f5"
cfg.setting(a).global_hotkey = True
cfg.setting(a).volume = 0.42
# 让 only-轮盘2 的音效也开一个全局，验证"两套轮盘各自贡献"
cfg.switch_wheel("w2")
cfg.setting(other).hotkey = "f7"
cfg.setting(other).global_hotkey = True
cfg.switch_wheel("w2")        # 当前停在轮盘 2

bank = sr.SoundBank(20, cfg)
check(all_keys[4] in [bank.full_at(i) for i in range(len(bank))], "轮盘 2 的槽位里有 other")

audio = sr.AudioEngine(bank, dict(sr.DEFAULT_CONFIG))
check(a in audio._global_slots, "轮盘 1 的全局音效被额外装载", str(audio._global_slots))
check(other not in audio._global_slots, "当前轮盘上已有的不重复装载")
check(len(audio) == len(bank), "len(engine) 仍是槽位数（不含全局副本）", f"{len(audio)} vs {len(bank)}")
gi = audio._global_slots.get(a)
check(gi is not None and gi >= len(bank), "全局副本排在槽位之后", str(gi))
check(gi is not None and audio.clips[gi] is not None, "全局副本的波形真的解出来了")

# 参数没丢：按全局下标取 setting
st_g = audio._setting_of_slot(gi)
check(st_g is not None and abs(st_g.volume - 0.42) < 1e-6,
      "全局副本取到原始音量", str(getattr(st_g, "volume", None)))

# 真的能播（按名触发）
try:
    ok = audio.play_named(a)
    check(ok, "play_named 能触发不在当前轮盘上的全局音效")
    audio.stop_all()
except Exception as exc:
    check(False, "play_named 能触发不在当前轮盘上的全局音效", repr(exc))

# 没开全局、又不在当前轮盘的音效：按不出来
cfg.switch_wheel("w1")
cfg.setting(cfg.order[1]).hotkey = "f8"      # 只在轮盘 1，且没开全局
bank.reload()
audio.load()
check(cfg.order[1] in [bank.full_at(i) for i in range(len(bank))], "轮盘 1 的音效在槽位上")
cfg.switch_wheel("w2")
bank.reload()
audio.load()
try:
    ok2 = audio.play_named(cfg.wheels[0].order[1]) if cfg.wheels[0].order[1] else False
except Exception:
    ok2 = False
check(not ok2, "没开全局的音效，切走后按不出来（行为没变）")

print("\n=== D. 按键绑定 ===")
cfg = fresh_scfg()
a = cfg.order[0]
cfg.setting(a).hotkey = "f5"
cfg.setting(a).global_hotkey = True
cfg.switch_wheel("w2")

bank = sr.SoundBank(20, cfg)
played = []
audio2 = SimpleNamespace(
    bank=bank,
    play_named=lambda n, token=0: played.append(n) or True,
    play_next=lambda: None,
    play_repeat_last=lambda: None,
)
wheel = SimpleNamespace(active=False, show_wheel=lambda: None, hide_wheel=lambda: None)

cfg_main = dict(sr.DEFAULT_CONFIG)
cfg_main["hotkey"] = "y"
cfg_main["repeat_last_key"] = ""
cfg_main["cycle_key"] = ""
cfg_main["switch_key"] = ""
poller = sr.InputPoller(cfg_main, wheel, audio2)
check("f5" in poller._by_key, "全局键进了按键绑定表", str(list(poller._by_key)))
check(a in poller._by_key.get("f5", []), "绑的是那个音效", str(poller._by_key.get("f5")))

# 按下 f5：应该真的触发
poller._key_prev["f5"] = False
poller._run_bind(a, "f5", True, False, 1.0)
check(a in played, "模拟按下后音效被触发", str(played))

# 撞上呼出轮盘键：让路，不绑定
cfg_dup = dict(cfg_main)
cfg_dup["hotkey"] = "f5"
poller2 = sr.InputPoller(cfg_dup, wheel, audio2)
check("f5" not in poller2._by_key, "撞上呼出轮盘键时音效让路", str(list(poller2._by_key)))

# 解锁键也要跨轮盘
cfg = fresh_scfg()
a = cfg.order[0]
cfg.setting(a).hotkey = "f5"
cfg.setting(a).global_hotkey = True
cfg.setting(a).unlock_mode = sc.UNLOCK_KEY
cfg.setting(a).unlock_key = "g"
cfg.switch_wheel("w2")
bank2 = sr.SoundBank(20, cfg)
audio3 = SimpleNamespace(bank=bank2, play_named=lambda n, token=0: True,
                         play_next=lambda: None, play_repeat_last=lambda: None)
poller3 = sr.InputPoller(cfg_main, wheel, audio3)
check("g" in poller3._unlock_keys, "全局音效的解锁键也跨轮盘生效", str(list(poller3._unlock_keys)))
check(a in poller3._unlock_keys.get("g", []), "解锁键名下挂着这个音效")

# 真引擎 + 真 poller：从"按下键"一路走到"真的开始播"
cfg = fresh_scfg()
a = cfg.order[0]
cfg.setting(a).hotkey = "f9"
cfg.setting(a).global_hotkey = True
cfg.switch_wheel("w2")
bank3 = sr.SoundBank(20, cfg)
audio3 = sr.AudioEngine(bank3, dict(sr.DEFAULT_CONFIG))
poller4 = sr.InputPoller(cfg_main, wheel, audio3)
try:
    poller4._run_bind(a, "f9", True, False, 1.0)
    check(audio3.playing, "真引擎走完整链路会真的出声")
finally:
    audio3.stop_all()

print("\n=== E. 设置页 ===")
from settings_window import SettingsWindow  # noqa: E402

cfg_disk = sr.load_config()
scfg_ui = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
scfg_ui.load()
bank_ui = sr.SoundBank(int(cfg_disk["slots"]), scfg_ui)
win = SettingsWindow(cfg_disk, scfg_ui, bank_ui)
win.setAttribute(  # 不真的弹窗
    __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.WA_DontShowOnScreen, True
)
win.resize(1120, 800)
win.show()
app.processEvents()
win.tabs.setCurrentIndex(2)
app.processEvents()

detail = win.detail
target = bank_ui.full_at(0)
detail.set_sound(target)
app.processEvents()
check(detail.chk_global.isVisible() or detail.chk_global.isVisibleTo(detail),
      "普通音效显示「全局通用」")
check(not detail.chk_global.isChecked(), "默认不勾")

detail.chk_global.setChecked(True)
app.processEvents()
disk = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
disk.load()
check(disk.setting(target).global_hotkey is True, "勾选写入 sounds.json",
      str(disk.setting(target).global_hotkey))

detail.chk_global.setChecked(False)
app.processEvents()
disk = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
disk.load()
check(disk.setting(target).global_hotkey is False, "取消勾选也写盘")

# 组合音效：也要有这个开关（组合的定义全盘共用，但这个键在别的盘还算不算数，得单独决定）
cd = sc.ComboDef(cid="ctest", name="测试组合",
                 items=[sc.ComboItem(sound=all_keys[0])]).clamped()
scfg_ui.combos["ctest"] = cd
detail.set_sound(sr.combo_key("ctest") if hasattr(sr, "combo_key")
                 else "combo::ctest")
app.processEvents()
check(detail.chk_global.isVisible(), "组合音效也显示「全局通用」")

# 勾上要真的写进盘里，而不是只停在界面上
detail.hotkey.set_key("f8")
app.processEvents()
detail.chk_global.setChecked(True)
app.processEvents()
disk = sr.SoundsConfig(sr.SOUNDS_CONFIG_PATH)
disk.load()
ck = sr.combo_key("ctest") if hasattr(sr, "combo_key") else "combo::ctest"
check(disk.setting(ck).global_hotkey is True, "组合的勾选也写盘",
      str(disk.setting(ck).global_hotkey))
check(disk.global_hotkey_groups().get("f8") == [ck], "组合进了全局键表",
      str(disk.global_hotkey_groups()))

# 换回普通音效：开关要重新出现（隐藏是粘性的，容易忘记还原）
detail.set_sound(target)
app.processEvents()
check(detail.chk_global.isVisible(), "切回普通音效后开关重新出现")

# 勾了但没绑键：提示里要说清楚
detail.hotkey.set_key("")
app.processEvents()
detail.chk_global.setChecked(True)
app.processEvents()
tip = detail.chk_global.toolTip()
check("还没绑" in tip or "暂时不会生效" in tip, "空键时提示会说明不生效", tip[:40])

win.close()


print("\n=== F. 组合音效也能全局通用 ===")
# 组合的定义是全盘共用的，但"这个键在别的盘还算不算数"仍然记在各套轮盘的 items 里。
# 这里盯两件事：切盘后键还要在，以及参数不能被当前盘的空壳盖成默认值。
cfg3 = fresh_scfg()
ck = sr.combo_key("cx") if hasattr(sr, "combo_key") else "combo::cx"
w1 = cfg3.cur_wheel()
w1.items[ck] = sc.SoundSetting(
    hotkey="f8", global_hotkey=True,
    trigger_mode=sc.TRIGGER_HOLD, unlock_mode=sc.UNLOCK_KEY,
    unlock_key="g", unlock_ms=3000, unlock_count=2,
)
cfg3.combos["cx"] = sc.ComboDef(cid="cx", name="跨盘组合",
                                items=[sc.ComboItem(sound=all_keys[0])]).clamped()

check(cfg3.global_hotkey_groups().get("f8") == [ck], "组合进了全局键表",
      str(cfg3.global_hotkey_groups()))

cfg3.switch_wheel("w2")
# 模拟 hotkey_groups() 在别的盘顺手建出来的空壳记录
w2 = cfg3.cur_wheel()
w2.items[ck] = sc.SoundSetting()
check((cfg3.hotkey_groups().get("f8") or []) == [], "当前盘本来没有这个键",
      str(cfg3.hotkey_groups()))
check(cfg3.global_hotkey_groups().get("f8") == [ck], "换了一套轮盘，键还在",
      str(cfg3.global_hotkey_groups()))

got = cfg3.setting_any(ck)
check(got.trigger_mode == sc.TRIGGER_HOLD, "参数取的是勾全局那一套（触发方式）",
      got.trigger_mode)
check(got.unlock_mode == sc.UNLOCK_KEY and got.unlock_key == "g"
      and got.unlock_ms == 3000, "解锁条件也跟着过去了",
      f"{got.unlock_mode}/{got.unlock_key}/{got.unlock_ms}")
check(ck in cfg3.unlock_groups().get("g", []), "解锁键在别的盘也认这个组合",
      str(cfg3.unlock_groups()))

# 没勾全局的组合：换盘之后就该消失，别把"全盘共用"理解成"所有键都能跨盘"
cfg4 = fresh_scfg()
ck2 = sr.combo_key("cy") if hasattr(sr, "combo_key") else "combo::cy"
cfg4.cur_wheel().items[ck2] = sc.SoundSetting(hotkey="f9", global_hotkey=False)
cfg4.combos["cy"] = sc.ComboDef(cid="cy", name="只在当前盘",
                                items=[sc.ComboItem(sound=all_keys[1])]).clamped()
cfg4.switch_wheel("w2")
check("f9" not in cfg4.global_hotkey_groups(), "没勾全局的组合换盘后不生效",
      str(cfg4.global_hotkey_groups()))


# 按键绑定层：换盘之后这个键还得真的挂得上、按得响
class _FakeWheel:
    active = False
    raw = None

    def show_wheel(self):
        pass

    def hide_wheel(self):
        pass

    def commit(self):
        return None

    def poll_selection(self):
        pass

    def reload_entries(self):
        pass


class _FakeAudio:
    def __init__(self, cfgs):
        self.bank = SimpleNamespace(scfg=cfgs)
        self.played = []

    def play(self, i):
        pass

    def play_named(self, n, token=0):
        self.played.append(n)

    def play_repeat_last(self):
        return False

    def play_next(self):
        return False

    def stop_all(self):
        pass

    def reset_pitch(self):
        pass


pcfg = dict(sr.DEFAULT_CONFIG)
pcfg["hotkey"] = "y"
a_c = _FakeAudio(cfg3)
p_c = sr.InputPoller(pcfg, _FakeWheel(), a_c, None)
check(ck in (p_c._by_key.get("f8") or []), "组合的全局键进了绑定表",
      str(p_c._by_key.get("f8")))

kst = {"f8": False, "g": False}
p_c._down = lambda n: kst.get(n, False)
# 这条组合在别的盘上设了"条件解锁"（解锁键 g），先解锁才能响
kst["g"] = True
p_c.tick()
kst["g"] = False
p_c.tick()
kst["f8"] = True
p_c.tick()
check(ck in a_c.played, "在别的轮盘上按这个键，组合真的被放出来", str(a_c.played))

print("\n" + "=" * 60)
print(f"通过 {len(OK)} 项，失败 {len(BAD)} 项")
if BAD:
    for n in BAD:
        print("  失败:", n)
    sys.exit(1)
