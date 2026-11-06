"""音效配置：轮盘槽位顺序 + 每个音效的独立参数。

单独存成 sounds.json（和程序全局设置 config.json 分开），放在程序目录。
文件清单永远以磁盘为准，这里只记三件事：
  1. order —— 哪些音效在轮盘上、内圈的先后顺序（前 8 个是内圈，之后是外圈成员）
  2. outer_slots —— 外圈 12 个固定位置各摆着谁，可以留空（空格子不画）
  3. items —— 每个音效自己的参数

这样用户在文件夹里直接删文件、加文件，程序都能自动同步，
不会因为配置和磁盘对不上而出现空槽位或者幽灵音效。
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

CONFIG_VERSION = 4

# 最多能存几套轮盘（含当前正在用的那套）
MAX_WHEELS = 8

# 轮盘分两层：内圈最多 8 个，装满后第 9 个开始进外圈，外圈最多 12 个。
# 这两个数字同时约束 order 的长度上限，改的时候两边都要一致。
INNER_MAX = 8
OUTER_MAX = 12
MAX_SLOTS = INNER_MAX + OUTER_MAX

# 文件名开头的序号前缀（"01 "、"01_"、"01-"），改名配对时忽略它
_LEADING_NUM = re.compile(r"^\s*\d+\s*[_\-.]?\s*")


def _norm_name(name: str) -> str:
    """去掉扩展名、开头的序号，转小写，用于"是不是同一个音效"的模糊比较。"""
    stem = Path(name).stem.lower()
    return _LEADING_NUM.sub("", stem).strip()

# 变调模式
PITCH_NONE = "none"
PITCH_UP = "up"
PITCH_DOWN = "down"
PITCH_RANDOM = "random"
PITCH_FIXED = "fixed"   # 固定变调：每次播放都直接变固定半音，不看连击窗口
PITCH_MODES = (PITCH_NONE, PITCH_UP, PITCH_DOWN, PITCH_RANDOM, PITCH_FIXED)

PITCH_MODE_LABEL = {
    PITCH_NONE: "不改变音调",
    PITCH_UP: "连续播放时升调",
    PITCH_DOWN: "连续播放时降调",
    PITCH_RANDOM: "每次随机变调",
    PITCH_FIXED: "固定变调",
}

# 速度模式（时间拉伸：只改快慢，音调不变，和上面的变调互不干扰）
SPEED_NONE = "none"
SPEED_UP = "up"
SPEED_DOWN = "down"
SPEED_MODES = (SPEED_NONE, SPEED_UP, SPEED_DOWN)

SPEED_MODE_LABEL = {
    SPEED_NONE: "不改变速度",
    SPEED_UP: "连续播放时加快",
    SPEED_DOWN: "连续播放时变慢",
}


# ---------------------------------------------------------------- 触发方式
#
# v0.9 新增：快捷键按下去之后，到底"什么时候响、什么时候停"。
# 以前只有一种行为（按下响一次），现在由每个音效自己挑：
#
#   tap     点击触发（默认，和以前完全一致）：按下响一次，松手不管
#   hold    长按触发：按下开始响，松手立刻停（下次按从头开始）
#   release 松手触发：按下什么都不做，松手的那一下才响
#   repeat  长按连续触发：按下响一次，之后每 N 毫秒再"虚拟点一次"，
#           用来驱动连击变调/变速（按得越久，音越连）

TRIGGER_TAP = "tap"
TRIGGER_HOLD = "hold"
TRIGGER_RELEASE = "release"
TRIGGER_REPEAT = "repeat"
TRIGGER_MODES = (TRIGGER_TAP, TRIGGER_HOLD, TRIGGER_RELEASE, TRIGGER_REPEAT)

TRIGGER_MODE_LABEL = {
    TRIGGER_TAP: "点击触发",
    TRIGGER_HOLD: "长按触发",
    TRIGGER_RELEASE: "松手触发",
    TRIGGER_REPEAT: "长按连续触发",
}

TRIGGER_MODE_TIP = {
    TRIGGER_TAP: "按下快捷键立刻响一次，松手不停。",
    TRIGGER_HOLD: "按住时一直响，松手立刻停；下次再按会从头开始。",
    TRIGGER_RELEASE: "按下时不出声，松手的那一刻才响。",
    TRIGGER_REPEAT: "按下响一次，按住不放则每隔一段时间再响一次，\n"
                    "相当于用手连续点这个键（连击变调/变速会跟着累加）。",
}

# 长按连续触发的间隔：50ms（每秒 20 次，已经很糊）~ 2000ms（每 2 秒一次）
REPEAT_MS_MIN = 50
REPEAT_MS_MAX = 2000

# ---------------------------------------------------------------- 触发条件
#
# 音效默认"无条件"，按了就能响。设成"条件解锁"之后，必须先按一下解锁键，
# 这个音效才在"解锁时间"内、"解锁次数"内可以被触发。
#
# 注意两件事：
#   1. 解锁时间只管"能不能再触发新的"，时间到了**不会**掐断正在响的声音
#   2. 解锁次数 0 = 不限；长按连续触发整段按住只算 1 次

UNLOCK_NONE = "none"
UNLOCK_KEY = "key"
UNLOCK_MODES = (UNLOCK_NONE, UNLOCK_KEY)

UNLOCK_MODE_LABEL = {
    UNLOCK_NONE: "无条件",
    UNLOCK_KEY: "条件解锁",
}

UNLOCK_MS_MAX = 600000      # 解锁时间上限 10 分钟
UNLOCK_COUNT_MAX = 999      # 解锁次数上限


@dataclass
class SoundSetting:
    """单个音效的独立参数。默认值 = 和以前完全一样的行为。"""

    volume: float = 1.0            # 相对音量倍数，0.0 ~ 2.0
    pitch_mode: str = PITCH_NONE   # none / up / down / random / fixed
    # 升/降调模式：多少毫秒内再次播放算"连击"（随机/固定模式不看这个）
    pitch_window_ms: int = 2500
    # 升/降调模式：每次连击升/降多少半音；随机模式：随机范围 ±N 半音
    pitch_step: float = 1.0
    pitch_limit: float = 12.0      # 最多累计到多少半音（正负都算）
    # 固定变调模式：每次播放直接变这么多半音，-24 ~ +24（正升负降）
    pitch_fixed: float = 0.0
    # 速度模式：连续播放时越按越快 / 越慢（只改快慢，音调不动）
    speed_mode: str = SPEED_NONE
    speed_step: float = 0.10       # 每次连击快/慢多少，0.10 = 10%
    speed_limit: float = 0.60      # 最多累计到多少，0.6 = 快 60% 或慢 60%
    hotkey: str = ""               # 直接触发键，空表示不绑定
    # 全局通用：这个快捷键不再跟着轮盘走，切到任何一套轮盘都能按响。
    # 关着的时候（默认）快捷键只在这一套轮盘上生效，和以前完全一样。
    global_hotkey: bool = False

    # ---- v0.9 新增 ----
    trigger_mode: str = TRIGGER_TAP   # 按下/长按/松手/长按连发
    repeat_ms: int = 200              # 长按连续触发的间隔（毫秒）
    unlock_mode: str = UNLOCK_NONE    # 无条件 / 条件解锁
    unlock_key: str = ""              # 解锁键，空 = 没设（等同于无条件）
    unlock_ms: int = 0                # 解锁有效期，0 = 不限时（直到把次数用完）
    unlock_count: int = 0             # 可用次数，0 = 不限次

    def clamped(self) -> "SoundSetting":
        """把越界的值收回来。手改 json 写错了也不至于出怪声。"""
        s = SoundSetting(**asdict(self))
        s.volume = max(0.0, min(2.0, float(s.volume)))
        if s.pitch_mode not in PITCH_MODES:
            s.pitch_mode = PITCH_NONE
        s.pitch_window_ms = max(0, min(30000, int(s.pitch_window_ms)))
        s.pitch_step = max(0.0, min(12.0, float(s.pitch_step)))
        s.pitch_limit = max(0.0, min(24.0, float(s.pitch_limit)))
        s.pitch_fixed = max(-24.0, min(24.0, round(float(s.pitch_fixed), 1)))
        if s.speed_mode not in SPEED_MODES:
            s.speed_mode = SPEED_NONE
        # 单次最大 40%、累计最大 80%：再快就只剩一声"啪"，再慢就拖成糊音
        s.speed_step = max(0.0, min(0.40, float(s.speed_step)))
        s.speed_limit = max(0.0, min(0.80, float(s.speed_limit)))
        s.hotkey = (s.hotkey or "").strip().lower()
        s.global_hotkey = bool(s.global_hotkey)
        if s.trigger_mode not in TRIGGER_MODES:
            s.trigger_mode = TRIGGER_TAP
        s.repeat_ms = max(REPEAT_MS_MIN, min(REPEAT_MS_MAX, int(s.repeat_ms)))
        if s.unlock_mode not in UNLOCK_MODES:
            s.unlock_mode = UNLOCK_NONE
        s.unlock_key = (s.unlock_key or "").strip().lower()
        s.unlock_ms = max(0, min(UNLOCK_MS_MAX, int(s.unlock_ms)))
        s.unlock_count = max(0, min(UNLOCK_COUNT_MAX, int(s.unlock_count)))
        return s


_DEFAULT_KEYS = {f.name for f in fields(SoundSetting)}


# ---------------------------------------------------------------- 轮盘
#
# 一份 sounds.json 里可以存最多 MAX_WHEELS 套轮盘。每套各记自己的：
#   order / outer_slots —— 哪些音效摆在哪些格子
#   items               —— 这套轮盘里每个音效的参数（音量、变调、速度…）
#   color               —— 这套轮盘的颜色（空 = 跟随应用主题色）
# 音效库本身（sounds 目录里的文件）和组合音效是全套共用的。


def _blank_slots() -> list[str | None]:
    return [None] * OUTER_MAX


@dataclass
class WheelDef:
    """一套轮盘的完整配置。"""

    wid: str
    name: str = ""
    color: str = ""                       # "#rrggbb"；空字符串 = 跟随主题色
    order: list[str] = field(default_factory=list)
    outer_slots: list[str | None] = field(default_factory=_blank_slots)
    items: dict[str, SoundSetting] = field(default_factory=dict)

    def trimmed(self) -> "WheelDef":
        """把越界的数据收回来（手改 json 写错了也不至于出怪东西）。"""
        self.order = [str(x) for x in (self.order or []) if isinstance(x, str)]
        slots = list(self.outer_slots or [])[:OUTER_MAX]
        slots += [None] * (OUTER_MAX - len(slots))
        self.outer_slots = [str(v) if isinstance(v, str) and v else None for v in slots]
        if not isinstance(self.items, dict):
            self.items = {}
        return self

    def to_dict(self) -> dict:
        return {
            "wid": self.wid,
            "name": self.name,
            "color": self.color,
            "order": self.order,
            "outer_slots": self.outer_slots,
            "items": {k: asdict(v) for k, v in self.items.items()},
        }

    def clone(self, wid: str, name: str) -> "WheelDef":
        """复制一份（深拷贝参数，两套轮盘以后改参数互不影响）。"""
        return WheelDef(
            wid=wid,
            name=name,
            color=self.color,
            order=list(self.order),
            outer_slots=list(self.outer_slots),
            items={k: SoundSetting(**asdict(v)) for k, v in self.items.items()},
        )



# ---------------------------------------------------------------- 组合音效
#
# 设计原则（v0.7.1 重做，v0.7 那套时间轴/音轨已废弃）：
#   1. 每一项只描述"什么时候响"，不用拖时间轴，参数全是离散数字 → 可复制、可校验
#   2. 触发条件只有三种，语义和用户嘴里的说法一一对应：
#        combo      —— 组合开始后（第一项用）
#        prev_start —— 上一项"开始响"之后 X 毫秒
#        prev_end   —— 上一项"播完"之后 X 毫秒
#   3. 排程在播放瞬间一次算完（纯函数 combo_plan），不依赖定时器回调，
#      所以不会出现"点了没反应/越按越乱/卡住"这类问题

# 组合在轮盘/配置里的键形如 "combo::c1"。冒号在 Windows 文件名里非法，
# 所以绝不可能和磁盘上的音效撞名。
COMBO_PREFIX = "combo::"

# 触发条件
TRIG_COMBO = "combo"
TRIG_PREV_START = "prev_start"
TRIG_PREV_END = "prev_end"
TRIGS = (TRIG_COMBO, TRIG_PREV_START, TRIG_PREV_END)

TRIG_LABEL = {
    TRIG_COMBO: "组合开始时",
    TRIG_PREV_START: "上一项开始后",
    TRIG_PREV_END: "上一项结束后",
}

# 播放模式：随机抽取只是"选哪几项"，接龙规则和顺序模式完全一致
CM_SEQ = "seq"
CM_RAND = "rand"
# v0.7.6 新增：两种"按次数推进"的模式，内部维护一个游标，
# 每触发一次往前走一格，播满一圈回到第一项（ABCD→ABCD 不断循环）
CM_STEP = "step"        # 按顺序点击播放：一次只响 1 项
CM_ACC = "acc"          # 累加播放：第 N 次同时响前 N 项
COMBO_MODES = (CM_SEQ, CM_RAND, CM_STEP, CM_ACC)

COMBO_MODE_LABEL = {
    CM_SEQ: "按顺序全部播放",
    CM_RAND: "随机抽取 N 个播放",
    CM_STEP: "按顺序点击播放（一次 1 个）",
    CM_ACC: "累加播放（越点越多）",
}

COMBO_MODE_TIP = {
    CM_SEQ: "从第一项到最后一项，每项按自己的触发条件决定什么时候响。",
    CM_RAND: "每次从成员里随机抽 N 个（不重复），抽中的项按原顺序接龙，\n"
             "每项的触发条件和延迟照常生效。",
    CM_STEP: "每按一次只响 1 项，按顺序往下走，播完最后一项回到第一项，\n"
             "一直循环。\n"
             "注意：一次只有一项在响，它就是起点，所以只有触发条件设成\n"
             "「组合开始时」的那一项，它的延迟才会生效。",
    CM_ACC: "第 1 次响第 1 项，第 2 次响前 2 项，第 3 次响前 3 项……\n"
            "叠满全部之后回到第 1 项重新累加，一直循环。\n"
            "越点越乱，建议配合冷却使用。",
}

MAX_COMBO_ITEMS = 24


# 延迟可以为负：负数 = 比参照点更早开始，用来做"尾巴叠上一项"的交叠衔接。
# 下限 -5000 是够用又不至于把自己绕晕的量级。
DELAY_MIN_MS = -5000
DELAY_MAX_MS = 10000


@dataclass
class ComboItem:
    """组合里的一项：放哪个音效、什么时候响、以什么姿态响。"""

    sound: str = ""          # 成员音效（sounds 目录里的文件名）
    trig: str = TRIG_PREV_END  # 触发条件
    delay_ms: int = 0        # 相对触发点的延迟，DELAY_MIN_MS ~ DELAY_MAX_MS（负数=提前）
    gain: float = 1.0        # 这一项的音量倍率 0.0 ~ 2.0
    semitones: float = 0.0   # 这一项的变调（半音，-24 ~ +24，0 = 不变）
    rate: float = 1.0        # 这一项的速度（0.5 ~ 2.0，不变调）

    # ---- v0.7.2 新增 ----
    # 片段裁剪：只取原音效中间的一段。起点单位毫秒（按原速算），
    # 长度 0 = 一直取到结尾。做"只要起手那一下""只要尾音"就靠这两个数。
    clip_start_ms: int = 0
    clip_len_ms: int = 0
    # 每次触发时在这一项上再抖一下：±rand_semi 半音、±rand_rate 速度
    rand_semi: float = 0.0
    rand_rate: float = 0.0

    def clamped(self) -> "ComboItem":
        trig = self.trig if self.trig in TRIGS else TRIG_PREV_END
        return ComboItem(
            sound=str(self.sound or ""),
            trig=trig,
            delay_ms=max(DELAY_MIN_MS, min(DELAY_MAX_MS, int(self.delay_ms))),
            gain=max(0.0, min(2.0, float(self.gain))),
            semitones=round(max(-24.0, min(24.0, float(self.semitones))), 1),
            rate=round(max(0.5, min(2.0, float(self.rate))), 2),
            clip_start_ms=max(0, min(600000, int(self.clip_start_ms))),
            clip_len_ms=max(0, min(600000, int(self.clip_len_ms))),
            rand_semi=round(max(0.0, min(12.0, float(self.rand_semi))), 1),
            rand_rate=round(max(0.0, min(0.50, float(self.rand_rate))), 2),
        )

    def describe(self) -> str:
        trig = TRIG_LABEL.get(self.trig, TRIG_LABEL[TRIG_PREV_END])
        return f"{trig} {int(self.delay_ms)} ms"


@dataclass
class ComboDef:
    """一个组合音效。cid 是稳定 id，改名不影响轮盘上的引用。"""

    cid: str = ""
    name: str = ""
    mode: str = CM_SEQ
    count: int = 3           # 随机模式抽几项（1 = 随机播一个）
    shuffle: bool = False    # 抽中后是否打乱播放顺序
    items: list = None       # type: ignore[assignment]  # list[ComboItem]

    # ---- v0.7.2 新增：整体参数 ----
    # 整体参数乘/加在每一项自己的参数之上，改一处等于全组合一起改
    rate: float = 1.0        # 整体速度 0.5 ~ 2.0
    semitones: float = 0.0   # 整体变调 ±24 半音
    rand_rate: float = 0.0   # 每次触发整体随机变速 ±N（0.1 = ±10%，全组合共用同一个值）
    rand_semi: float = 0.0   # 每次触发整体随机变调 ±N 半音（全组合共用同一个值）
    cooldown_ms: int = 0     # 冷却：触发后多少毫秒内再按无效，防连按叠音
    max_voices: int = 0      # 最多允许几条这条组合的声音同时响，0 = 不限

    def __post_init__(self) -> None:
        if self.items is None:
            self.items = []

    def clamped(self) -> "ComboDef":
        items = [it.clamped() for it in (self.items or [])
                 if isinstance(it, ComboItem)]
        c = ComboDef(
            cid=str(self.cid or ""),
            name=str(self.name or "").strip() or "未命名组合",
            mode=self.mode if self.mode in COMBO_MODES else CM_SEQ,
            count=max(1, min(MAX_COMBO_ITEMS, int(self.count))),
            shuffle=bool(self.shuffle),
            items=items[:MAX_COMBO_ITEMS],
            rate=round(max(0.5, min(2.0, float(self.rate))), 2),
            semitones=round(max(-24.0, min(24.0, float(self.semitones))), 1),
            rand_rate=round(max(0.0, min(0.80, float(self.rand_rate))), 2),
            rand_semi=round(max(0.0, min(12.0, float(self.rand_semi))), 1),
            cooldown_ms=max(0, min(60000, int(self.cooldown_ms))),
            max_voices=max(0, min(16, int(self.max_voices))),
        )
        # 第一项的触发点必须是"组合开始"：否则它没有"上一项"可参照，
        # 留着 prev_* 语义会变成悬空值，排程算不出来
        if c.items:
            c.items[0].trig = TRIG_COMBO
        return c

    def play_order(self, step: int = 0) -> list[int]:
        """这一次要播的成员下标。

        顺序模式 = 全部，随机模式 = 抽中的；
        step = 当前游标，只有"按顺序点击 / 累加"两种模式会用到它
        （游标由播放器按 cid 维护，这里保持纯函数，不算状态）。
        """
        n = len(self.items)
        if n == 0:
            return []
        if self.mode == CM_STEP:
            return [(int(step) % n)]
        if self.mode == CM_ACC:
            return list(range(int(step) % n + 1))
        if self.mode != CM_RAND:
            return list(range(n))
        k = max(1, min(int(self.count), n))
        idx = _rng.sample(range(n), k)
        if not self.shuffle:
            idx.sort()          # 默认保持组合里的原顺序，结果可预期
        return idx

    def steps_per_trigger(self) -> int:
        """每触发一次，游标往前走几格（不用游标的模式返回 0）。"""
        return 1 if self.mode in (CM_STEP, CM_ACC) else 0


def is_combo_key(name: str) -> bool:
    return isinstance(name, str) and name.startswith(COMBO_PREFIX)


_rng = random.Random()


class SoundsConfig:
    """sounds.json 的读写与同步。

    对外仍然暴露 order / outer_slots / items 三个属性，但它们指向的是
    **当前那套轮盘**——上层所有代码（拖放、同步、绘制）都不用关心
    "现在有几套轮盘"，该读 order 就读到当前这套的 order。
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.wheels: list[WheelDef] = [WheelDef(wid="w1", name="轮盘 1")]
        self._cur = "w1"
        # 组合音效：cid -> ComboDef。全套轮盘共用（它们是"音效"，不是"摆位"）。
        # 轮盘上以 "combo::cid" 的形式占一个槽位
        self.combos: dict[str, ComboDef] = {}
        # 是否已经有配置文件：决定 sync 时要不要把磁盘上的文件全数上盘。
        # 只在"第一次运行"这么做，之后轮盘只放用户自己挑的。
        self._initialized = path.exists()

    # ---- 当前轮盘 ----
    def cur_wheel(self) -> WheelDef:
        for w in self.wheels:
            if w.wid == self._cur:
                return w
        if not self.wheels:
            self.wheels = [WheelDef(wid="w1", name="轮盘 1")]
        self._cur = self.wheels[0].wid
        return self.wheels[0]

    @property
    def current(self) -> str:
        """当前生效的轮盘 id。"""
        return self.cur_wheel().wid

    @property
    def order(self) -> list[str]:
        return self.cur_wheel().order

    @order.setter
    def order(self, value) -> None:
        self.cur_wheel().order = [str(x) for x in (value or [])]

    @property
    def outer_slots(self) -> list[str | None]:
        return self.cur_wheel().outer_slots

    @outer_slots.setter
    def outer_slots(self, value) -> None:
        slots = list(value or [])[:OUTER_MAX]
        slots += [None] * (OUTER_MAX - len(slots))
        self.cur_wheel().outer_slots = slots

    @property
    def items(self) -> dict[str, SoundSetting]:
        return self.cur_wheel().items

    @items.setter
    def items(self, value) -> None:
        self.cur_wheel().items = value if isinstance(value, dict) else {}


    # ---- 读写 ----
    def load(self) -> None:
        self.wheels = [WheelDef(wid="w1", name="轮盘 1")]
        self._cur = "w1"
        self.order = []
        self.outer_slots = [None] * OUTER_MAX
        self.items = {}
        self.combos = {}
        if not self.path.exists():
            self._initialized = False
            return
        self._initialized = True
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            # 文件坏了就当没有：sync 会把磁盘上的音效全数上盘，
            # 总比轮盘空空如也、用户以为程序坏了要好
            self._initialized = False
            return
        if not isinstance(data, dict):
            self._initialized = False
            return

        def read_items(raw) -> dict[str, SoundSetting]:
            out: dict[str, SoundSetting] = {}
            if not isinstance(raw, dict):
                return out
            for name, body in raw.items():
                if not isinstance(body, dict):
                    continue
                kwargs = {k: v for k, v in body.items() if k in _DEFAULT_KEYS}
                try:
                    out[str(name)] = SoundSetting(**kwargs).clamped()
                except Exception:
                    out[str(name)] = SoundSetting()
            return out

        # 轮盘列表（v0.8）。老版本的 sounds.json 没有这一段，
        # 会把顶层那套 order/items 迁移成"轮盘 1"，一个音效都不丢。
        raw_wheels = data.get("wheels")
        wheels: list[WheelDef] = []
        if isinstance(raw_wheels, list):
            for raw in raw_wheels[:MAX_WHEELS]:
                if not isinstance(raw, dict) or not raw.get("wid"):
                    continue
                w = WheelDef(
                    wid=str(raw.get("wid")),
                    name=str(raw.get("name") or ""),
                    color=str(raw.get("color") or ""),
                    order=list(raw.get("order") or []),
                    outer_slots=list(raw.get("outer_slots") or []),
                    items=read_items(raw.get("items")),
                ).trimmed()
                if all(x.wid != w.wid for x in wheels):
                    wheels.append(w)
        if not wheels:
            wheels = [WheelDef(
                wid="w1",
                name="轮盘 1",
                order=list(data.get("order") or []),
                outer_slots=list(data.get("outer_slots") or []),
                items=read_items(data.get("items")),
            ).trimmed()]
        self.wheels = wheels
        cur = str(data.get("current") or "")
        self._cur = cur if any(w.wid == cur for w in wheels) else wheels[0].wid

        # 组合音效（v0.7.1 结构）。老 v0.7 的 combos 是另一套字段，读不出来的
        # 那份会被 clamped 兜住（缺字段用默认值），不影响普通音效
        raw_combos = data.get("combos")
        if isinstance(raw_combos, list):
            item_keys = {f.name for f in fields(ComboItem)}
            for raw in raw_combos:
                if not isinstance(raw, dict) or not raw.get("cid"):
                    continue
                try:
                    c = ComboDef(
                        cid=str(raw.get("cid")),
                        name=str(raw.get("name") or ""),
                        mode=str(raw.get("mode") or CM_SEQ),
                        count=int(raw.get("count", 3)),
                        shuffle=bool(raw.get("shuffle", False)),
                        items=[
                            ComboItem(**{k: v for k, v in it.items() if k in item_keys})
                            for it in (raw.get("items") or [])
                            if isinstance(it, dict)
                        ],
                        rate=float(raw.get("rate", 1.0)),
                        semitones=float(raw.get("semitones", 0.0)),
                        rand_rate=float(raw.get("rand_rate", 0.0)),
                        rand_semi=float(raw.get("rand_semi", 0.0)),
                        cooldown_ms=int(raw.get("cooldown_ms", 0)),
                        max_voices=int(raw.get("max_voices", 0)),
                    ).clamped()
                except Exception:
                    continue
                if c.cid and c.cid not in self.combos:
                    self.combos[c.cid] = c
        self.normalize_outer()

    def save(self) -> None:
        for w in self.wheels:
            self.normalize_outer(w)
        cur = self.cur_wheel()
        payload = {
            "version": CONFIG_VERSION,
            "current": cur.wid,
            "wheels": [w.to_dict() for w in self.wheels],
            # 下面三个是"当前轮盘"的镜像，写给旧版程序看：
            # 万一用户换回老版本，轮盘不会突然空掉（读不到 wheels 就退到这三个键）
            "order": cur.order,
            "outer_slots": cur.outer_slots,
            "items": {k: asdict(v) for k, v in cur.items.items()},
            "combos": [
                {
                    "cid": c.cid, "name": c.name, "mode": c.mode,
                    "count": c.count, "shuffle": c.shuffle,
                    "rate": c.rate, "semitones": c.semitones,
                    "rand_rate": c.rand_rate, "rand_semi": c.rand_semi,
                    "cooldown_ms": c.cooldown_ms, "max_voices": c.max_voices,
                    "items": [asdict(it) for it in c.items],
                }
                for c in self.combos.values()
            ],
        }
        try:
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    # ---- 轮盘管理 ----
    def wheel_by_id(self, wid: str) -> WheelDef | None:
        for w in self.wheels:
            if w.wid == wid:
                return w
        return None

    def _new_wid(self) -> str:
        used = {w.wid for w in self.wheels}
        n = 1
        while f"w{n}" in used:
            n += 1
        return f"w{n}"

    def switch_wheel(self, wid: str) -> bool:
        """换到另一套轮盘。返回是否真的换了。"""
        if wid == self._cur or self.wheel_by_id(wid) is None:
            return False
        self.normalize_outer()      # 走之前把当前这套对齐一下，免得留下半截状态
        self._cur = wid
        self.normalize_outer()
        return True

    def new_wheel(self, name: str = "", copy_current: bool = True) -> WheelDef | None:
        """另存为一套新轮盘。装满 MAX_WHEELS 套时返回 None。"""
        if len(self.wheels) >= MAX_WHEELS:
            return None
        wid = self._new_wid()
        base = self.cur_wheel()
        if copy_current:
            w = base.clone(wid, name.strip() or f"轮盘 {len(self.wheels) + 1}")
        else:
            w = WheelDef(wid=wid, name=name.strip() or f"轮盘 {len(self.wheels) + 1}")
        self.wheels.append(w)
        return w

    def delete_wheel(self, wid: str) -> bool:
        """删掉一套轮盘。最后一套不能删（否则没有轮盘可用了）。"""
        if len(self.wheels) <= 1:
            return False
        w = self.wheel_by_id(wid)
        if w is None:
            return False
        self.wheels.remove(w)
        if self._cur == wid:
            self._cur = self.wheels[0].wid
        return True

    def rename_wheel(self, wid: str, name: str) -> bool:
        w = self.wheel_by_id(wid)
        clean = str(name or "").strip()
        if w is None or not clean or clean == w.name:
            return False
        w.name = clean
        return True

    def clear_wheel(self, wid: str) -> bool:
        """清空一套轮盘的格子（音效文件、参数、组合都不动）。"""
        w = self.wheel_by_id(wid)
        if w is None:
            return False
        w.order = []
        w.outer_slots = [None] * OUTER_MAX
        return True

    def wheel_color(self, wid: str = "") -> str:
        """某套轮盘的颜色；空字符串表示跟随应用主题色。"""
        w = self.wheel_by_id(wid) if wid else self.cur_wheel()
        return (w.color if w is not None else "") or ""

    def set_wheel_color(self, color: str, wid: str = "") -> None:
        w = self.wheel_by_id(wid) if wid else self.cur_wheel()
        if w is not None:
            w.color = str(color or "").strip()

    # ---- 同步 ----
    def sync(self, names: list[str]) -> list[str]:
        """按磁盘实际文件校正 order，返回校正后的顺序。

        轮盘是"sounds 目录里挑出来的一部分"，不是全部：
        - **首次运行**（还没有 sounds.json）：把磁盘上的文件全数放上去，
          免得升级之后轮盘突然空了
        - 之后：只保留 order 里仍然存在的文件，**新文件不会自动上盘**，
          要用户在配置窗口里自己拖上去
        - order 里已消失的丢掉，items 里对应的也一起清

        额外兜一层：用户直接在资源管理器里给文件改名（比如把 `冰冰冰.wav`
        改成 `01 冰冰冰.wav`）时，order 会全部对不上。这时按"去掉序号的
        名字"重新配对，尽量把原来的位置和参数认回去，别让轮盘莫名其妙变空。
        """
        alive = set(names)
        prev_order = list(self.order)

        def _live_combo(key: str) -> bool:
            """组合键是否还指向一个存在的组合（组合删了就该从轮盘上消失）。"""
            return is_combo_key(key) and key[len(COMBO_PREFIX):] in self.combos

        renamed: dict[str, str] = {}

        if not self._initialized:
            final = list(names)
            self._initialized = True
        else:
            exact = [n for n in self.order if n in alive or _live_combo(n)]
            olds = [n for n in self.order if n not in alive and not _live_combo(n)]
            news = [n for n in names if n not in exact]
            renamed = self._match_renamed(olds, news)

            final = []
            for n in self.order:
                if n in alive or _live_combo(n):
                    final.append(n)
                elif n in renamed:
                    final.append(renamed[n])

            # 大面积改名把 order 清空了：按磁盘重建，不然轮盘会整个空掉。
            # （用户手动清空轮盘时会立刻把空 order 存盘，所以这里不会误触发）
            if prev_order and not final and names:
                final = list(names)

        # 去重（手改 json 时可能出现重复项）
        dedup: list[str] = []
        for n in final:
            if n not in dedup:
                dedup.append(n)
        final = dedup

        # 参数字典的键要跟着改名一起迁移，否则"改完名字参数全丢"
        for old, new in renamed.items():
            if old in self.items and new not in self.items:
                self.items[new] = self.items.pop(old)
            # 组合成员引用的文件名也要跟着改，否则组合里那一项会"失踪"
            for c in self.combos.values():
                for it in c.items:
                    if it.sound == old:
                        it.sound = new

        # 老版本可能把参数存在"去扩展名"的键下，同样迁移到全名，
        # 否则这些参数会跟着下面的清理一起被删掉（表现为"调了不生效"）
        by_stem = {Path(n).stem: n for n in names}
        by_norm: dict[str, str] = {}
        for n in names:
            by_norm.setdefault(_norm_name(n), n)
        for k in [k for k in self.items if k not in alive and not is_combo_key(k)]:
            full = by_stem.get(Path(k).stem) or by_norm.get(_norm_name(k))
            if full and full not in self.items:
                self.items[full] = self.items.pop(k)

        # 清理已消失文件的参数。组合键（combo::xxx）单独留着：
        # 它们的参数（音量/快捷键）跟着组合定义一起由 delete_combo 收拾
        for dead in [k for k in self.items if k not in alive and not is_combo_key(k)]:
            self.items.pop(dead, None)

        self.order = final
        self.normalize_outer()

        # 其他几套轮盘也要跟着收拾：文件被删/改名后，切过去不该出现空槽位。
        # 只做"减"，不自动补新文件（那是首次运行才有的待遇）。
        cur = self.cur_wheel()
        for w in self.wheels:
            if w is cur:
                continue
            w.order = [n for n in w.order if n in alive or _live_combo(n)]
            for dead in [k for k in w.items if k not in alive and not is_combo_key(k)]:
                w.items.pop(dead, None)
            self.normalize_outer(w)
        return list(final)

    @staticmethod
    def _match_renamed(olds: list[str], news: list[str]) -> dict[str, str]:
        """猜"老名字 -> 新名字"的对应关系。

        典型场景：用户在文件夹里给音效加了序号前缀。判定规则：
        去掉扩展名、去掉开头的序号、转小写之后，两个名字相同或互为前缀，
        并且候选唯一，才认。
        """
        left = list(news)
        out: dict[str, str] = {}
        for old in olds:
            o = _norm_name(old)
            if not o:
                continue
            cand = [n for n in left if _norm_name(n) == o]
            if not cand:
                cand = [
                    n for n in left
                    if _norm_name(n).startswith(o) or o.startswith(_norm_name(n))
                ]
            if len(cand) == 1:
                out[old] = cand[0]
                left.remove(cand[0])
        return out

    # ---- 外圈摆位 ----
    def normalize_outer(self, wheel: WheelDef | None = None) -> None:
        """把外圈位置表对齐到 order（默认只处理当前那套轮盘）。

        order 决定"谁在盘上"，outer_slots 只决定"外圈那 12 个位置各摆谁"。
        两边一旦不同步（手改 json、删文件、改名），以 order 为准：
        多余/重复的位置清掉，还没位置的按顺序补进第一个空位。
        """
        w = wheel if wheel is not None else self.cur_wheel()
        slots: list[str | None] = [None] * OUTER_MAX
        outer_names = w.order[INNER_MAX:]
        alive = set(outer_names)
        seen: set[str] = set()
        for k, name in enumerate(list(w.outer_slots)[:OUTER_MAX]):
            if name in alive and name not in seen:
                slots[k] = name
                seen.add(name)
        for name in outer_names:
            if name in seen:
                continue
            for k in range(OUTER_MAX):
                if slots[k] is None:
                    slots[k] = name
                    seen.add(name)
                    break
        w.outer_slots = slots

    def outer_index_map(self) -> list[int | None]:
        """外圈 12 个位置 -> 该位置上的音效在 order 里的下标；空位是 None。"""
        out: list[int | None] = [None] * OUTER_MAX
        for k, name in enumerate(self.outer_slots):
            if name is None:
                continue
            try:
                out[k] = self.order.index(name)
            except ValueError:
                pass
        return out

    def slot_of(self, name: str) -> int | None:
        """音效在轮盘上的槽位号：0~7 内圈，8~19 外圈位置；不在盘上返回 None。"""
        name = self.canon(name)
        if name in self.order:
            idx = self.order.index(name)
            if idx < INNER_MAX:
                return idx
            if name in self.outer_slots:
                return INNER_MAX + self.outer_slots.index(name)
        return None

    def swap_slots(self, a: int, b: int) -> bool:
        """轮盘内部拖动：两个槽位互换（外圈可以换成空格子，原位就空出来）。

        内圈和外圈之间也能换，前提是外圈那一格**有**音效：两边都是实格，
        换完内圈还是满的，不会有洞。内圈拖到外圈的空位仍然拒绝 ——
        内圈 8 格必须满，空一个出来整个轮盘就不好判定了。
        """
        if a == b or a < 0 or b < 0:
            return False
        a_in, b_in = a < INNER_MAX, b < INNER_MAX
        if a_in and b_in:
            if a >= len(self.order) or b >= len(self.order):
                return False
            self.order[a], self.order[b] = self.order[b], self.order[a]
            return True

        if a_in or b_in:
            # 跨圈互换：内圈的 order[inner] 和外圈的 outer_slots[p] 对调。
            # 关键是 order 的排布：内圈永远是 order[:8]，外圈是 order[8:]，
            # 所以两个名字在 order 里的位置也得换，否则 normalize_outer
            # 会把跑到外圈位置上的内圈名字当成"不在盘上"清掉。
            inner, outer = (a, b) if a_in else (b, a)
            p = outer - INNER_MAX
            if not (0 <= p < OUTER_MAX) or inner >= len(self.order):
                return False
            other = self.outer_slots[p]
            if other is None:
                return False          # 外圈那格空着：换过去内圈就缺一格了
            mine = self.order[inner]
            if other == mine or other not in self.order:
                return False
            i_mine = self.order.index(mine)
            i_other = self.order.index(other)
            if i_other < INNER_MAX:
                return False          # 数据不一致（外圈位置挂着内圈的名字）就不动
            self.order[i_mine], self.order[i_other] = other, mine
            self.outer_slots[p] = mine
            self.normalize_outer()
            return True

        pa, pb = a - INNER_MAX, b - INNER_MAX
        if not (0 <= pa < OUTER_MAX and 0 <= pb < OUTER_MAX):
            return False
        self.outer_slots[pa], self.outer_slots[pb] = (
            self.outer_slots[pb],
            self.outer_slots[pa],
        )
        return True

    def put_at_slot(self, sid: int, name: str) -> bool:
        """把音效放到指定槽位（从音效库拖过来的落点）。

        内圈沿用"格子对格子替换"；外圈额外支持放进空格子。
        """
        name = self.canon(name)
        if not name:
            return False
        if sid < INNER_MAX:
            if sid < len(self.order):
                if self.order[sid] == name:
                    return False
                return self.replace_at(sid, name)
            return self.add(name)
        p = sid - INNER_MAX
        if not (0 <= p < OUTER_MAX):
            return False
        cur = self.outer_slots[p]
        if cur == name:
            return False
        if name in self.order:
            # 已经在盘上：只在外圈内部换过去，跨圈会留下空洞
            q = self.slot_of(name)
            if q is None or q < INNER_MAX:
                return False
            self.swap_slots(INNER_MAX + p, q)
            self.normalize_outer()
            return True
        if cur is not None:
            idx = self.order.index(cur)
            self.order[idx] = name
            self.outer_slots[p] = name
            self.setting(name)
            return True
        if len(self.order) >= MAX_SLOTS:
            return False
        self.order.append(name)
        self.outer_slots[p] = name
        self.setting(name)
        return True

    # ---- 访问 ----
    def canon(self, name: str) -> str:
        """把"音效名"统一成配置里的键。

        历史包袱：配置键一直用文件名（`01 冰冰冰.wav`），但界面显示用的是
        去掉扩展名的 `01 冰冰冰`。两边混用会让参数被写到另一个键上，
        表现出来就是"调了音量不管用"。这里统一收口，谁传 stem 都能找到。
        """
        if not name:
            return name
        if name in self.items or name in self.order:
            return name
        stem = Path(name).stem
        # 传进来的只有裸文件名时，不拿它去配对"子文件夹里的同名文件"。
        # 否则 sounds/alpha.wav 的参数会被写到 sounds/整活/alpha.wav 上，
        # 表现为"调了音量不生效"。
        bare = "/" not in str(name).replace("\\", "/")
        for k in list(self.items) + list(self.order):
            if bare and "/" in str(k).replace("\\", "/"):
                continue
            if Path(k).stem == stem:
                return k
        return name

    def setting(self, name: str) -> SoundSetting:
        key = self.canon(name)
        st = self.items.get(key)
        if st is None:
            st = SoundSetting()
            self.items[key] = st
        return st

    def set_order(self, names: list[str]) -> None:
        self.order = list(names)
        self.normalize_outer()

    def remove(self, name: str) -> None:
        """把音效从轮盘上撤下来（不影响磁盘上的文件）。"""
        name = self.canon(name)
        if name in self.order:
            self.order.remove(name)
        self.items.pop(name, None)
        self.normalize_outer()

    def add(self, name: str, index: int | None = None) -> bool:
        """把音效放到轮盘上。已经在盘上则不动，返回是否发生了变化。"""
        name = self.canon(name)
        if name in self.order:
            return False
        if len(self.order) >= MAX_SLOTS:
            return False   # 内 8 + 外 12 已经排满
        if index is None or not (0 <= index <= len(self.order)):
            self.order.append(name)
        else:
            self.order.insert(index, name)
        self.setting(name)
        self.normalize_outer()
        return True

    def replace_at(self, index: int, name: str) -> bool:
        """把第 index 格换成 name（格子对格子替换）。

        与 place() 的区别：place 是"插进去，后面整体后移一格"，
        拖到盘上会看着像"多了一个"；这里格子数不变。
        被换下去的音效只是离开轮盘，仍在 sounds 目录里、参数也保留。

        如果拖进来的音效本来就在盘上（从音效库拖一个已经上盘的），
        两个格子**交换位置** —— 否则把它挪过来会顺手丢掉原来那格。
        """
        name = self.canon(name)
        if not (0 <= index < len(self.order)):
            return False
        if self.order[index] == name:
            return False
        if name in self.order:
            old = self.order.index(name)
            self.order[old], self.order[index] = self.order[index], self.order[old]
            self.normalize_outer()
            return True
        self.order[index] = name
        self.setting(name)
        self.normalize_outer()
        return True

    def place(self, name: str, index: int) -> bool:
        """放到指定槽位：已存在则移动过去，不存在则插进去。"""
        name = self.canon(name)
        if name in self.order:
            src = self.order.index(name)
            if src == index:
                return False
            self.order.pop(src)
            if src < index:
                index -= 1
            index = max(0, min(index, len(self.order)))
            self.order.insert(index, name)
            return True
        return self.add(name, index)

    def move(self, src: int, dst: int) -> bool:
        """轮盘内部拖动：把第 src 个槽位挪到第 dst 个位置。"""
        n = len(self.order)
        if not (0 <= src < n) or not (0 <= dst < n) or src == dst:
            return False
        item = self.order.pop(src)
        self.order.insert(dst, item)
        self.normalize_outer()
        return True

    def is_on_wheel(self, name: str) -> bool:
        return self.canon(name) in self.order

    def rename(self, old: str, new: str) -> None:
        if old == new:
            return
        if old in self.order:
            self.order[self.order.index(old)] = new
        if old in self.items:
            self.items[new] = self.items.pop(old)
        self.outer_slots = [new if n == old else n for n in self.outer_slots]
        self.normalize_outer()

    # ---- 组合音效 ----
    @staticmethod
    def combo_key(cid: str) -> str:
        return COMBO_PREFIX + cid

    def combo_of(self, key: str) -> ComboDef | None:
        """order 里的条目 -> 组合定义；不是组合键或组合已删则 None。"""
        if not is_combo_key(key):
            return None
        return self.combos.get(key[len(COMBO_PREFIX):])

    def display_name(self, key: str) -> str:
        """给界面看的名字：文件 -> 去扩展名，组合 -> ◆名字。"""
        c = self.combo_of(key) if is_combo_key(key) else None
        if c is not None:
            return f"◆{c.name}"
        if is_combo_key(key):
            return "◆（已删除的组合）"
        return Path(key).stem

    def new_combo(self, name: str = "新组合") -> ComboDef:
        """建一个空组合。cid 取现有最大编号 +1，删过的编号可以复用。"""
        n = 1
        while f"c{n}" in self.combos:
            n += 1
        # 名字重复不影响功能，但界面上分不清，顺手加个后缀
        base = name
        used = {c.name for c in self.combos.values()}
        k = 2
        while name in used:
            name = f"{base} {k}"
            k += 1
        c = ComboDef(cid=f"c{n}", name=name).clamped()
        self.combos[c.cid] = c
        return c

    def delete_combo(self, cid: str) -> None:
        """删组合：定义、轮盘引用、参数一起清，不留幽灵格子。"""
        key = self.combo_key(cid)
        self.combos.pop(cid, None)
        if key in self.order:
            self.order.remove(key)
        self.items.pop(key, None)
        self.outer_slots = [None if n == key else n for n in self.outer_slots]
        self.normalize_outer()

    def combo_setting(self, cid: str) -> SoundSetting:
        """组合在轮盘上的参数（音量/快捷键），和普通音效共用一套字典。"""
        return self.setting(self.combo_key(cid))

    def hotkey_groups(self) -> dict[str, list[str]]:
        """返回 {按键: [order 里的键, ...]}，用于直接触发。

        v0.9 起一个键可以挂**多个**音效：像"长按左键播 AAA、松手左键播 B"
        这种玩法，本来就是两个音效共用同一个键，各自按自己的触发方式响应。
        以前是一对一（谁后设谁生效），做不到这个。

        组合的专属热键不必先把组合拖到轮盘上才能用：轮盘只有 20 格，
        而"某条组合单独绑一个键"本身就是不占格子的用法，所以这里把
        没上盘、但设了热键的组合也一并登记。
        """
        out: dict[str, list[str]] = {}

        def _add(name: str) -> None:
            hk = (self.setting(name).hotkey or "").strip().lower()
            if not hk:
                return
            bucket = out.setdefault(hk, [])
            if name not in bucket:
                bucket.append(name)

        for name in self.order:
            _add(name)
        for cid in self.combos:
            key = self.combo_key(cid)
            if key not in self.order:
                _add(key)          # 已经在上面处理过了，别重复占一个键
        return out

    def hotkey_map(self) -> dict[str, str]:
        """兼容旧调用：{按键: 第一个绑这个键的音效}。

        新代码请用 hotkey_groups()，那个才是完整信息。
        """
        return {k: v[0] for k, v in self.hotkey_groups().items() if v}

    def global_hotkey_groups(self) -> dict[str, list[str]]:
        """{按键: [音效键, ...]}：勾了「全局通用」的音效，跨所有轮盘收集。

        和 hotkey_groups() 的区别是它**不看当前轮盘**：只要某个音效在它
        所在的那套轮盘里勾了全局通用，切到别的轮盘照样能按响。
        两边合起来用（轮盘内的 + 全局的），按键轮询那边再去重。
        """
        out: dict[str, list[str]] = {}
        for w in self.wheels:
            for key, st in (w.items or {}).items():
                if not getattr(st, "global_hotkey", False):
                    continue
                hk = (st.hotkey or "").strip().lower()
                if not hk:
                    continue          # 勾了全局却没绑键：没有意义，别占位
                bucket = out.setdefault(hk, [])
                if key not in bucket:
                    bucket.append(key)
        return out

    def global_names(self) -> list[str]:
        """所有勾了全局通用、且绑了键的音效键（去重，保持稳定顺序）。

        音频引擎拿它来决定"要不要为不在当前轮盘上的音效额外准备一份波形"。
        """
        seen: list[str] = []
        for key, st in self._items_all_wheels():
            if not getattr(st, "global_hotkey", False):
                continue
            if not (st.hotkey or "").strip():
                continue
            if key not in seen:
                seen.append(key)
        return seen

    def _items_all_wheels(self):
        """按"当前轮盘优先"的顺序遍历所有轮盘的 items，带轮盘 id。"""
        cur = self.cur_wheel()
        yield from cur.items.items()
        for w in self.wheels:
            if w.wid != cur.wid:
                yield from (w.items or {}).items()

    def setting_any(self, name: str) -> SoundSetting:
        """取音效参数，但不限于当前轮盘。

        快捷键可能来自"另一套轮盘里的全局音效"，那时当前轮盘的 items 里
        根本没有这条记录；如果直接走 setting()，会凭空造一份默认值出来，
        音量、变调、长按方式全部变成默认，听起来像设置丢了。

        优先级：当前轮盘有就用当前轮盘的（切过去之后按那套轮盘的参数走），
        否则找勾了全局通用那一套轮盘的原始参数。
        """
        key = self.canon(name)
        cur = self.cur_wheel()
        st = cur.items.get(key)
        if is_combo_key(key):
            # 组合的定义是全盘共用的，但「全局通用」这个勾记在各套轮盘的 items 里。
            # hotkey_groups() 每轮都会为组合在当前盘顺手建一条记录（热键为空），
            # 那条空壳不能当真：真正的触发方式/解锁条件在勾了全局的那一套里，
            # 直接返回它会把参数读成默认值，解锁键就白设了。
            if st is not None and getattr(st, "global_hotkey", False):
                return st
            for w in self.wheels:
                if w.wid == cur.wid:
                    continue
                other = (w.items or {}).get(key)
                if other is not None and getattr(other, "global_hotkey", False):
                    return other
            if st is not None:
                return st
            st = SoundSetting()
            cur.items[key] = st
            return st
        if st is not None:
            return st
        for w in self.wheels:
            if w.wid == cur.wid:
                continue
            other = (w.items or {}).get(key)
            if other is not None and getattr(other, "global_hotkey", False):
                return other
        st = SoundSetting()
        cur.items[key] = st
        return st

    def unlock_groups(self) -> dict[str, list[str]]:
        """返回 {解锁键: [音效键, ...]}。

        同一个解锁键按一下，会把名下所有音效一起解锁（各自按自己的
        解锁时间/次数算），所以 G 一次能同时放开 AAA 和 B。

        勾了「全局通用」的音效也算进来：它们可能在别的轮盘上，参数得用
        setting_any() 取，否则会读到当前轮盘凭空造出来的默认值（无条件），
        解锁键就白设了。
        """
        out: dict[str, list[str]] = {}
        groups = list(self.hotkey_groups().values())
        groups += list(self.global_hotkey_groups().values())
        for names in groups:
            for name in names:
                st = self.setting_any(name)
                if st.unlock_mode != UNLOCK_KEY:
                    continue
                key = (st.unlock_key or "").strip().lower()
                if not key:
                    continue      # 选了条件解锁却没设键：当作无条件，别把人锁死
                bucket = out.setdefault(key, [])
                if name not in bucket:
                    bucket.append(name)
        return out
