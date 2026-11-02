"""SR Voiceover Roulette - 游戏内音效轮盘

v0.2.0 的两处重做：
  1. 输入：不再读光标绝对位置（游戏把光标钉在准星，读到的永远是常量）。
     改用 Raw Input 拿鼠标硬件相对位移，自绘一个虚拟光标。
     轮盘绘制中心与判定基准强制为同一个点，物理上不可能错位。
  2. 音频：不再"每个槽位一个播放器"（每次播放都重新打开音频会话 → 电流声）。
     改成全程只开一个输出设备，程序自己混音，音效首尾各加淡入淡出。

v0.3.0：
  1. 位置：轮盘固定弹在屏幕正中，不再跟着光标跑（游戏把光标锁到别处时会弹歪）。
     想恢复旧行为把 config.json 的 wheel_anchor 改成 "cursor"。
  2. 配色：特征色改为绿色，统一收敛到 theme.py，界面与图标共用同一来源。

v0.4.0：
  1. 配置窗口（settings_window.py）：左侧三页签 + 右侧可拖拽轮盘预览。
  2. 轮盘从"自动全上"改成"手动挑选"，顺序与每音效参数存在 sounds.json。
  3. 每个音效独立音量、连击升/降调、独立直按快捷键。
  4. 托盘新增「设置…」入口，双击托盘也能打开。

v0.5.1（v0.4.0 的"很多功能点了没反应"大修）：
  1. 键名不统一导致单音效参数全部失效：sounds.json 用带扩展名的文件名做键，
     界面传的却是去掉扩展名的名字，参数写到了另一个键上，播放时读不到。
     现在统一由 SoundsConfig.canon() 收口，两边混用都能命中。
  2. 试听按钮不出声：同上，按名字找槽位时匹配不上。
  3. 快捷键页的两个动作键重开后显示"未绑定"，看着像没保存。
  4. 拖音量滑块会触发整盘音效重新解码（卡顿）：参数改动不再重解码。
  5. 按键冲突不再静默失效（重复上一个和呼出轮盘都绑 Y 时，按 Y 什么都不发生）。
  6. 快捷键输入框改成"按什么键就绑什么键"，不用手打 F1。
  7. 单击热键 = 轻按动作（默认重播上一个），长按才弹轮盘；
     所有按键框都能绑鼠标键（左/右/中/侧键1/侧键2）。
  8. 用户在文件夹里给音效改名后轮盘会被清空：改为按名字模糊配对认回原位。

v0.5.2：
  1. 鼠标键（左/右/中/侧键1/侧键2）全部当不了快捷键：RAWMOUSE 结构体
     少了 ulButtons 联合体那一层，ctypes 把 usButtonFlags 摆到了偏移 2 的
     对齐填充字节上，读到的永远是 0。补齐联合体后偏移与 C 定义一致（4）。
  2. 按键框加可见的 ✕ 清除按钮，取消绑定不用再靠"按 Delete"这种暗门。
  3. 变调新增「每次随机变调」：每按一次在 ±N 半音内抽一个整数半音，
     且不与上一次相同。

v0.5.3：
  1. 轮盘中空区域松手，从"什么也不做"改成"立刻停掉正在播的声音"。
     想让那句喊话闭嘴，指回中心松手就行，不用等它播完。
     停止带 12ms 淡出，避免从波形中间硬切出"啪"的爆音。
  2. 中空区域提示文案随状态变：有声音在响时显示"松开停止播放"，
     没声音时仍显示"松开取消"。

v0.5.4：
  1. 双环布局：内圈最多 8 个，第 9 个开始进外圈（12 个固定 30° 位置，
     没编入音效的格子不画）。内圈尺寸不变，外圈往外长，厚度可在
     「轮盘」页调（outer_thickness，默认 60px）。
  2. 拖放语义修正：从音效库拖到格子上是**替换**那一格（以前是插进去，
     看着像"多了一个"）；拖到中心才是追加到末尾；空的外圈格不接受拖放。
  3. 上限从 16 提到 20（内 8 + 外 12）。

v0.5.5：
  1. 轮盘中心不再是接近纯黑的实心圆，改成和普通格子同一套填充/描边。
  2. 外圈可以留空：12 个固定位置各摆谁都记在 sounds.json 的 outer_slots 里，
     把某一格拖到空位就挪过去、原位变空，所以外圈能分散到上/右/下/左，
     不必挤在一起。没编入的位置照样不画。
  3. 轮盘内部拖动改成"两格互换"（以前是整体挪动一格），内外圈之间不跨圈。
  4. 内圈外圈之间不再留缝（OUTER_GAP = 0），两圈连成一整块。

设计约束（沿用已在本游戏验证过的方案）：
  - 不安装键盘/鼠标钩子，不拦截任何输入（Raw Input 只是"旁听"设备数据）
  - 置顶窗口为分层窗口，整窗鼠标穿透，且不抢游戏焦点
  - 不读取游戏内存、不注入进程、不模拟输入、不联网

运行：python sr_roulette.py
"""

from __future__ import annotations

import ctypes
import json
import math
import os
import random
import sys
import time
from ctypes import wintypes
from pathlib import Path

import numpy as np
from PySide6.QtCore import (
    QAbstractNativeEventFilter,
    QEasingCurve,
    QEventLoop,
    QIODevice,
    QObject,
    QPoint,
    QPointF,
    QRectF,
    Qt,
    QTimer,
    QUrl,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)
from PySide6.QtMultimedia import (
    QAudio,
    QAudioDecoder,
    QAudioFormat,
    QAudioSink,
    QAudioSource,
    QMediaDevices,
    QMediaPlayer,
)
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from sounds_config import (
    COMBO_PREFIX,
    ComboDef,
    INNER_MAX,
    MAX_SLOTS,
    OUTER_MAX,
    PITCH_DOWN,
    PITCH_FIXED,
    PITCH_NONE,
    PITCH_RANDOM,
    SPEED_DOWN,
    SPEED_NONE,
    TRIG_COMBO,
    TRIG_PREV_END,
    TRIG_PREV_START,
    SoundsConfig,
    is_combo_key,
)
import theme
from theme import accent, accent_dark, accent_light, set_accent

APP_NAME = "SR Voiceover Roulette"
APP_VERSION = "v0.8.2"

DEBUG = os.environ.get("SR_DEBUG") == "1"

AUDIO_EXTS = (".wav", ".mp3", ".ogg", ".flac", ".m4a")

# 显式指定字体：不指定时 Qt 走默认链，某些环境下会挑到没有中文字形的字体，
# 屏幕上就变成一串方块。微软雅黑在所有中文 Windows 上都存在。
UI_FONT = "Microsoft YaHei UI"

# 特征色集中在 theme.py：轮盘、托盘图标、exe 图标共用同一份来源

# ---------------------------------------------------------------- Win32

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000

WM_INPUT = 0x00FF
RID_INPUT = 0x10000003
RIM_TYPEMOUSE = 0
RIDEV_INPUTSINK = 0x00000100
MOUSE_MOVE_ABSOLUTE = 0x01

# Raw Input 的鼠标按键位（UP = DOWN << 1）
RI_MOUSE_BUTTON_DOWN = {
    "mouse_left": 0x0001,
    "mouse_right": 0x0004,
    "mouse_middle": 0x0010,
    "mouse_4": 0x0040,   # 侧键 1
    "mouse_5": 0x0100,   # 侧键 2
}
MOUSE_KEYS = tuple(RI_MOUSE_BUTTON_DOWN)

# 轮盘弹出来之后，按这两个键 = 立刻取消这次呼出（松手也不会播任何东西）。
# 游戏里的习惯动作：想反悔就点一下左键或右键。
WHEEL_CANCEL_KEYS = ("mouse_left", "mouse_right")

user32 = ctypes.WinDLL("user32", use_last_error=True)


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
        ("dwFlags", wintypes.DWORD),
        ("hwndTarget", wintypes.HWND),
    ]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", wintypes.DWORD),
        ("dwSize", wintypes.DWORD),
        ("hDevice", wintypes.HANDLE),
        ("wParam", wintypes.WPARAM),
    ]


class _MOUSEBUTTONS(ctypes.Structure):
    """RAWMOUSE 里那个 ulButtons 联合体中匿名结构的形状。"""
    _fields_ = [
        ("usButtonFlags", wintypes.USHORT),
        ("usButtonData", wintypes.USHORT),
    ]


class _MOUSEBUTTONUNION(ctypes.Union):
    """必须是联合体，不能把 usButtonFlags 直接平铺在 usFlags 后面。

    C 定义里 ulButtons 是 ULONG，要求 4 字节对齐，所以 usFlags(2 字节)
    之后有 2 字节填充，usButtonFlags 实际落在偏移 4。
    早先把它平铺成 USHORT/USHORT/USHORT 时 ctypes 会把 usButtonFlags
    放到偏移 2（填充字节上），读到的永远是 0 —— 表现就是"鼠标左/右/中/侧键
    全都当不了快捷键"，而鼠标移动（lLastX 偏移恰好正确）一直正常，
    把这个坑藏了很久。
    """
    _anonymous_ = ("s",)
    _fields_ = [
        ("ulButtons", wintypes.ULONG),
        ("s", _MOUSEBUTTONS),
    ]


class RAWMOUSE(ctypes.Structure):
    _anonymous_ = ("buttons",)
    _fields_ = [
        ("usFlags", wintypes.USHORT),
        ("buttons", _MOUSEBUTTONUNION),
        ("ulRawButtons", wintypes.ULONG),
        ("lLastX", wintypes.LONG),
        ("lLastY", wintypes.LONG),
        ("ulExtraInformation", wintypes.ULONG),
    ]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("mouse", RAWMOUSE)]


def vk_of(name: str) -> int:
    """把配置里的按键名转成虚拟键码。"""
    name = (name or "y").strip().lower()
    if len(name) == 1 and name.isalpha():
        return ord(name.upper())
    if len(name) == 1 and name.isdigit():
        return ord(name)
    if name.startswith("f") and name[1:].isdigit():
        n = int(name[1:])
        if 1 <= n <= 24:
            return 0x6F + n
    table = {
        "space": 0x20, "tab": 0x09, "enter": 0x0D, "esc": 0x1B,
        "shift": 0x10, "ctrl": 0x11, "alt": 0x12, "capslock": 0x14,
        "win": 0x5B, "lwin": 0x5B, "rwin": 0x5C,
        "comma": 0xBC, "period": 0xBE, "slash": 0xBF,
        "semicolon": 0xBA, "quote": 0xDE,
        "lshift": 0xA0, "rshift": 0xA1, "lctrl": 0xA2, "rctrl": 0xA3,
        "lalt": 0xA4, "ralt": 0xA5,
        "mouse_left": 0x01, "mouse_right": 0x02, "mouse_mid": 0x04,
        # 侧键：GetAsyncKeyState 对这两个不可靠，正常走 Raw Input，这里只作兜底
        "mouse_middle": 0x04, "mouse_4": 0x05, "mouse_5": 0x06,
    }
    return table.get(name, 0x59)


# ---- 组合键 ----
# 修饰键统一映射到通用名：GetAsyncKeyState 查 0x11 时左右两个 Ctrl 都算按下，
# 所以 "ctrl+y" 对左右手都成立，不用逼用户记住自己绑的是哪一只。
_SPEC_MODS = {
    "ctrl": "ctrl", "control": "ctrl", "lctrl": "ctrl", "rctrl": "ctrl",
    "shift": "shift", "lshift": "shift", "rshift": "shift",
    "alt": "alt", "lalt": "alt", "ralt": "alt",
    "win": "win", "meta": "win", "cmd": "win", "super": "win",
    "lwin": "win", "rwin": "win",
}
_MOD_ORDER = {"ctrl": 0, "alt": 1, "shift": 2, "win": 3}

_SPEC_LABEL = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win"}


def spec_parts(spec: str) -> list[str]:
    """把 "ctrl+shift+y" 拆成 ["ctrl", "shift", "y"]，顺带规范化。

    修饰键统一成 ctrl / alt / shift / win 四个通用名（左右不分），
    并把顺序固定成 ctrl → alt → shift → win → 主键。这样
    "shift+ctrl+y" 和 "ctrl+shift+y" 会被认成同一个绑定，
    冲突检查才不会因为书写顺序不同而漏判。

    单个键的旧写法（"y" / "f1" / "mouse_4"）走同一条路径，原样返回。
    """
    raw = [p.strip().lower() for p in str(spec or "").split("+")]
    raw = [p for p in raw if p]
    if not raw:
        return []
    mods: list[str] = []
    keys: list[str] = []
    for p in raw:
        canon = _SPEC_MODS.get(p)
        if canon is not None:
            if canon not in mods:
                mods.append(canon)
        else:
            keys.append(p)
    mods.sort(key=lambda m: _MOD_ORDER.get(m, 9))
    return mods + keys[:1]


def norm_spec(spec: str) -> str:
    """规范化后的字符串形式，用来存配置和比较冲突。"""
    return "+".join(spec_parts(spec))


def spec_label(spec: str) -> str:
    """给人看的写法：ctrl+shift+y -> "Ctrl + Shift + Y"。"""
    parts = spec_parts(spec)
    if not parts:
        return ""
    return " + ".join(_SPEC_LABEL.get(p, p.upper()) for p in parts)



def is_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def cursor_pos() -> tuple[int, int]:
    p = POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def sector_from_delta(dx: float, dy: float, n: int, deadzone: float) -> int | None:
    """根据虚拟光标相对轮盘中心的位移判断落在第几个扇区。

    0 号扇区从正上方开始，顺时针编号。位移小于死区时返回 None，
    避免手抖误触发。
    """
    if n <= 0:
        return None
    if math.hypot(dx, dy) < float(deadzone):
        return None
    # 屏幕坐标 y 向下，atan2 得到的是"数学角"的取负，+90 对齐到"正上方为 0 号"
    ang = (math.degrees(math.atan2(dy, dx)) + 90.0) % 360.0
    return int(ang // (360.0 / n)) % n


def clamp_offset(x: float, y: float, limit: float) -> tuple[float, float]:
    """摇杆式软钳制：推过头就停在边界上，反向推立刻回退。"""
    dist = math.hypot(x, y)
    if dist <= limit or dist == 0.0:
        return x, y
    scale = limit / dist
    return x * scale, y * scale


# ---------------------------------------------------------------- 轮盘几何

OUTER_GAP = 0.0   # 内圈与外圈之间的缝。0 = 两圈紧贴成一整块（默认）


def wheel_scale_of(cfg: dict) -> float:
    """用户设的「整体大小」，1.0 = 100%。

    这一层缩放乘在轮盘的每一个像素尺寸上（内圈半径、中空半径、外圈厚度、
    字号、中心提示的行距……），所以它是"整体大小"，不是"内圈大小"。
    设置窗口里调的时候所有判定和绘制都走同一个值，不会出现
    "看着是这么大、选起来是那么大"。
    """
    try:
        v = float(cfg.get("wheel_scale", 1.0) or 1.0)
    except (TypeError, ValueError):
        return 1.0
    return max(0.5, min(2.0, v))


# 设置窗口的预览最多要装得下「整体大小」拉到 140%，所以 100% 的时候
# 只占预览框的 1/1.4 ≈ 71%，剩下的余量留给滑块往右拖时变大。
PREVIEW_SCALE_MAX = 1.4


def ring_layout(cfg: dict, count: int, scale: float = 1.0) -> dict:
    """算出轮盘每一层的半径范围与格数。

    只有不超过 8 个音效时是单环（和以前完全一样，均匀等分）；
    第 9 个进来才长出外圈：内圈固定 8 格、外圈固定 12 个位置（30° 一格），
    已经编入的才画，空的格子不画。

    scale 是"最终缩放系数"，调用方自己把「整体大小」（wheel_scale_of）算进去：
    游戏里直接传 wheel_scale_of(cfg)，配置窗口的预览再乘一个自适应的适配比例。
    """
    r_in = float(cfg["wheel_radius"]) * scale
    hole = r_in * float(cfg["inner_ratio"])
    two_ring = count > INNER_MAX
    geo = {
        "two_ring": two_ring,
        "hole": hole,
        "inner_n": INNER_MAX if two_ring else max(1, count),
        "inner_r0": hole,
        "inner_r1": r_in,
        "outer_n": 0,
        "outer_r0": r_in,
        "outer_r1": r_in,
        "extent": r_in,        # 轮盘最外缘（窗口大小按它算）
    }
    if two_ring:
        gap = OUTER_GAP * scale
        thick = max(24.0, float(cfg.get("outer_thickness", 60))) * scale
        # 外圈紧贴内圈外缘（gap=0 时 outer_r0 == inner_r1），两圈连成一整块
        geo["outer_r0"] = r_in + gap
        geo["outer_r1"] = r_in + gap + thick
        geo["outer_n"] = max(0, min(count - INNER_MAX, OUTER_MAX))
        geo["extent"] = r_in + gap + thick
    return geo


def ring_sector_path(cx: float, cy: float, r0: float, r1: float,
                     start_deg: float, span_deg: float) -> QPainterPath:
    """环形扇区（甜甜圈切一块）。r0 为 0 时退化成从圆心出发的扇形。"""
    path = QPainterPath()
    rect_o = QRectF(cx - r1, cy - r1, r1 * 2, r1 * 2)
    if r0 <= 0.5:
        path.moveTo(cx, cy)
        path.arcTo(rect_o, start_deg, -span_deg)
    else:
        rect_i = QRectF(cx - r0, cy - r0, r0 * 2, r0 * 2)
        path.arcMoveTo(rect_o, start_deg)
        path.arcTo(rect_o, start_deg, -span_deg)
        path.arcTo(rect_i, start_deg - span_deg, span_deg)
    path.closeSubpath()
    return path


def slot_geometry(geo: dict, sid: int):
    """槽位号画在哪儿：(内缘半径, 外缘半径, 起始角, 张角)；画不出来返回 None。

    槽位号 sid 是"位置"不是"第几个音效"：0~7 是内圈，8~19 是外圈那 12 个
    固定位置。外圈允许留空，所以位置和音效序号是两回事。
    """
    if sid < 0:
        return None
    if sid < INNER_MAX:
        if sid >= geo["inner_n"]:
            return None
        span = 360.0 / max(1, geo["inner_n"])
        return geo["inner_r0"], geo["inner_r1"], 90.0 - sid * span, span
    k = sid - INNER_MAX
    if not geo["two_ring"] or k >= OUTER_MAX:
        return None
    span = 360.0 / OUTER_MAX
    return geo["outer_r0"], geo["outer_r1"], 90.0 - k * span, span


def outer_index_map_of(bank) -> list[int | None]:
    """外圈 12 个位置 -> 摆在那儿的音效在 bank 里的下标；空位是 None。"""
    fn = getattr(bank, "outer_index_map", None)
    if callable(fn):
        try:
            return list(fn())
        except Exception:
            pass
    # 兜底：不认识摆位表就按顺序从第 0 格排起
    n = max(0, len(bank) - INNER_MAX)
    return [INNER_MAX + p if p < n else None for p in range(OUTER_MAX)]


def index_of_slot(sid: int | None, count: int,
                  outer_map: list[int | None] | None = None) -> int | None:
    """槽位号 -> 音效下标；那一格空着（或越界）返回 None。

    槽位号是"位置"（0~7 内圈、8~19 外圈 12 个固定位置），音效下标是"第几个音效"。
    内圈永远满员，所以内圈里两者数值恰好相等——这正是坑所在：v0.5.5 把拖放数据
    从"音效下标"换成"槽位号"之后，凡是还拿它直接当 order[...] 用的地方，
    内圈看不出问题，外圈（8~19）一律错位。所有这种换算都必须过这一层。
    """
    if sid is None or sid < 0 or count <= 0:
        return None
    if sid < INNER_MAX:
        return sid if sid < count else None
    table = list(outer_map) if outer_map is not None else None
    if table is None:
        extra = max(0, count - INNER_MAX)
        table = [INNER_MAX + p if p < extra else None for p in range(OUTER_MAX)]
    k = sid - INNER_MAX
    return table[k] if 0 <= k < len(table) else None


def index_from_delta(dx: float, dy: float, count: int, deadzone: float,
                     cfg: dict, scale: float = 1.0,
                     outer_map: list[int | None] | None = None) -> int | None:
    """虚拟光标位移 -> 音效下标；落在中空区或空的外圈格返回 None。

    0 号从正上方开始顺时针。距离决定内圈/外圈，角度决定是哪一格。
    outer_map 是外圈摆位表（位置 -> 音效下标），不传就按顺序从第 0 格排起。

    ★ 中空区判定 = 画面上那块空白的半径（geo["hole"]），**不是** fixed 像素死区。
    以前这里用的是 cfg["deadzone_px"]（默认 24px），而画出来的中空半径是
    wheel_radius × inner_ratio（默认 180 × 0.42 ≈ 76px）——两个数毫无关系，
    结果就是"光标还在白圈里、某一格已经亮了"，而且怎么调中空比例都不变。
    现在唯一的口径是中空半径：中心留白多大，能"不选中"的范围就多大。
    deadzone 参数只为兼容老调用方留着，已经不再参与判定。
    """
    if count <= 0:
        return None
    dist = math.hypot(dx, dy)
    geo = ring_layout(cfg, count, scale)
    if dist < float(geo["hole"]):
        return None
    if geo["two_ring"] and dist >= geo["outer_r0"]:
        pos = sector_from_delta(dx, dy, OUTER_MAX, 0.0)
        if pos is None:
            return None
        table = outer_map
        if table is None:      # 没给摆位表：当作从第 0 格开始依次排满
            extra = max(0, count - INNER_MAX)
            table = [INNER_MAX + p if p < extra else None for p in range(OUTER_MAX)]
        if pos >= len(table):
            return None
        return table[pos]     # None = 这一格空着，等于没指任何东西
    return sector_from_delta(dx, dy, int(geo["inner_n"]), 0.0)


def wheel_angle(dx: float, dy: float) -> float:
    """位移 -> 轮盘角度（0° 指向正上方，顺时针增大），和扇区编号同一套约定。"""
    return (math.degrees(math.atan2(dy, dx)) + 90.0) % 360.0


def pos_from_angle(ang: float, span: float) -> int:
    """角度 -> 外圈的第几个位置（0 ~ OUTER_MAX-1）。"""
    return min(int(ang // span), OUTER_MAX - 1)


def clamp_to_filled(vx: float, vy: float, cfg: dict, count: int,
                    scale: float = 1.0,
                    outer_map: list[int | None] | None = None,
                    prev: tuple[float, float] | None = None) -> tuple[float, float]:
    """把虚拟光标挡在"有音效的格子"里，而且绝不许跨过空白格去够远处的格子。

    内圈一定是满的，只有外圈会留空。所以半径还在内圈里就原样放行。

    进了外圈带又落在空白格上时，墙在哪儿要靠 prev（上一帧已经被夹过的位置）
    来定，不然就会"瞬移"：
      · 上一帧站在有音效的外圈格里 -> 这一帧最多滑到这一格自己的边界上停住，
        绝不越过旁边的空白去贴另一头的格子（那正是看起来像瞬移的原因）
      · 上一帧的角度本来就落在空白上（人还在内圈里）-> 外圈这一片整块过不去，
        半径顶在内外圈分界处、角度一动不动，手感就是"推到这里推不动了"
    prev 给 None 时退化成"贴落点最近的边界"，只留给离线测试用。
    """
    geo = ring_layout(cfg, count, scale)
    if count <= 0 or not geo["two_ring"]:
        return vx, vy
    dist = math.hypot(vx, vy)
    if dist < geo["outer_r0"]:
        return vx, vy          # 内圈整圈都有音效，站哪儿都算数

    table = list(outer_map) if outer_map is not None else None
    if table is None:          # 没给摆位表：当作从第 0 格开始依次排满
        extra = max(0, count - INNER_MAX)
        table = [INNER_MAX + p if p < extra else None for p in range(OUTER_MAX)]
    if len(table) < OUTER_MAX:
        table += [None] * (OUTER_MAX - len(table))
    if all(t is not None for t in table[:OUTER_MAX]):
        return vx, vy          # 外圈排满了，一堵墙都没有

    span = 360.0 / OUTER_MAX
    eps = span * 0.02          # 停在边界"内侧"这么一点，保证判定仍算在这一格里
    ang = wheel_angle(vx, vy)
    pos = pos_from_angle(ang, span)
    if table[pos] is not None:
        return vx, vy

    if prev is not None and math.hypot(*prev) >= 1e-6:
        p_ang = wheel_angle(*prev)
        p0 = pos_from_angle(p_ang, span)
        if table[p0] is None:
            # 人还在内圈、方向又冲着空白：外圈过不去，顶在分界处，角度不动。
            # 半径是连续收进去的，所以看不出任何跳变。
            r = min(dist, geo["outer_r0"] - 1.0)
            rad = math.radians(p_ang)
            return r * math.sin(rad), -r * math.cos(rad)
        # 站在有音效的格子里：贴着它朝落点方向的那条边界内侧停下
        clockwise = 1 <= (pos - p0) % OUTER_MAX <= OUTER_MAX // 2
        target = (p0 + 1) * span - eps if clockwise else p0 * span + eps
        rad = math.radians(target)
        return dist * math.sin(rad), -dist * math.cos(rad)

    # 没有历史位置（离线测试 / 刚呼出）：只能贴落点最近的边界
    low = high = None
    for i in range(1, OUTER_MAX):
        q = pos - i
        if low is None and table[q % OUTER_MAX] is not None:
            low = (q + 1) * span - eps     # 那个格子的顺时针边界
        q = pos + i
        if high is None and table[q % OUTER_MAX] is not None:
            high = q * span + eps          # 那个格子的逆时针边界
        if low is not None and high is not None:
            break
    cands = [a for a in (low, high) if a is not None]
    if not cands:
        return vx, vy
    target = min(cands, key=lambda a: min((ang - a) % 360.0, (a - ang) % 360.0))

    rad = math.radians(target)
    return dist * math.sin(rad), -dist * math.cos(rad)


# ---------------------------------------------------------------- Raw Input

class RawMouse(QObject):
    """后台旁听鼠标硬件位移。

    关键点：lLastX / lLastY 是驱动层给出的相对位移，跟光标当前停在哪无关。
    游戏把光标钉死在准星上时，这里照样能读到手的真实移动。

    这里只"接收"数据，不拦截、不改写，游戏收到的输入完全不受影响。
    """

    def __init__(self) -> None:
        super().__init__()
        self._dx = 0.0
        self._dy = 0.0
        self._events = 0
        self._absolute_events = 0
        self.registered = False
        # 鼠标按键状态。键盘走 GetAsyncKeyState，鼠标侧键那个 API 不可靠，
        # 所以统一从 Raw Input 的 usButtonFlags 拿。
        self._btn_state: dict[str, bool] = {k: False for k in MOUSE_KEYS}

        # 1x1 的离屏窗口，只为给 Raw Input 提供一个投递目标，用户完全看不到
        self._host = QWidget(
            None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus
        )
        self._host.setAttribute(Qt.WA_TranslucentBackground, True)
        self._host.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._host.setFocusPolicy(Qt.NoFocus)
        self._host.setGeometry(-30000, -30000, 1, 1)
        self._host.show()
        self._host.hide()

    def start(self, app: QApplication) -> bool:
        dev = RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK, int(self._host.winId()))
        ok = bool(
            user32.RegisterRawInputDevices(
                ctypes.byref(dev), 1, ctypes.sizeof(RAWINPUTDEVICE)
            )
        )
        self.registered = ok
        if not ok:
            _log(f"[raw] RegisterRawInputDevices 失败 err={ctypes.get_last_error()}")
            return False
        self._filter = _RawFilter(self)
        app.installNativeEventFilter(self._filter)
        return True

    def _on_raw(self, mouse: RAWMOUSE) -> None:
        # 按键状态要先取：绝对坐标事件里也可能带按键
        flags = mouse.usButtonFlags
        if flags:
            for name, down_bit in RI_MOUSE_BUTTON_DOWN.items():
                if flags & down_bit:
                    if DEBUG and not self._btn_state[name]:
                        _log(f"[raw] {name} 按下")
                    self._btn_state[name] = True
                elif flags & (down_bit << 1):
                    if DEBUG and self._btn_state[name]:
                        _log(f"[raw] {name} 松开")
                    self._btn_state[name] = False

        if mouse.usFlags & MOUSE_MOVE_ABSOLUTE:
            # 远程桌面 / 数位板之类走绝对坐标，这里不做换算，直接跳过
            self._absolute_events += 1
            return
        self._events += 1
        self._dx += mouse.lLastX
        self._dy += mouse.lLastY

    def button_down(self, name: str) -> bool:
        return bool(self._btn_state.get(name, False))

    def take(self) -> tuple[float, float]:
        """取走并清零自上次调用以来的累计位移。"""
        d = (self._dx, self._dy)
        self._dx = self._dy = 0.0
        return d

    def drop(self) -> None:
        self._dx = self._dy = 0.0

    @property
    def stats(self) -> tuple[int, int]:
        return self._events, self._absolute_events


class _RawFilter(QAbstractNativeEventFilter):
    def __init__(self, owner: RawMouse) -> None:
        super().__init__()
        self.owner = owner

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        try:
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message != WM_INPUT:
                return False, 0

            size = wintypes.UINT(0)
            user32.GetRawInputData(msg.lParam, RID_INPUT, None,
                                   ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
            if size.value == 0:
                return False, 0
            buf = ctypes.create_string_buffer(size.value)
            got = user32.GetRawInputData(msg.lParam, RID_INPUT, buf,
                                         ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
            if got == 0:
                return False, 0
            ri = ctypes.cast(buf, ctypes.POINTER(RAWINPUT)).contents
            if ri.header.dwType == RIM_TYPEMOUSE:
                self.owner._on_raw(ri.mouse)
        except Exception as exc:  # 输入回调里绝不能抛，抛了会影响到主循环
            _log(f"[raw] 处理 WM_INPUT 异常: {exc}")
        return False, 0


# ---------------------------------------------------------------- 配置

CONFIG_VERSION = 3


def _app_dir() -> Path:
    """打包成 exe 后 __file__ 指向临时解压目录，必须改用 exe 所在目录，
    否则 sounds / config 会读写到一个每次重启都会消失的地方。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = _app_dir()
CONFIG_PATH = BASE_DIR / "config.json"
SOUNDS_CONFIG_PATH = BASE_DIR / "sounds.json"
SOUNDS_DIR = BASE_DIR / "sounds"
LOG_PATH = BASE_DIR / "sr_roulette.log"


def sound_key(path: Path) -> str:
    """音效在配置里的键：相对 sounds 目录的路径，一律用 `/` 分隔。

    顶层文件就是 `冰冰冰.wav`（和老版本存的一模一样，旧配置不用迁移），
    子文件夹里的是 `整活/冰冰冰.wav`。这样同名文件放进不同文件夹不会打架。
    """
    try:
        rel = path.relative_to(SOUNDS_DIR)
    except ValueError:
        return path.name
    return rel.as_posix()


def sound_path(key: str) -> Path:
    """配置键 -> 磁盘路径。键里带子目录时自然拼进对应文件夹。"""
    if not key:
        return SOUNDS_DIR / ""
    return SOUNDS_DIR / Path(str(key).replace("\\", "/"))


def is_audio_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in AUDIO_EXTS


def scan_sound_files() -> list[tuple[str, Path]]:
    """递归扫描 sounds 目录，返回 (配置键, 绝对路径)，按路径排序。

    子文件夹里的音效也算 —— 用户想用文件夹分类整理音效，这是唯一的入口。
    隐藏文件夹（以 . 开头）跳过，避免把 .git 之类的东西扫进来。
    """
    out: list[tuple[str, Path]] = []
    if not SOUNDS_DIR.exists():
        return out
    try:
        for p in SOUNDS_DIR.rglob("*"):
            try:
                rel = p.relative_to(SOUNDS_DIR)
            except ValueError:
                continue
            if any(part.startswith(".") for part in rel.parts):
                continue
            if is_audio_file(p):
                out.append((rel.as_posix(), p))
    except Exception as exc:
        _log(f"[sound] 扫描 sounds 目录失败: {exc}")
    out.sort(key=lambda kv: kv[0].lower())
    return out



def _log(msg: str) -> None:
    """windowed 模式没有控制台，直接 print 会抛异常，统一走这里。
    exe 模式下同时落一份日志，方便用户反馈问题时排查。"""
    try:
        print(msg)
    except Exception:
        pass
    if getattr(sys, "frozen", False):
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%m-%d %H:%M:%S')} {msg}\n")
        except Exception:
            pass


DEFAULT_CONFIG = {
    "config_version": CONFIG_VERSION,
    "hotkey": "y",
    # 单击热键 = 轻按动作（默认重播上一个），所以这个阈值要留够：
    # 设得太小，正常"单击"会被判成长按，一按就弹轮盘
    "hold_ms": 220,
    "volume": 0.8,
    # 槽位上限：内圈 8 + 外圈 12。实际格子数 = 已编入轮盘的音效数
    "slots": MAX_SLOTS,
    "outer_thickness": 60,   # 外圈那条环的厚度(px)，只有出现外圈时才用得上
    "sensitivity": 0.85,     # Raw Input 位移 → 虚拟光标位移的倍率
    "noise_floor": 2,        # 每次轮询位移不超过这个值视为手抖，丢弃
    "max_offset_ratio": 0.9,  # 虚拟光标最远能推到轮盘半径的多少
    "wheel_radius": 180,
    "inner_ratio": 0.42,
    # 整体大小：1.0 = 100%。乘在轮盘的每一个像素尺寸上（内圈、中空、外圈厚度、
    # 字号、中心提示），绘制与判定共用，所以放大缩小都不会"看着大、选着小"。
    "wheel_scale": 1.0,
    # 轮盘弹出位置：screen = 固定屏幕正中（推荐），cursor = 跟随鼠标
    "wheel_anchor": "screen",
    "opacity": 0.94,
    "show_names": True,
    # 动画总开关（设置页「轮盘」那一栏）：关掉就全部瞬间显示/瞬间消失。
    # 有人晕动/或者嫌动画挡视线，给一个一刀切的出口。
    "animations": True,
    "poll_ms": 8,
    "fade_ms": 6,
    "audio_buffer_ms": 60,
    # ---- 快捷动作：空字符串表示不绑定 ----
    "repeat_last_key": "",   # 重复播放上一个音效
    "cycle_key": "",         # 按槽位顺序播放下一个
    # 呼出"切换轮盘的轮盘"的键：按住弹出、划到哪套松手就切到哪套。
    # 默认不绑定——多一个键就多一份和游戏键位打架的风险，谁需要谁自己开。
    "switch_key": "",
    # 轻按（没长到弹轮盘）时做什么：none / repeat_last / next
    # 默认 repeat_last：单击热键重播上一个音效，长按才弹轮盘
    "tap_action": "repeat_last",
    # ---- 外观 ----
    # 应用主题色：托盘图标、设置界面的高亮/滑块/选中态。任意色值，不是只有四个预设。
    # 轮盘本身的颜色不在这里，它跟着每套轮盘走（见 sounds.json 的 wheels[].color）
    "accent_color": "#2ed36c",
    "accent_theme": "green",  # 老版本的字段名，只为兼容旧配置保留
    # 每次启动都先把配置窗口打开（在「快捷键」页可以关掉）
    "open_settings_on_start": True,
    # 开机自启动：写当前用户注册表的 Run 项（在「快捷键」页开关）
    "autostart": False,
    # 首次启动那张「去看看常见问题」的引导卡看过没有（看过就不再弹）
    "help_tip_shown": False,
    # ---- 麦克风注入（要把音效送进游戏语音，必须有虚拟声卡，比如 VB-CABLE）----
    "mic_enabled": False,
    "mic_device": "",         # 采集设备名，空 = 自动挑一个真实麦克风
    "cable_device": "",       # 虚拟声卡播放设备名，空 = 自动找名字带 CABLE 的
    "mic_gain": 0.9,          # 你自己的原声送给对方多响
    "cable_effect_gain": 1.0,  # 音效送给对方多响
    "monitor_enabled": True,  # 音效是否也从自己耳机里放出来
    "mic_latency_ms": 60,     # 麦克风缓冲留多少余量，太小吃时钟漂移、太大手慢
}

# 老版本没有这些手感参数，混用会让"手感差"的问题继续存在，所以只继承用户真正在意的项
_CARRY_OVER_KEYS = (
    "hotkey", "volume", "opacity", "show_names", "wheel_radius", "wheel_scale",
    "hold_ms", "repeat_last_key", "cycle_key", "tap_action",
    "sensitivity", "noise_floor",
)


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    has_color = False
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if data.get("config_version") == CONFIG_VERSION:
                    cfg.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
                else:
                    # 老配置：只保留用户的个性化项，手感参数一律用新默认值
                    for k in _CARRY_OVER_KEYS:
                        if k in data:
                            cfg[k] = data[k]
                    _log("[config] 检测到旧版配置，手感参数已重置为新默认值")
                has_color = "accent_color" in data
                if not has_color and data.get("accent_theme"):
                    cfg["accent_theme"] = data["accent_theme"]
        except Exception as exc:
            _log(f"[config] 读取失败，使用默认值: {exc}")
    # 老配置只有四个预设名（accent_theme），没有自由色值：翻成对应的 RGB
    if not has_color:
        cfg["accent_color"] = theme.rgb_to_hex(
            theme.PALETTES.get(str(cfg.get("accent_theme") or "green"), theme.DEF_ACCENT)
        )
    else:
        cfg["accent_color"] = theme.rgb_to_hex(theme.hex_to_rgb(cfg["accent_color"]))
    return cfg


def save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        _log(f"[config] 保存失败: {exc}")


# ---------------------------------------------------------------- 开机自启

_AUTOSTART_VALUE = "SR Voiceover Roulette"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_supported() -> bool:
    """只有打包版（exe）能自启：源码运行注册 pythonw 反而添乱。"""
    return bool(getattr(sys, "frozen", False))


def _autostart_read(value_name: str = _AUTOSTART_VALUE) -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            v, _t = winreg.QueryValueEx(k, value_name)
            return str(v)
    except OSError:
        return None


def autostart_active() -> bool:
    return _autostart_read() is not None


def set_autostart(enable: bool, value_name: str = _AUTOSTART_VALUE) -> bool:
    """写/删 HKCU 的 Run 项（只动自己名字的那个键，不碰别人）。

    值带引号：路径里有空格时 Windows 才不会把前半截当程序名。
    """
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as k:
            if enable:
                winreg.SetValueEx(
                    k, value_name, 0, winreg.REG_SZ, f'"{sys.executable}"'
                )
            else:
                try:
                    winreg.DeleteValue(k, value_name)
                except FileNotFoundError:
                    pass
        return True
    except OSError as exc:
        _log(f"[autostart] 注册表写入失败: {exc}")
        return False


def sync_autostart(cfg: dict) -> None:
    """启动时对齐注册表和配置：开了就写（exe 挪过位置也顺手更新），关了就删。"""
    if not autostart_supported():
        return
    want = bool(cfg.get("autostart", False))
    if want or autostart_active():
        set_autostart(want)


# ---------------------------------------------------------------- 音效库

class ComboEntry:
    """轮盘上的组合音效条目。

    和文件条目放同一个列表里占一个槽位，对外露出和 Path 相同的两个只读
    属性（name = 配置键，stem = 显示名），这样轮盘绘制、槽位详情不用分叉。
    """

    def __init__(self, cdef: ComboDef) -> None:
        self.cdef = cdef

    @property
    def key(self) -> str:
        return COMBO_PREFIX + self.cdef.cid

    @property
    def name(self) -> str:
        return self.key

    @property
    def stem(self) -> str:
        return f"◆{self.cdef.name}"


class SoundBank(QObject):
    """扫描 sounds/ 目录，按 sounds.json 里的顺序分配槽位。

    磁盘是唯一事实来源：文件多了自动补到末尾，文件删了自动消失。
    顺序存在 sounds.json，所以用户可以随意拖动排序而不用改文件名。
    槽位上的条目有两种：普通音效是 Path，组合音效是 ComboEntry。
    """

    def __init__(self, slots: int, scfg=None) -> None:
        super().__init__()
        self.slots = max(1, int(slots))
        self.scfg = scfg
        self.items: list = []
        self.reload()

    def reload(self) -> None:
        try:
            SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            _log(f"[sound] 创建 sounds 目录失败: {exc}")
        found: list[tuple[str, Path]] = scan_sound_files()
        entries: list = []
        if self.scfg is not None:
            names = [key for key, _p in found]
            order = self.scfg.sync(names)   # 顺带清掉已删除文件留下的配置
            by_name = dict(found)
            for n in order:
                if n in by_name:
                    entries.append(by_name[n])
                else:
                    cdef = self.scfg.combo_of(n)
                    if cdef is not None:
                        entries.append(ComboEntry(cdef))
        else:
            entries = [p for _k, p in found]
        self.items = entries[: self.slots]

    def entry_at(self, idx: int):
        """槽位上的原始条目：Path（普通音效）或 ComboEntry（组合）。"""
        if 0 <= idx < len(self.items):
            return self.items[idx]
        return None

    def is_combo(self, idx: int) -> bool:
        return isinstance(self.entry_at(idx), ComboEntry)

    def name_at(self, idx: int) -> str:
        """显示用的名字：文件去扩展名，组合带 ◆ 前缀。配置里请用 full_at()。"""
        e = self.entry_at(idx)
        if e is None:
            return "空槽位"
        return e.stem

    def outer_index_map(self) -> list[int | None]:
        """外圈 12 个位置 -> 音效下标（None = 空格子）。

        位置表在 sounds.json 的 outer_slots 里，所以外圈可以留空、
        也可以随手把某一格拖到别处。没有配置时按顺序从第 0 格排起。
        """
        if self.scfg is not None:
            try:
                return self.scfg.outer_index_map()
            except Exception as exc:
                _log(f"[sound] 外圈摆位读取失败: {exc}")
        n = max(0, len(self.items) - INNER_MAX)
        return [INNER_MAX + p if p < n else None for p in range(OUTER_MAX)]

    def full_at(self, idx: int) -> str:
        """配置用的键：相对路径或组合键，和 sounds.json 的 order 一致。"""
        e = self.entry_at(idx)
        if e is None:
            return ""
        return sound_key(e) if isinstance(e, Path) else e.name

    def setting_at(self, idx: int):
        if self.scfg is None or not (0 <= idx < len(self.items)):
            return None
        return self.scfg.setting(self.full_at(idx))

    def index_of_name(self, name: str) -> int:
        """接受配置键 / 文件名 / 去扩展名的名字 / 组合键，都能找到槽位。"""
        for i, e in enumerate(self.items):
            if self.full_at(i) == name:
                return i
        for i, e in enumerate(self.items):
            if e.stem == name:
                return i
        return -1

    def path_at(self, idx: int) -> Path | None:
        """普通音效返回文件路径；组合条目返回 None（它有自己的一套播放）。"""
        if 0 <= idx < len(self.items):
            e = self.items[idx]
            return e if isinstance(e, Path) else None
        return None

    def __len__(self) -> int:
        return len(self.items)


# ---------------------------------------------------------------- 音频

# ---------------------------------------------------------------- 音频设备

# 名字里带这些词的，基本可以断定是"虚拟声卡"（装出来专门接音频回路的设备）。
# CABLE = VB-CABLE，Voicemeeter = VB 家的虚拟调音台，Soundpad 自带一个，剩下的兜底。
VIRTUAL_HINTS = (
    "cable", "vb-audio", "voicemeeter", "virtual audio", "soundpad", "虚拟",
)


def is_virtual_name(name: str) -> bool:
    low = (name or "").lower()
    return any(h in low for h in VIRTUAL_HINTS)


def find_output(name: str):
    if not name:
        return None
    for dev in QMediaDevices.audioOutputs():
        if dev.description() == name:
            return dev
    return None


def find_input(name: str):
    if not name:
        return None
    for dev in QMediaDevices.audioInputs():
        if dev.description() == name:
            return dev
    return None


def real_inputs() -> list:
    """所有"像真麦克风"的采集设备（把 CABLE Output 这类虚拟设备剔掉）。

    不剔除的话，用户很容易选中 CABLE Output 当麦克风——那是虚拟声卡的回放端，
    选它等于自己录自己，对方会听到完全静音。
    """
    return [d for d in QMediaDevices.audioInputs()
            if not is_virtual_name(d.description())]


def all_inputs() -> list:
    """不管真假的全部输入设备。

    只在 real_inputs() 一个都不剩时才拿出来用：这种人多半是只装了虚拟声卡、
    或者麦克风名字里正好带了关键字。与其让下拉框显示"没检测到麦克风"让人干瞪眼，
    不如把设备列出来、旁边写清楚为什么不能选。
    """
    return list(QMediaDevices.audioInputs())


def virtual_outputs() -> list:
    """所有长得像虚拟声卡的播放设备。"""
    return [d for d in QMediaDevices.audioOutputs()
            if is_virtual_name(d.description())]


def guess_virtual_output(prefer_name: str = ""):
    """挑一个能当虚拟声卡用的播放设备。没有就返回 None（说明还没装）。"""
    dev = find_output(prefer_name)
    if dev is not None and is_virtual_name(dev.description()):
        return dev
    cands = virtual_outputs()
    if not cands:
        return None
    # 双声道那条（CABLE Input）优先；16ch 那条留给专业调音台用
    cands.sort(key=lambda d: (
        "16ch" in d.description().lower(),
        "cable input" not in d.description().lower(),
    ))
    return cands[0]


def guess_capture_input(prefer_name: str = ""):
    """挑采集用的麦克风。

    顺序：用户上次选的 > 系统默认输入（但不能是虚拟设备）> 第一个真实麦克风。
    装了 VB-CABLE 之后系统默认输入会被改成 CABLE Output，所以第二步必须过滤，
    否则一上来就"录自己"，对方只会听到静音。
    """
    dev = find_input(prefer_name)
    if dev is not None and not is_virtual_name(dev.description()):
        return dev
    default = QMediaDevices.defaultAudioInput()
    if default is not None and default.description() and not is_virtual_name(
        default.description()
    ):
        return default
    cands = real_inputs()
    return cands[0] if cands else None


def _fmt(rate: int, ch: int, sf) -> QAudioFormat:
    f = QAudioFormat()
    f.setSampleRate(int(rate))
    f.setChannelCount(int(ch))
    f.setSampleFormat(sf)
    return f


def _same_fmt(a: QAudioFormat, b: QAudioFormat) -> bool:
    return (
        a.sampleRate() == b.sampleRate()
        and a.channelCount() == b.channelCount()
        and a.sampleFormat() == b.sampleFormat()
    )


def _fmt_label(fmt: QAudioFormat) -> str:
    """把格式写成一句人话，报错时用：48k立体声/浮点。"""
    sf = {
        QAudioFormat.Float: "浮点",
        QAudioFormat.Int16: "16位",
        QAudioFormat.Int32: "32位",
        QAudioFormat.UInt8: "8位",
    }.get(fmt.sampleFormat(), fmt.sampleFormat().name)
    return (
        f"{fmt.sampleRate() // 1000}k"
        f"{'立体声' if fmt.channelCount() == 2 else '单声道'}"
        f"/{sf}"
    )


def _target_format() -> QAudioFormat:
    """挑一个播放用的格式：解码时转一次，播放时就不用再转。

    这里**只用 Float**：混音器按"每帧每声道 4 字节"算缓冲和内存拷贝，
    换成整型会整条链路对不上。所以降级也只能在采样率和声道上退，
    退到底仍不支持就还是交 48k/立体声/浮点（和以前的兜底一致）。
    """
    dev = QMediaDevices.defaultAudioOutput()
    first = _fmt(48000, 2, QAudioFormat.Float)
    if dev.isFormatSupported(first):
        return first
    # 输出设备不认 48k 就走 44.1k，再不行就按它自己报的首选采样率来
    for rate in (44100, int(dev.preferredFormat().sampleRate())):
        if rate <= 0:
            continue
        cand = _fmt(rate, 2, QAudioFormat.Float)
        if dev.isFormatSupported(cand):
            return cand
    return first


# 采集格式：从"和播放一模一样"开始，一层层往下退。
# 顺序讲究——先保采样率（48k 跟播放同源，不用重采样），再保声道，
# 最后才退到整型。真实设备里最常见的就是"只能单声道"和"只有 16k"两种。
_CAPTURE_LADDER = (
    (48000, 2, QAudioFormat.Float),
    (48000, 2, QAudioFormat.Int16),
    (48000, 1, QAudioFormat.Float),
    (48000, 1, QAudioFormat.Int16),
    (44100, 2, QAudioFormat.Float),
    (44100, 2, QAudioFormat.Int16),
    (44100, 1, QAudioFormat.Float),
    (44100, 1, QAudioFormat.Int16),
    (32000, 1, QAudioFormat.Float),
    (16000, 1, QAudioFormat.Float),
    (16000, 1, QAudioFormat.Int16),
)


def capture_formats(dev) -> list:
    """这台设备能挨个试的**一串**格式，从好到差排好。

    和 capture_format 的区别：那个只给"第一选择"，这个给"整条退路"。

    为什么必须是一串：`isFormatSupported` 是**设备自己报的**，报得并不老实。
    有些虚拟声卡、蓝牙耳麦、共享模式下的设备会满口答应"48k 立体声没问题"，
    真去 start() 却直接拒绝。以前一台设备只试一两种就整台放弃，
    明明 16k 单声道能出声也用不上，用户看到的就是"麦克风打不开、注入不了"。
    """
    out: list = []
    if dev is None:
        return out

    def push(cand) -> None:
        if any(_same_fmt(cand, f) for f in out):
            return
        out.append(cand)

    for rate, ch, sf in _CAPTURE_LADDER:
        cand = _fmt(rate, ch, sf)
        try:
            if dev.isFormatSupported(cand):
                push(cand)
        except Exception:
            continue

    # 兜底：一条梯子都不认时，才拿设备自报的首选格式碰碰运气
    # （有些专业声卡只认自己那一个古怪组合）。
    # 不能无条件追加：老实的设备已经报准了格式，再塞一个它没答应过的纯属瞎试。
    if not out:
        try:
            pf = dev.preferredFormat()
            if pf.sampleRate() > 0 and pf.channelCount() > 0:
                out.append(_fmt(pf.sampleRate(), pf.channelCount(), pf.sampleFormat()))
        except Exception:
            pass
    return out


def capture_format(dev) -> QAudioFormat | None:
    """这台设备的第一选择（没有可用格式时返回 None）。"""
    fmts = capture_formats(dev)
    return fmts[0] if fmts else None


def capture_candidates(prefer_name: str = "") -> list:
    """采集设备候选队列：先说好要用的，再退到系统默认，最后一个个试。

    和 guess_capture_input 的区别：那个只给"一个答案"，
    这个给"一串退路"，第一个打不开就换下一个。
    """
    out: list = []
    seen: set[str] = set()

    def add(dev) -> None:
        if dev is None:
            return
        name = dev.description()
        if not name or name in seen:
            return
        # 虚拟设备当麦克风用等于自己录自己，对方只会听到静音
        if is_virtual_name(name):
            return
        seen.add(name)
        out.append(dev)

    add(find_input(prefer_name))
    add(QMediaDevices.defaultAudioInput())
    for dev in real_inputs():
        add(dev)
    return out


_DECODE_CACHE: dict[tuple, np.ndarray | None] = {}
_DECODE_CACHE_MAX = 48
_DECODE_BYTES = 0
_DECODE_BYTES_LIMIT = 192 * 1024 * 1024      # 缓存最多占这么多内存


def _file_stamp(path: Path) -> tuple:
    """文件指纹：路径 + 大小 + 修改时间。换过文件就不算同一份，缓存自然失效。"""
    try:
        st = path.stat()
        return (str(path), int(st.st_size), int(st.st_mtime))
    except OSError:
        return (str(path), -1, -1)


def decode_clip(path: Path, fmt: QAudioFormat, fade_ms: float) -> np.ndarray | None:
    """把音频文件解成 float32 波形 (帧数, 2)，并在首尾各加一段淡入淡出。

    淡入淡出是消除"咔哒"声的关键：不管原始文件的第一个采样是不是 0，
    进输出流时都从 0 平滑爬升、到尾部平滑落回 0，不会产生阶跃。

    解出来的波形会按文件指纹缓存：换轮盘时音效文件一个都没变，只是槽位
    顺序换了，没有这层缓存的话每换一次都要把全部音效重解一遍——实测 8 个
    音效要 100 多毫秒，松手那一下就明显顿住。
    """
    global _DECODE_BYTES

    stamp = _file_stamp(path)
    if stamp[1] < 0:                  # 文件不在，别白白走一遍解码器再等超时
        _log(f"[audio] 文件不存在 {path}")
        return None
    key = stamp + (
        fmt.sampleRate(), fmt.channelCount(), fmt.sampleFormat(),
        round(float(fade_ms), 3),
    )
    if key in _DECODE_CACHE:
        return _DECODE_CACHE[key]

    decoder = QAudioDecoder()
    decoder.setAudioFormat(fmt)
    chunks: list[np.ndarray] = []
    errors: list[str] = []

    def on_buffer() -> None:
        buf = decoder.read()
        if not buf.isValid():
            return
        data = np.frombuffer(bytes(buf.constData()), dtype="<f4")
        ch = buf.format().channelCount()
        if ch <= 0:
            return
        if ch == 2:
            arr = data.reshape(-1, 2)
        elif ch == 1:
            arr = np.repeat(data.reshape(-1, 1), 2, axis=1)
        else:
            arr = data.reshape(-1, ch)[:, :2]
        chunks.append(arr.astype(np.float32, copy=True))

    decoder.bufferReady.connect(on_buffer)
    decoder.error.connect(lambda *_: errors.append(decoder.errorString()))

    loop = QEventLoop()
    decoder.finished.connect(loop.quit)
    decoder.error.connect(loop.quit)
    guard = QTimer()
    guard.setSingleShot(True)
    guard.timeout.connect(loop.quit)
    guard.start(6000)

    decoder.setSource(QUrl.fromLocalFile(str(path)))
    decoder.start()
    loop.exec()
    guard.stop()
    decoder.stop()
    decoder.deleteLater()

    if not chunks:
        _log(f"[audio] 解码失败 {path.name} {errors}")
        return None

    clip = np.concatenate(chunks, axis=0)
    if clip.size == 0:
        return None

    # 直流偏移会把波形整体推离 0，播放时听感上偏"闷"，顺手扣掉
    clip -= clip.mean(axis=0, keepdims=True)

    rate = fmt.sampleRate()
    fade = max(16, int(rate * max(0.0, fade_ms) / 1000.0))
    fade = min(fade, len(clip) // 2)
    if fade > 0:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32).reshape(-1, 1)
        clip[:fade] *= ramp
        clip[-fade:] *= ramp[::-1]

    # 存进缓存前先算好占用，超了就按"先进先出"扔掉最老的一批
    size = int(clip.nbytes)
    while _DECODE_CACHE and (
        _DECODE_BYTES + size > _DECODE_BYTES_LIMIT or len(_DECODE_CACHE) >= _DECODE_CACHE_MAX
    ):
        _DECODE_BYTES -= int(_DECODE_CACHE.pop(next(iter(_DECODE_CACHE))).nbytes)
    _DECODE_CACHE[key] = clip
    _DECODE_BYTES += size
    return clip


def pitch_shift(clip: np.ndarray, semitones: float) -> np.ndarray:
    """用重采样改变音调。

    升调 = 播得更快（变短变尖），降调 = 播得更慢（变长变沉）。
    鬼畜音效要的正是这种"变速变调"的效果，所以不需要相位声码器那种
    保持时长的复杂算法——那个反而会把声音修得太平滑、不鬼畜了。
    """
    if abs(semitones) < 1e-3 or len(clip) == 0:
        return clip
    rate = 2.0 ** (semitones / 12.0)
    n_out = max(1, int(round(len(clip) / rate)))
    src = np.arange(len(clip), dtype=np.float64)
    dst = np.arange(n_out, dtype=np.float64) * rate
    out = np.empty((n_out, clip.shape[1]), dtype=np.float32)
    for ch in range(clip.shape[1]):
        out[:, ch] = np.interp(dst, src, clip[:, ch])
    return out


def combo_value(prev: float, step: float, limit: float, in_window: bool) -> float:
    """连击累计：窗口内再加一档，超时归零，最多累到 ±limit。

    变调（半音）和变速（百分比）都走这一个算法，只是单位不同。
    """
    if not in_window or step == 0.0:
        return 0.0
    return max(-limit, min(limit, prev + step))


# ---------------------------------------------------------------- 组合排程

_LIB_CACHE: dict[str, np.ndarray | None] = {}


def lib_clip(name: str, fmt: QAudioFormat, fade_ms: float = 6.0) -> np.ndarray | None:
    """按文件名解一段波形（带缓存）。

    组合里的成员可能不在轮盘上（只在组合里用），所以不能只靠 AudioEngine
    的 clips 列表，得能按名字直接取。
    """
    key = f"{name}|{fmt.sampleRate()}|{fmt.channelCount()}|{fade_ms}"
    if key in _LIB_CACHE:
        return _LIB_CACHE[key]
    path = sound_path(name)          # 键可以是 "整活/冰冰冰.wav" 这种带子目录的
    clip = decode_clip(path, fmt, fade_ms) if path.exists() else None
    if len(_LIB_CACHE) > 64:
        _LIB_CACHE.pop(next(iter(_LIB_CACHE)))
    _LIB_CACHE[key] = clip
    return clip


_DUR_CACHE: dict[tuple, float] = {}


def audio_duration(path: Path) -> float:
    """读音频文件的时长（秒）。读不出来返回 0。

    wav 直接读文件头（几毫秒）；mp3 / ogg / flac / m4a 用 Qt 的解码器
    只读流信息，不解码整段。结果按"路径 + 大小 + 修改时间"缓存，
    音效库每次刷新都不会重复读盘。
    """
    try:
        st = path.stat()
        key = (str(path), st.st_size, int(st.st_mtime))
    except OSError:
        return 0.0
    if key in _DUR_CACHE:
        return _DUR_CACHE[key]

    dur = 0.0
    if path.suffix.lower() == ".wav":
        try:
            import wave

            with wave.open(str(path)) as fh:
                frames, rate = fh.getnframes(), fh.getframerate()
                dur = frames / float(rate) if rate else 0.0
        except Exception:
            dur = 0.0
    if dur <= 0.0:
        player = QMediaPlayer()
        loop = QEventLoop()
        got: list[float] = []

        def on_dur(ms: int) -> None:
            if ms > 0:
                got.append(ms / 1000.0)
            loop.quit()

        def on_status(status) -> None:
            if status == QMediaPlayer.InvalidMedia:
                loop.quit()

        player.durationChanged.connect(on_dur)
        player.mediaStatusChanged.connect(on_status)
        guard = QTimer()
        guard.setSingleShot(True)
        guard.timeout.connect(loop.quit)
        guard.start(1500)          # 文件坏了别把界面卡死
        player.setSource(QUrl.fromLocalFile(str(path)))
        loop.exec()
        guard.stop()
        try:
            player.setSource(QUrl())
            player.deleteLater()
        except Exception:
            pass
        dur = got[0] if got else 0.0

    if len(_DUR_CACHE) > 400:
        _DUR_CACHE.clear()
    _DUR_CACHE[key] = dur
    return dur


def lib_duration(name: str) -> float:
    """某音效解码后的时长（秒）。找不到返回 0，编辑器拿它算总时长/检测缺失。"""
    clip = lib_clip(name, _target_format(), 6.0)
    if clip is None or len(clip) == 0:
        return 0.0
    return len(clip) / float(_target_format().sampleRate())


def trim_clip(clip: np.ndarray, start_ms: int, len_ms: int) -> np.ndarray | None:
    """按毫秒裁一段出来（片段裁剪）。

    起点/长度都按**原始速度**算，也就是"原音效的第 1.2 秒处"这种直觉说法，
    裁剪在变速/变调之前做，所以同一段素材换速度之后取到的还是同一段。
    两端各补 6ms 淡入淡出：剪切点是从波形中间下刀的，不补会"啪"一声。
    """
    if clip is None or len(clip) == 0:
        return None
    start_ms = max(0, int(start_ms))
    len_ms = max(0, int(len_ms))
    if start_ms == 0 and len_ms == 0:
        return clip                      # 没裁：原样返回，不复制、不花时间
    rate = float(_target_format().sampleRate())
    s = int(rate * start_ms / 1000.0)
    if s >= len(clip):
        return None                      # 起点已经在结尾之后：这项没内容可放
    e = len(clip) if len_ms <= 0 else min(len(clip), s + int(rate * len_ms / 1000.0))
    out = clip[s:e].copy()               # 必须复制：切片是视图，就地乘淡入会改到缓存的原波形
    n = len(out)
    if n <= 1:
        return None
    f = min(max(1, int(rate * 0.006)), n // 2)
    if f > 0:
        ramp = np.linspace(0.0, 1.0, f, dtype=np.float32).reshape(-1, 1)
        out[:f] *= ramp
        out[-f:] *= ramp[::-1]
    return out


def item_src_duration(it) -> float:
    """组合里某一项"裁剪之后、变速变调之前"的时长（秒）。0 = 文件缺失/裁没了。"""
    base = lib_duration(getattr(it, "sound", ""))
    if base <= 0.0:
        return 0.0
    start = max(0.0, int(getattr(it, "clip_start_ms", 0)) / 1000.0)
    if start >= base:
        return 0.0
    rest = base - start
    ln = max(0.0, int(getattr(it, "clip_len_ms", 0)) / 1000.0)
    return rest if ln <= 0 else min(rest, ln)


def combo_item_clip(it, fmt: QAudioFormat, fade_ms: float = 6.0,
                    rate_abs: float | None = None,
                    semi_abs: float | None = None) -> np.ndarray | None:
    """把组合的一项处理成可播的波形：裁剪 → 变速 → 变调。

    rate_abs / semi_abs 是**算完之后**的实际速度与变调（已经把组合整体参数
    和本次触发的随机值叠进去了）。传 None 就只用这一项自己的参数。
    分开传绝对值而不是传倍率，是为了让缓存键和实际生成的东西严格对应。
    """
    base = lib_clip(getattr(it, "sound", ""), fmt, fade_ms)
    if base is None:
        return None
    clip = trim_clip(base, getattr(it, "clip_start_ms", 0),
                     getattr(it, "clip_len_ms", 0))
    if clip is None:
        return None
    r = float(getattr(it, "rate", 1.0)) if rate_abs is None else float(rate_abs)
    if abs(r - 1.0) >= 0.01:
        clip = stretch_any(clip, r)
    s = float(getattr(it, "semitones", 0.0)) if semi_abs is None else float(semi_abs)
    if abs(s) >= 0.05:
        clip = pitch_shift(clip, s)
    return clip


def stretch_any(clip: np.ndarray, rate: float) -> np.ndarray:
    """变速到任意倍率：超出单次范围（0.5~2.0）就分几次做。

    time_stretch 内部会把倍率夹到 0.5~2.0（再快就只剩"啪"一声）。
    但"整体速度 × 逐项速度"很容易叠出 3 倍、4 倍，这里拆成两步做完，
    而不是让它在用户不知情的情况下被悄悄夹掉。
    """
    r = max(0.2, min(5.0, float(rate)))
    if abs(r - 1.0) < 0.01:
        return clip
    for _ in range(3):
        if r <= 2.0:
            break
        clip = time_stretch(clip, 2.0)
        r /= 2.0
    for _ in range(3):
        if r >= 0.5:
            break
        clip = time_stretch(clip, 0.5)
        r /= 0.5
    return time_stretch(clip, r)


def combo_plan(
    items: list, order: list[int], durs: dict[int, float], rate: int
) -> list[tuple[int, int]]:
    """算这一次播放的实际排程：[(成员下标, 起始延迟帧), ...]。

    规则（每一项只看它自己的触发条件）：
      组合开始时      start = 该组合开始的时间 + 延迟
      上一项开始后    start = 上一项的开始时间 + 延迟
      上一项结束后    start = 上一项的开始时间 + 上一项的时长 + 延迟

    延迟可以是负数（v0.7.2）：等于"提前起"，用来让后一项叠到前一项的尾巴上，
    做交叠淡出那种顺滑衔接。但无论怎么提前，都不能早于组合触发那一刻，
    所以算出来的起点统一夹到 >= 0。

    第一声永远紧贴触发时刻：随机模式下抽到的第一项往往不是组合里的第 1 项，
    它身上那个"上一项开始后 1000ms"的延迟不该让组合先干等一秒。
    确实想让第一声晚点响，就把那一项的条件设成"组合开始时"再填延迟。

    纯函数：给定成员、顺序、时长就是确定结果。不依赖定时器、不依赖
    "实际播到哪了"，所以不会越按越飘、也不会因为界面卡一下就走样。
    缺失成员（时长 0）不打断接龙，后面照常排。
    """
    plan: list[tuple[int, int]] = []
    if not order or rate <= 0:
        return plan
    t_combo = 0
    prev_start = 0
    prev_dur = 0.0
    for k, idx in enumerate(order):
        if not (0 <= idx < len(items)):
            continue
        it = items[idx]
        delay_ms = int(getattr(it, "delay_ms", 0))
        delay = int(rate * delay_ms / 1000.0)      # 负数 = 提前，别在这里夹
        trig = str(getattr(it, "trig", TRIG_PREV_END))
        if k == 0:
            start = t_combo + delay if trig == TRIG_COMBO else t_combo
        elif trig == TRIG_COMBO:
            start = t_combo + delay
        elif trig == TRIG_PREV_START:
            start = prev_start + delay
        else:                       # TRIG_PREV_END 及任何异常值都按"结束后"
            start = prev_start + int(prev_dur * rate) + delay
        start = max(0, start)       # 再早也不能早到触发之前
        plan.append((idx, start))
        prev_start = start
        prev_dur = float(durs.get(idx, 0.0))
    return plan


def _xcorr(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """互相关（a 长、b 短），只返回能完整对齐的那一段。

    用 FFT 算而不是 np.correlate：后者是逐个位置点乘，1024 长的帧跑几千帧
    要几百毫秒，按键就有明显延迟了。FFT 是 O(n log n)，快一个数量级。
    """
    n = len(a) + len(b) - 1
    nfft = 1 << (n - 1).bit_length()
    fa = np.fft.rfft(a, nfft)
    fb = np.fft.rfft(b[::-1], nfft)
    full = np.fft.irfft(fa * fb, nfft)[:n]
    # 只取"b 完整落在 a 里面"的那段：长度 len(a) - len(b) + 1
    return full[len(b) - 1:len(a)]


def _sliding_energy(x: np.ndarray, frame: int) -> np.ndarray:
    """每 frame 个点的平方和（滑动窗口），用来把互相关归一化。"""
    c = np.concatenate(([0.0], np.cumsum(x.astype(np.float64) ** 2)))
    return c[frame:] - c[:-frame]


def time_stretch(clip: np.ndarray, rate: float, frame: int = 1024) -> np.ndarray:
    """改变播放速度但**保持音调**（WSOLA：波形相似叠加）。

    rate > 1 更快（输出更短），rate < 1 更慢（输出更长），音高不变。

    做法：把原波形切成 50% 重叠的短帧，按 rate 决定每帧往前跳多远；
    取每一帧之前先在附近找一个"和上一帧接得最顺"的位置（波形最相似处），
    这样拼接点不会有相位断裂的"咔哒"声。

    为什么不复用 pitch_shift：那个是重采样，快慢和音调绑在一起（磁带快进），
    而这里要的是"把话说过一遍"——嗓子还是那个嗓子，只是语速变了。
    """
    n_in = len(clip)
    if n_in < frame * 4 or abs(rate - 1.0) < 1e-3:
        return clip
    rate = max(0.5, min(2.0, float(rate)))
    ch = clip.shape[1]
    hop_s = frame // 2                      # 合成帧间隔（固定）
    hop_a = max(1, int(round(hop_s * rate)))  # 分析帧间隔（按速度放大/缩小）
    n_out = max(frame, int(round(n_in / rate)))
    win = np.hanning(frame).astype(np.float32)
    out = np.zeros((n_out + frame, ch), dtype=np.float32)
    acc = np.zeros(n_out + frame, dtype=np.float32)
    mono = clip.mean(axis=1).astype(np.float32) if ch > 1 else clip[:, 0].copy()
    tol = max(1, frame // 8)                # 找相似位置的搜索半径

    prev_pos: int | None = None
    out_pos = 0
    while out_pos < n_out:
        k = out_pos // hop_s
        nominal = max(0, min(n_in - frame, int(round(k * hop_a))))
        pos = nominal
        if prev_pos is not None:
            lo = max(0, nominal - tol)
            hi = min(n_in - frame, nominal + tol)
            if hi > lo:
                tgt = mono[prev_pos + hop_s: prev_pos + hop_s + frame]
                if len(tgt) == frame and float(np.abs(tgt).sum()) > 1e-6:
                    reg = mono[lo:hi + frame]
                    cc = _xcorr(reg, tgt)
                    energy = _sliding_energy(reg, frame)
                    cc = cc / np.sqrt(np.maximum(energy, 1e-8))
                    pos = lo + int(np.argmax(cc[:hi - lo + 1]))
        pos = max(0, min(n_in - frame, pos))
        out[out_pos:out_pos + frame] += clip[pos:pos + frame] * win[:, None]
        acc[out_pos:out_pos + frame] += win
        prev_pos = pos
        out_pos += hop_s

    out = out[:n_out]
    # 50% 重叠的汉宁窗在中间叠加正好是 1；首尾不足，按实际叠加重建，别让音量跳
    out /= np.maximum(acc[:n_out], 0.5)[:, None]
    return np.clip(out, -1.0, 1.0)


class MicCapture:
    """麦克风数据的缓冲池：QAudioSource 采到的数据先存这儿，等虚拟声卡那一路来取。

    为什么要先缓冲再取：采集和播放是两套时钟（麦克风一个晶振、声卡一个晶振），
    天然有个千分之几的偏差。采一点就立刻写一点的话，一会儿缺数据一会儿积压，
    听感就是持续的"咔哒"。这里留一小段余量（默认 60ms），水位高了就丢几帧、
    低了就补零，偏差被慢慢吃掉，听不出接缝。

    这里刻意**不继承 QIODevice**：QAudioSource 的回调式接口（writeData）
    在 PySide6 里会把二进制数据当字符串传进来，容易把音频数据弄坏。
    改成主动读（start() 拿一个可读设备，用计时器泵）就不碰这个坑。
    """

    def __init__(self, fmt: QAudioFormat, src_fmt: QAudioFormat | None = None) -> None:
        """fmt = 播放（混音器）那边的格式，也就是这里最终要交出去的样子。

        src_fmt = 麦克风实际被打开的格式。不传就等于两边一致（老行为）。
        传了不一样的，push 时会把整型转浮点、单声道补成双声道、
        采样率不一样就重采样——这样 16kHz 的蓝牙耳麦也能接进来。
        """
        self.channels = max(1, fmt.channelCount())
        self.rate = fmt.sampleRate()
        src = src_fmt if src_fmt is not None else fmt
        self.src_channels = max(1, src.channelCount())
        self.src_rate = src.sampleRate() or self.rate
        self.src_sample_format = src.sampleFormat()
        self._buf = np.zeros((0, self.channels), dtype=np.float32)
        self._primed = False     # 攒够一次余量之前不放行，避免一开机就狂补零
        self._peak = 0.0
        self._level = 0.0
        self.underruns = 0
        self.dropped = 0
        self.consumed = 0        # 累计被取走的帧数，用来判断"链路是不是真的在跑"
        self.pushed = 0          # 累计采到的帧数
        # 采集格式和播放格式不一样时用到的中间状态
        self._raw_tail = b""     # 上次剩下不满一帧的字节，留到下次一起解
        self._rs_pos = 0.0       # 重采样：下一帧要取的位置（相对 _rs_buf）
        self._rs_buf: np.ndarray | None = None

    # ---- 格式适配 ----
    def _decode(self, raw: bytes) -> np.ndarray | None:
        """原始字节 -> (帧数, 采集声道) 的 float32。"""
        ch = self.src_channels
        sf = self.src_sample_format
        item = 4 if sf == QAudioFormat.Float else 2 if sf == QAudioFormat.Int16 else 4
        # Qt 偶尔会给出"差几个字节不满一帧"的块，直接扔了会每次咔一下，
        # 所以把尾巴留到下一次，凑齐再解
        if self._raw_tail:
            raw = self._raw_tail + raw
            self._raw_tail = b""
        usable = (len(raw) // (item * ch)) * item * ch
        if usable <= 0:
            self._raw_tail = raw[-item * ch * 2:] if len(raw) > item * ch * 2 else raw
            return None
        if usable < len(raw):
            self._raw_tail = raw[usable:]
        body = raw[:usable]

        if sf == QAudioFormat.Float:
            arr = np.frombuffer(body, dtype="<f4").astype(np.float32, copy=False)
        elif sf == QAudioFormat.Int16:
            arr = np.frombuffer(body, dtype="<i2").astype(np.float32) / 32768.0
        elif sf == QAudioFormat.Int32:
            arr = np.frombuffer(body, dtype="<i4").astype(np.float32) / 2147483648.0
        elif sf == QAudioFormat.UInt8:
            arr = (np.frombuffer(body, dtype="u1").astype(np.float32) - 128.0) / 128.0
        else:
            # 不认识的类型：先按浮点试，坏了也不至于崩
            arr = np.frombuffer(body, dtype="<f4").astype(np.float32, copy=False)
        if arr.size % ch:
            arr = arr[: arr.size // ch * ch]
        if arr.size == 0:
            return None
        return arr.reshape(-1, ch)

    def _map_channels(self, arr: np.ndarray) -> np.ndarray:
        """采集声道数 -> 播放声道数。单声道补双声道，多声道取前两路。"""
        if arr.shape[1] == self.channels:
            return arr
        if arr.shape[1] == 1 and self.channels == 2:
            return np.repeat(arr, 2, axis=1)
        if arr.shape[1] > self.channels:
            return arr[:, : self.channels]
        # 声道数比不上（比如 2 声道要 4 路）：用现有声道循环补
        reps = int(np.ceil(self.channels / arr.shape[1]))
        return np.tile(arr, (1, reps))[:, : self.channels]

    def _resample(self, arr: np.ndarray) -> np.ndarray:
        """采样率不同才走这里：线性插值，语音足够。

        必须跨块连续：留最后一段缓冲当下一块的起点，否则每 8ms 接一次接缝，
        听感是持续的低频"噗噗"声。
        """
        if self.src_rate == self.rate or len(arr) == 0:
            return arr
        step = float(self.src_rate) / float(self.rate)
        buf = arr if self._rs_buf is None or len(self._rs_buf) == 0 else np.concatenate(
            [self._rs_buf, arr]
        )
        if len(buf) < 2:
            self._rs_buf = buf
            return np.zeros((0, buf.shape[1]), dtype=np.float32)
        if self._rs_pos > len(buf) - 2:
            self._rs_buf = buf
            return np.zeros((0, buf.shape[1]), dtype=np.float32)
        n_out = int(np.floor((len(buf) - 2 - self._rs_pos) / step)) + 1
        if n_out <= 0:
            self._rs_buf = buf
            return np.zeros((0, buf.shape[1]), dtype=np.float32)
        idx = self._rs_pos + step * np.arange(n_out, dtype=np.float64)
        i0 = np.floor(idx).astype(np.int64)
        frac = (idx - i0).astype(np.float32)[:, None]
        out = buf[i0] * (1.0 - frac) + buf[i0 + 1] * frac
        nxt = float(idx[-1]) + step
        consumed = int(np.floor(nxt))
        self._rs_buf = buf[consumed:]
        self._rs_pos = nxt - consumed
        return out.astype(np.float32, copy=False)

    def push(self, raw: bytes) -> int:
        """喂进原始 PCM 字节，内部会按需要转格式、转声道、转采样率。"""
        if not raw:
            return 0
        arr = self._decode(raw)
        if arr is None or len(arr) == 0:
            return 0
        arr = self._map_channels(arr)
        arr = self._resample(arr)
        if len(arr) == 0:
            return 0
        self._buf = arr if len(self._buf) == 0 else np.concatenate([self._buf, arr])
        # 上限保护：没人来取（比如虚拟声卡选错了）时别把内存吃光
        cap = self.rate * 2
        if len(self._buf) > cap:
            self._buf = self._buf[-cap:]
        peak = float(np.abs(arr).max())
        if peak > self._peak:
            self._peak = peak
        self.pushed += len(arr)
        return len(arr)

    def pull(self, frames: int, target: int) -> np.ndarray:
        """取 frames 帧出来混音。target = 稳态想保留的余量（帧）。"""
        avail = len(self._buf)
        if not self._primed:
            if avail < frames + target:
                self.underruns += 1
                return np.zeros((frames, self.channels), dtype=np.float32)
            self._primed = True
        if avail < frames:
            # 采集断档（设备被抢/驱动卡了一下）：补零顶上，等下把余量重新攒起来
            self.underruns += 1
            if avail == 0:
                self._primed = False
            out = np.zeros((frames, self.channels), dtype=np.float32)
            out[:avail] = self._buf
            self._buf = self._buf[:0]
            return out
        excess = avail - frames
        if excess > target:
            drop = excess - target
            self._buf = self._buf[drop:]
            self.dropped += drop
        out = np.array(self._buf[:frames], dtype=np.float32, copy=True)
        self._buf = self._buf[frames:]
        self.consumed += frames
        return out

    def peak(self, decay: float = 0.86) -> float:
        """最近一瞬间的电平（0~1），给"说话测试"的电平条用。"""
        self._level = max(self._peak, self._level * decay)
        self._peak = 0.0
        return self._level

    def reset(self) -> None:
        self._buf = self._buf[:0]
        self._primed = False
        self._peak = 0.0
        self._level = 0.0
        # 重采样状态一起清：留着上一轮的尾巴会从中间接错位置
        self._raw_tail = b""
        self._rs_pos = 0.0
        self._rs_buf = None


class Mixer(QIODevice):
    """拉模式音频源：QAudioSink 缺数据时来这儿要，我们现混一遍给它。

    一个 Mixer 对应一个输出设备。没声音的时候输出全 0，流不断，
    也就没有"每次播放都重建会话"的爆音。

    开了麦克风注入之后会有两个实例，各自接一个出口：
    - 耳机那一路：只有音效（不加麦克风，否则自己听到自己，戴耳机也会觉得怪）
    - 虚拟声卡那一路：音效 + 麦克风原声（对方听到的就是这个）
    两个实例各记各的播放进度，不共用游标——共用会互相抢数据，变成咔咔声。
    """

    def __init__(self, fmt: QAudioFormat) -> None:
        super().__init__()
        self.channels = max(1, fmt.channelCount())
        self.rate = fmt.sampleRate()
        self.clips: list[np.ndarray] = []
        self.voices: list[list] = []  # [clip_index, 播放位置]
        self.volume = 0.8
        self.rendered_frames = 0
        # 挂在虚拟声卡那一路上时，把麦克风原声混进来（耳机那一路是 None）
        self.mic: MicCapture | None = None
        self.mic_gain = 1.0
        self.mic_target = int(self.rate * 0.06)

    # Qt 需要这个声明是顺序流
    def isSequential(self) -> bool:  # noqa: N802
        return True

    def bytesAvailable(self) -> int:  # noqa: N802
        return (1 << 20) + super().bytesAvailable()

    def trigger(self, clip: np.ndarray, gain: float = 1.0, delay: int = 0,
                group: str | None = None, max_voices: int = 0) -> bool:
        """播放一段波形。直接收 clip 而不是索引，因为变调后的波形是临时算的。

        delay 是"再过多少帧才开始响"，组合音效靠它做排程：
        排程在触发瞬间一次算完，交给混音器按帧数顺延，不用任何定时器
        （定时器会被 GUI 卡顿带偏，这是 v0.7 卡死的根源之一）。

        group / max_voices 是"同一条组合最多几条声音同时在响"：
        超了就把这条组合最早的那条掐掉（正在响的走 12ms 淡出，
        还没开口的直接摘掉）。不同组合各算各的，互不影响。
        """
        if clip is None or len(clip) == 0:
            return False
        if group and max_voices > 0:
            self._retire_oldest(group, max_voices)
        # 同一音效连按两次时叠加播放，不做打断，免得出现截断的尾巴
        # [波形, 播放位置, 音量, 淡出剩余帧, 延迟剩余帧, 分组]
        self.voices.append([clip, 0, float(gain), 0, max(0, int(delay)), group])
        return True

    def _retire_oldest(self, group: str, max_voices: int) -> None:
        """这条分组里的声音超过上限时，把最老的几条让出去。

        遍历用下标而不是 list.remove：列表里装着 numpy 数组，
        remove 会走 == 比较，两个不同长度的波形一比较就抛异常
        （v0.7 闪退的元凶）。正在淡出的不再计数，免得同一秒内反复挑中它。
        """
        while True:
            live = [
                k for k, v in enumerate(self.voices)
                if len(v) > 5 and v[5] == group and v[3] <= 0
            ]
            if len(live) < max_voices:
                return
            k = live[0]                       # 最早触发的那条
            voice = self.voices[k]
            if len(voice) > 4 and voice[4] > 0:
                del self.voices[k]            # 还没响：直接摘掉，不用淡出
                continue
            voice[3] = max(1, int(self.rate * 0.012))   # 正在响：12ms 淡出

    def stop_all(self, fade_ms: float = 12.0) -> None:
        """停止所有正在播放的声音。

        直接清空列表等于从波形中间"咔嚓"切断，扬声器会蹦出一声爆音
        （听起来像软件崩了）。这里给每路挂一个十几毫秒的淡出倒计时：
        人耳分辨不出这点延迟，但不会有杂音。

        还没开口的延迟语音（组合里排在后头的项）直接摘掉，
        否则用户按了"停止"，一秒钟后还会有声音冒出来。
        """
        if fade_ms <= 0:
            self.voices.clear()
            return
        fade = max(1, int(self.rate * fade_ms / 1000.0))
        kept: list[list] = []
        for voice in self.voices:
            if len(voice) > 4 and voice[4] > 0:
                continue          # 还没开始响：直接不留
            voice[3] = fade
            kept.append(voice)
        self.voices = kept

    @property
    def playing(self) -> bool:
        return bool(self.voices)

    def readData(self, maxlen: int):  # noqa: N802
        bpf = self.channels * 4  # float32
        frames = int(maxlen) // bpf
        if frames <= 0:
            return b""

        out = np.zeros((frames, self.channels), dtype=np.float32)
        if self.voices:
            alive: list[list] = []
            for voice in self.voices:
                clip = voice[0]
                pos = voice[1]
                gain = voice[2]
                fade = voice[3]
                delay = voice[4] if len(voice) > 4 else 0
                off = 0
                if delay > 0:
                    # 还没到该响的时刻：这一块先静音走过去
                    if delay >= frames:
                        voice[4] = delay - frames
                        alive.append(voice)
                        continue
                    off = int(delay)
                    voice[4] = 0
                n = min(frames - off, len(clip) - pos)
                if fade > 0:
                    n = min(n, fade)            # 淡出只需再走这么多帧
                if n <= 0:
                    continue                    # 播完/淡完：不进 alive 就等于丢了
                seg = clip[pos:pos + n]
                if gain != 1.0:
                    seg = seg * gain
                if fade > 0:
                    # (fade-1)/fade … 0/fade：收到 0 时正好静音，不会留在半途
                    ramp = (fade - np.arange(n, dtype=np.float32)) / float(fade)
                    seg = seg * ramp[:, None]
                    voice[3] = fade - n
                out[off:off + n] += seg
                voice[1] = pos + n
                if voice[1] < len(clip) and not (fade > 0 and voice[3] <= 0):
                    alive.append(voice)
            # 用"重建列表"代替 list.remove(voice)：后者走 == 比较，
            # 两个不同长度的波形一比较就 numpy 广播报错（v0.7 闪退的元凶）
            self.voices = alive

            # 两路叠加可能超过 1.0，先按平方律调音量（更贴合听觉），再硬限幅兜底
            gain = self.volume * self.volume
            if gain != 1.0:
                out *= gain

        # 麦克风原声只在虚拟声卡那一路混（mic 为 None 时这里直接跳过）。
        # 放在音效音量之后再叠加，这样调"音效音量"不会连自己的说话声一起变。
        if self.mic is not None:
            mic = self.mic.pull(frames, self.mic_target)
            if self.mic_gain != 1.0:
                mic = mic * self.mic_gain
            out += mic

        np.clip(out, -1.0, 1.0, out=out)   # 叠加后可能爆表，硬限幅兜底

        self.rendered_frames += frames
        return out.tobytes()

    def writeData(self, data) -> int:  # noqa: N802
        return 0


class AudioEngine(QObject):
    """音效播放 + 麦克风注入。

    出口最多两个：
    - 耳机（默认输出）：只放音效，自己听得见
    - 虚拟声卡（CABLE Input）：音效 + 你的麦克风原声，游戏语音从这里取

    两个出口各有一个 Mixer，各走各的播放进度。共用一个混音器会让两次"取数据"
    互相抢游标，听起来就是持续的咔咔声——这是双路输出的第一道坑。
    """

    # 这些键一变就得整条链路重建（换设备、开关麦克风）
    _STRUCT_KEYS = ("mic_enabled", "mic_device", "cable_device", "monitor_enabled")

    # 链路出问题时发一句人话，主程序接过去弹托盘气泡（关着设置窗口也能看见）
    problem = Signal(str)

    def __init__(self, bank: SoundBank, cfg: dict) -> None:
        super().__init__()
        self.bank = bank
        self.cfg = cfg
        self.fmt = _target_format()
        # ---- 耳机那一路（没开麦克风时这是唯一的一路）----
        self.mixer = Mixer(self.fmt)
        self.mixer.volume = float(cfg["volume"])
        self.mixer.open(QIODevice.ReadOnly)
        self._sink: QAudioSink | None = None
        self._device_name = ""
        # ---- 虚拟声卡那一路 ----
        self.cable: Mixer | None = None
        self._cable_sink: QAudioSink | None = None
        self._cable_name = ""
        # ---- 麦克风采集 ----
        self.capture: MicCapture | None = None
        self._source: QAudioSource | None = None
        self._src_io = None                # 拉模式下 Qt 给的可读设备
        self._pump_timer = None            # 定时把采集数据搬进缓冲池
        self._mic_name = ""
        self.mic_error = ""
        self.mic_note = ""                 # 降级适配的说明（不是错误）
        self.cable_error = ""              # 虚拟声卡那一路开不起来的原因
        self._mic_try_at = 0.0             # 上次尝试开采集的时刻，失败重试要限频
        self._mic_err_logged = ""          # 采集中途断开只记一次日志
        self._last_problem = ""            # 上次通知过用户的故障，避免反复弹窗
        self._struct_sig: tuple | None = None
        self.clips: list[np.ndarray] = []
        # 连击变调用：某个槽位上次播放的时间、当前累计半音偏移
        self._last_at: dict[int, float] = {}
        self._pitch_now: dict[int, float] = {}
        # 连击变速用：当前累计的快慢偏移（0.1 = 快 10%，-0.2 = 慢 20%）
        self._speed_now: dict[int, float] = {}
        # 拉伸结果缓存：(槽位, 速度) -> 波形。同一档速度反复按不必重算
        self._stretch_cache: dict[tuple[int, float], np.ndarray] = {}
        # 随机变调用：某个槽位上一次抽到的半音偏移，用来避免连着两次一样
        self._rnd_pitch: dict[int, float] = {}
        # 组合成员的成品波形缓存：成员下标 -> 已变调/变速的波形
        self._combo_cache: dict[tuple, np.ndarray | None] = {}
        # 组合冷却：cid -> 上次真的播出去的时间（monotonic 秒）
        self._combo_last: dict[str, float] = {}
        # 组合游标：cid -> 下一次该从第几项起（只有"按顺序点击 / 累加"模式用）
        self._combo_step: dict[str, int] = {}
        # 预渲染排队：启动后一条一条烘焙，不卡界面
        self._warm_queue: list = []
        self._warm_timer: QTimer | None = None
        self.last_idx: int | None = None   # 供"重复上一个"使用
        self._cycle = -1                   # 供"顺序播放"使用
        self.load()

    # ---- 解码 ----
    def load(self, stop_playing: bool = True) -> None:
        """重新解码全部槽位。

        stop_playing=False 是给"换轮盘"用的：正在响的每一路自己抱着波形数组，
        换掉 clips 列表碰不到它们，所以可以不断音地换盘。
        """
        self.clips = []
        fade_ms = float(self.cfg.get("fade_ms", 6))
        n_real = 0
        for idx in range(len(self.bank)):
            path = self.bank.path_at(idx)
            if path is None:
                # 组合条目（或已删掉的文件）占一个 None，保持下标和槽位对齐
                self.clips.append(None)
                continue
            clip = decode_clip(path, self.fmt, fade_ms)
            self.clips.append(clip)
            if clip is not None:
                n_real += 1
        for mix in self._mixers_all():
            mix.clips = self.clips
            if stop_playing:
                mix.stop_all()
        self._stretch_cache.clear()     # 波形换了，旧的拉伸结果不能再用
        self._combo_cache.clear()
        _LIB_CACHE.clear()
        n_combo = len(self.bank) - n_real
        _log(f"[audio] 已装载 {n_real} 个音效"
             + (f" + {n_combo} 个组合" if n_combo else "")
             + f"（{self.fmt.sampleRate()}Hz/{self.fmt.channelCount()}ch）")

    # ---------------------------------------------------------------- 链路搭建
    def _mixers_all(self) -> list[Mixer]:
        out = [self.mixer]
        if self.cable is not None:
            out.append(self.cable)
        return out

    def _active_mixers(self) -> list[Mixer]:
        """真正接了输出设备、在跑的混音器。没接的触发声音只会积压。"""
        out = []
        if self._sink is not None:
            out.append(self.mixer)
        if self.cable is not None and self._cable_sink is not None:
            out.append(self.cable)
        return out

    def _buffer_bytes(self, ms: float) -> int:
        return int(self.fmt.sampleRate() * ms / 1000.0) * self.fmt.channelCount() * 4

    def _start_monitor_sink(self) -> None:
        dev = QMediaDevices.defaultAudioOutput()
        sink = QAudioSink(dev, self.fmt)
        sink.setBufferSize(self._buffer_bytes(float(self.cfg.get("audio_buffer_ms", 60))))
        sink.start(self.mixer)
        self._sink = sink
        self._device_name = dev.description()
        _log(f"[audio] 耳机输出={dev.description()} 缓冲={sink.bufferSize()}B "
             f"状态={sink.state().name}")

    def _start_cable_sink(self) -> None:
        dev = guess_virtual_output(str(self.cfg.get("cable_device") or ""))
        if dev is None:
            _log("[cable] 没找到虚拟声卡（需要 VB-CABLE / VoiceMeeter 这类设备）")
            self.cable_error = "没找到虚拟声卡"
            return
        mix = Mixer(self.fmt)
        mix.volume = float(self.cfg.get("cable_effect_gain", 1.0))
        mix.mic = self.capture          # 采集没起来就是 None，那一路只剩音效
        mix.mic_gain = float(self.cfg.get("mic_gain", 0.9))
        mix.mic_target = max(
            0, int(self.fmt.sampleRate() * float(self.cfg.get("mic_latency_ms", 60)) / 1000.0)
        )
        mix.clips = self.clips
        mix.open(QIODevice.ReadOnly)
        sink = QAudioSink(dev, self.fmt)
        sink.setBufferSize(self._buffer_bytes(float(self.cfg.get("audio_buffer_ms", 60))))
        sink.start(mix)
        state = sink.state().name
        if state != "ActiveState":
            # 开了但没跑起来：以前这里只写日志，用户在游戏里一句都收不到还以为是软件的问题
            self.cable_error = f"虚拟声卡「{dev.description()}」没启动（{state}）"
            _log("[cable] " + self.cable_error)
        self.cable = mix
        self._cable_sink = sink
        self._cable_name = dev.description()
        _log(f"[cable] 虚拟声卡={dev.description()} 麦克风={'有' if mix.mic else '无'} "
             f"余量={mix.mic_target / self.fmt.sampleRate() * 1000:.0f}ms "
             f"状态={state}")

    def _probe_capture(self, dev, fmt: QAudioFormat):
        """按给定格式开一路采集。成功返回 (cap, src, io)，失败返回 (None, 原因)。"""
        try:
            cap = MicCapture(self.fmt, src_fmt=fmt)
            src = QAudioSource(dev, fmt)
            src.setBufferSize(self._buffer_bytes(40))
            io = src.start()      # 拉模式：Qt 返回一个可读设备，我们自己去读
        except Exception as exc:
            return None, f"打不开（{exc}）"
        # 注意别用 err != QAudio.NoError 判断：PySide6 里同名的枚举实例
        # 直接比会判定为不等（踩过一次，导致麦克风明明正常却被判失败）。
        err_name = src.error().name
        if io is None or err_name != "NoError":
            try:
                src.stop()
            except Exception:
                pass
            src.deleteLater()
            return None, "被占用" if err_name == "NoError" else f"打不开（{err_name}）"
        return (cap, src, io), ""

    def _start_capture(self) -> None:
        """开采集。一处不行就换格式、换设备，直到有一路能起来。

        以前的写法是"挑一个设备、只认 48kHz 立体声浮点"，不满足就报错收手：
        蓝牙耳麦（16kHz 单声道）、部分 USB 麦克风（只给 44.1kHz）全部被判死，
        而且虚拟声卡那一路照跑，结果队友听你像哑巴。现在改成一层层往下退。

        注意**退到底**：一台设备要把整条格式梯子试穿再算放弃。
        设备自己报"支持"并不作数（虚拟声卡/蓝牙/共享模式都会谎报），
        真开不起来时还得往下试 44.1k、单声道、16k。
        """
        self._mic_try_at = time.monotonic()
        cands = capture_candidates(str(self.cfg.get("mic_device") or ""))[:4]
        if not cands:
            self.mic_error = "找不到可用的麦克风"
            self.mic_note = ""
            _log("[mic] " + self.mic_error)
            return

        fails: list[str] = []
        t0 = time.monotonic()
        for dev in cands:
            name = dev.description()
            fmts = capture_formats(dev)
            if not fmts:
                fails.append(f"{name}（没有可用格式）")
                continue
            first_why = ""
            n_try = 0
            for fmt in fmts:
                n_try += 1
                got, why = self._probe_capture(dev, fmt)
                if got is not None:
                    self._install_capture(dev, fmt, *got)
                    if fails:
                        _log(f"[mic] {name} 试了 {n_try} 种格式才对上："
                             f"{fmt.sampleRate()}Hz/{fmt.channelCount()}ch")
                    return
                if not first_why:
                    first_why = f"{_fmt_label(fmt)} {why}"
                # 全都打不开的设备会白试十几次，给个总时长上限，
                # 别让"修麦克风"把启动拖成几秒钟
                if time.monotonic() - t0 > 1.5:
                    break
            fails.append(f"{name}（试了 {n_try} 种格式，{first_why}）")
            if time.monotonic() - t0 > 1.5:
                break

        # 全都试过了还是不行：把前面两条原因带上，别只说"打不开"
        self.mic_error = "麦克风打不开：" + "；".join(fails[:2])
        self.mic_note = ""
        _log("[mic] " + self.mic_error + (f"（共试了 {len(fails)} 台设备）" if fails else ""))

    def _install_capture(self, dev, fmt: QAudioFormat, cap: MicCapture, src, io) -> None:
        """把开好的采集接上定时泵。"""
        self.capture = cap
        self._source = src
        self._src_io = io
        self._mic_name = dev.description()
        self.mic_error = ""
        # 降级说明：能用但不是原生格式时，在设置页写一句，别让人以为是坏了
        if fmt.sampleRate() != self.fmt.sampleRate() or fmt.channelCount() != self.fmt.channelCount():
            self.mic_note = (
                f"已自动适配到 {fmt.sampleRate() // 1000}kHz "
                f"{'立体声' if fmt.channelCount() == 2 else '单声道'}"
            )
        elif fmt.sampleFormat() != QAudioFormat.Float:
            self.mic_note = "已自动适配为整型采样"
        else:
            self.mic_note = ""
        # 8ms 泵一次：比一次读一大坨更平滑，也不会把设备缓冲堆满
        self._pump_timer = QTimer(self)
        self._pump_timer.setInterval(8)
        self._pump_timer.timeout.connect(self._pump_capture)
        self._pump_timer.start()
        _log(f"[mic] 采集={dev.description()} "
             f"格式={fmt.sampleRate()}Hz/{fmt.channelCount()}ch/{fmt.sampleFormat().name} "
             f"缓冲={src.bufferSize()}B 状态={src.state().name}"
             + (f"（{self.mic_note}）" if self.mic_note else ""))

    def _pump_capture(self) -> None:
        """把采集设备里攒下的数据搬进缓冲池。"""
        io = getattr(self, "_src_io", None)
        if io is None or self.capture is None:
            return
        # 设备被拔掉 / 被别的软件抢走时，readAll() 只会一直返回空，
        # 界面上却还写着"采集：xxx"，用户以为一切正常。这里主动看一眼错误状态。
        src = self._source
        if src is not None:
            try:
                err_name = src.error().name
            except Exception:
                err_name = "NoError"
            if err_name != "NoError" and err_name != self._mic_err_logged:
                self._mic_err_logged = err_name
                self.mic_error = f"麦克风中断（{err_name}），正在重连"
                _log("[mic] " + self.mic_error)
        try:
            data = io.readAll()
        except Exception as exc:
            _log(f"[mic] 读取失败: {exc}")
            return
        if data:
            self.capture.push(bytes(data))

    def _stop_capture(self) -> None:
        timer = getattr(self, "_pump_timer", None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()
            self._pump_timer = None
        self._src_io = None
        if self._source is not None:
            try:
                self._source.stop()
            except Exception:
                pass
            self._source.deleteLater()
            self._source = None
        self.capture = None
        self._mic_name = ""
        self.mic_note = ""
        self._mic_err_logged = ""
        if self.cable is not None:
            self.cable.mic = None

    def release_capture(self) -> None:
        """放掉麦克风（说话测试结束时用）。

        只在不做注入的时候调：开着注入时采集是"送声"的输入源，关掉等于把人声掐了。
        """
        self._stop_capture()

    def restart_capture(self) -> bool:
        """只重开采集（不碰两个出口），换麦克风 / 说话测试用。"""
        self._stop_capture()
        self._start_capture()
        if self.cable is not None:
            self.cable.mic = self.capture
        return self.capture is not None

    def stop_outputs(self) -> None:
        """拆掉整条链路（sink / 采集都停）。"""
        self._stop_capture()
        for attr in ("_sink", "_cable_sink"):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    obj.stop()
                    obj.deleteLater()
                except Exception:
                    pass
                setattr(self, attr, None)
        if self.cable is not None:
            self.cable.stop_all()
            self.cable.close()
            self.cable.deleteLater()
            self.cable = None
        self._device_name = ""
        self._cable_name = ""

    def rebuild(self) -> None:
        """按当前配置重新搭链路。开关麦克风、换设备都走这里。"""
        self.stop_outputs()
        self.mic_error = ""
        self.cable_error = ""
        self._struct_sig = tuple(str(self.cfg.get(k)) for k in self._STRUCT_KEYS)

        mic_on = bool(self.cfg.get("mic_enabled", False))
        monitor_on = bool(self.cfg.get("monitor_enabled", True))
        # 采集先起来，虚拟声卡那一路要拿它当输入
        if mic_on:
            self._start_capture()
        # 两路都不开等于"哑巴软件"，至少留耳机这一路
        if not monitor_on and not mic_on:
            monitor_on = True
        if monitor_on:
            self._start_monitor_sink()
        if mic_on:
            self._start_cable_sink()
        self._announce_problem()

    def _announce_problem(self) -> None:
        """链路有问题就发一次信号（主程序接托盘气泡）。

        只在内容变化时发：3 秒一次的设备巡检如果每回都发，
        用户会被气泡糊一脸，反而关掉通知。
        """
        if not bool(self.cfg.get("mic_enabled", False)):
            self._last_problem = ""
            return
        msg = self.mic_error or self.cable_error
        if msg == self._last_problem:
            return
        self._last_problem = msg
        if msg:
            self.problem.emit(msg)

    def announce_now(self) -> None:
        """外部刚接上信号时调一次：把启动阶段就存在的问题补报出来。"""
        self._last_problem = ""
        self._announce_problem()

    def _capture_needs_rebuild(self) -> bool:
        """采集这条线是不是需要重开（用它来判断要不要重建链路）。"""
        if not bool(self.cfg.get("mic_enabled", False)):
            return False
        if self.capture is None:
            # 刚失败过就别每 3 秒砸一次：至少隔 10 秒，且确实有麦克风可试
            if time.monotonic() - self._mic_try_at < 10.0:
                return False
            return bool(capture_candidates(str(self.cfg.get("mic_device") or "")))
        src = self._source
        if src is not None:
            try:
                if src.error().name != "NoError":
                    return True
            except Exception:
                pass
        # 正在用的那个麦克风从系统里消失了（拔掉 / 蓝牙断了）
        if self._mic_name and find_input(self._mic_name) is None:
            return True
        return False

    # 兼容旧调用名
    def start(self) -> None:
        self.rebuild()

    def stop_sink(self) -> None:
        self.stop_outputs()

    def restart_sink(self) -> None:
        """插拔耳机 / 蓝牙重连：设备名变了就重建，不用重启程序。

        输出和采集都要看：以前只看输出，麦克风拔了插回来不会自动重连，
        用户以为是软件坏了。
        """
        want_monitor = bool(self.cfg.get("monitor_enabled", True))
        cur = QMediaDevices.defaultAudioOutput().description()
        changed = False
        if self._sink is not None and cur != self._device_name:
            changed = True
        if not self._sink and want_monitor and self._device_name == "":
            changed = True
        if self.cable is not None or bool(self.cfg.get("mic_enabled", False)):
            dev = guess_virtual_output(str(self.cfg.get("cable_device") or ""))
            name = dev.description() if dev is not None else ""
            if name != self._cable_name:
                changed = True
        if not changed and self._capture_needs_rebuild():
            # 只重开采集，别动两个输出：整条链路重建会让正在放的音效卡一下
            _log("[mic] 采集需要重连，单独重开")
            self._stop_capture()
            self._start_capture()
            if self.cable is not None:
                self.cable.mic = self.capture
            self._announce_problem()
            return
        if changed:
            _log("[audio] 设备有变动，重建音频链路")
            self.rebuild()

    def apply_audio_cfg(self) -> None:
        """配置窗口改了音频相关项后调用：音量就地改，结构变了才重建。"""
        self._push_gains()
        sig = tuple(str(self.cfg.get(k)) for k in self._STRUCT_KEYS)
        if sig != self._struct_sig:
            self.rebuild()

    def _push_gains(self) -> None:
        self.mixer.volume = max(0.0, min(1.0, float(self.cfg.get("volume", 0.8))))
        if self.cable is not None:
            self.cable.volume = max(0.0, min(1.0, float(self.cfg.get("cable_effect_gain", 1.0))))
            self.cable.mic_gain = max(0.0, min(2.0, float(self.cfg.get("mic_gain", 0.9))))
            self.cable.mic_target = max(
                0,
                int(self.fmt.sampleRate() * float(self.cfg.get("mic_latency_ms", 60)) / 1000.0),
            )

    # ---- 播放 ----
    def set_volume(self, volume: float) -> None:
        self.mixer.volume = max(0.0, min(1.0, float(volume)))

    @property
    def volume(self) -> float:
        return self.mixer.volume

    def mic_level(self) -> float:
        """麦克风当前电平（0~1），配置窗口的"说话测试"用。"""
        return self.capture.peak() if self.capture is not None else 0.0

    def audio_status(self) -> dict:
        """给配置窗口显示状态用。"""
        return {
            "mic": self._mic_name,
            "cable": self._cable_name,
            "error": self.mic_error,
            "cable_error": self.cable_error,
            "note": self.mic_note,
            "underruns": self.capture.underruns if self.capture else 0,
            "dropped": self.capture.dropped if self.capture else 0,
        }

    def play(self, idx: int) -> bool:
        """播放第 idx 个槽位。会按该音效自己的设置算音量和变调。"""
        if not self._active_mixers():
            self.rebuild()
        if not (0 <= idx < len(self.clips)):
            return False

        # 组合条目：不走普通音效那套连击变调，直接进组合排程
        entry = self.bank.entry_at(idx)
        if isinstance(entry, ComboEntry):
            ok = self.play_combo(entry.cdef)
            if ok:
                self.last_idx = idx
            return ok

        clip = self.clips[idx]
        if clip is None:
            return False
        st = self.bank.setting_at(idx)
        gain = 1.0
        semitones = 0.0
        speed = 0.0

        if st is not None:
            gain = max(0.0, float(st.volume))
            now = time.monotonic()
            win_ms = float(st.pitch_window_ms)
            prev = self._last_at.get(idx)
            # 变调和变速共用同一个"连击窗口"：都是"多少毫秒内再按算一次连击"
            in_window = (
                win_ms > 0 and prev is not None and (now - prev) * 1000.0 <= win_ms
            )

            # ---- 变调 ----
            if st.pitch_mode == PITCH_RANDOM:
                # 随机模式不看连击窗口：每按一次就重新抽一个整数半音
                semitones = self._roll_random(idx, float(st.pitch_step))
                self._pitch_now[idx] = 0.0
            elif st.pitch_mode == PITCH_FIXED:
                # 固定变调：每次都直接变这么多，不累计、不看窗口
                semitones = float(st.pitch_fixed)
                self._pitch_now[idx] = 0.0
            elif st.pitch_mode != PITCH_NONE:
                step = float(st.pitch_step)
                if st.pitch_mode == PITCH_DOWN:
                    step = -step
                self._pitch_now[idx] = combo_value(
                    self._pitch_now.get(idx, 0.0), step,
                    float(st.pitch_limit), in_window,
                )
                semitones = self._pitch_now[idx]
            else:
                self._pitch_now[idx] = 0.0

            # ---- 变速（音调不变）----
            if st.speed_mode != SPEED_NONE:
                step = float(st.speed_step)
                if st.speed_mode == SPEED_DOWN:
                    step = -step
                self._speed_now[idx] = combo_value(
                    self._speed_now.get(idx, 0.0), step,
                    float(st.speed_limit), in_window,
                )
                speed = self._speed_now[idx]
            else:
                self._speed_now[idx] = 0.0

            self._last_at[idx] = now

        # 先变速再变调：拉伸最贵，缓存在"原始波形→拉伸后"这一层，
        # 这样同一档速度配上不同连击数的变调都能复用，不必重算
        if abs(speed) >= 0.01:
            clip = self._stretched(idx, clip, 1.0 + speed)
        if abs(semitones) >= 0.05:
            clip = pitch_shift(clip, semitones)

        if DEBUG and (abs(semitones) >= 0.05 or abs(speed) >= 0.01):
            _log(f"[play] {idx} 变调 {semitones:+.1f} 半音 / 速度 {speed * 100:+.0f}%")
        self.last_idx = idx
        # 每个出口都要触发一次（波形是同一个，进度各走各的）
        ok = False
        for mix in self._active_mixers():
            ok = mix.trigger(clip, gain) or ok
        return ok

    # ---- 组合播放 ----
    @staticmethod
    def combo_random(cdef) -> tuple[float, float]:
        """本次触发的整体参数：(变调半音, 速度倍率)。

        随机幅度在组合级只抽一次，全组合共用同一个值——这样"整体随机变调"
        听起来是"这一遍整体偏高了点"，而不是每一项各自跑调。
        """
        semi = float(getattr(cdef, "semitones", 0.0))
        rate = float(getattr(cdef, "rate", 1.0))
        rs = float(getattr(cdef, "rand_semi", 0.0))
        rr = float(getattr(cdef, "rand_rate", 0.0))
        if rs > 0:
            semi += random.uniform(-rs, rs)
        if rr > 0:
            rate *= 1.0 + random.uniform(-rr, rr)
        return semi, max(0.25, min(4.0, rate))

    def _combo_clip(self, cid: str, i: int, it,
                    rate_abs: float | None = None,
                    semi_abs: float | None = None) -> np.ndarray | None:
        """取组合第 i 项处理好的波形（按该项速度/变调/裁剪处理并缓存）。

        缓存键带上算完之后的实际速度/变调/裁剪值：改了参数自然换新，
        不用手动失效。随机抖动值先量化再进键，否则每按一次就是一个新键，
        缓存等于没有、内存还会被撑爆。
        """
        eff_rate = round(float(getattr(it, "rate", 1.0) if rate_abs is None
                               else rate_abs), 3)
        eff_semi = round(float(getattr(it, "semitones", 0.0) if semi_abs is None
                               else semi_abs), 2)
        key = (cid, i, eff_rate, eff_semi,
               int(getattr(it, "clip_start_ms", 0)),
               int(getattr(it, "clip_len_ms", 0)))
        if key in self._combo_cache:
            return self._combo_cache[key]
        clip = combo_item_clip(it, self.fmt, float(self.cfg.get("fade_ms", 6)),
                               rate_abs=eff_rate, semi_abs=eff_semi)
        self._combo_cache[key] = clip
        self._trim_combo_cache()
        return clip

    def _trim_combo_cache(self) -> None:
        """缓存按总字节数收敛，不是按条数。

        波形大小差得远（0.2 秒的一下 vs 8 秒的一段），按条数限流会出现
        "96 条就占了 300MB"或者反过来"早就该清了还留着"。
        """
        limit = 96 * 1024 * 1024
        total = 0
        for v in self._combo_cache.values():
            if v is not None:
                total += int(v.nbytes)
        while total > limit and len(self._combo_cache) > 1:
            k = next(iter(self._combo_cache))
            v = self._combo_cache.pop(k)
            if v is not None:
                total -= int(v.nbytes)

    def warm_combo(self, cdef) -> int:
        """预渲染一条组合：按当前参数把每项都算进缓存，下次按键就是零等待。

        冷启动时一次 6 项的组合要 100ms 出头（解码 + 拉伸 + 重采样），
        按键后能听出一点"慢半拍"；烘焙过之后触发只是从缓存里取数组。
        """
        if cdef is None:
            return 0
        cs, cr = float(getattr(cdef, "semitones", 0.0)), float(getattr(cdef, "rate", 1.0))
        n = 0
        for i, it in enumerate(list(getattr(cdef, "items", []) or [])):
            clip = self._combo_clip(cdef.cid, i, it,
                                    float(getattr(it, "rate", 1.0)) * cr,
                                    float(getattr(it, "semitones", 0.0)) + cs)
            if clip is not None:
                n += 1
        return n

    def warm_all_async(self, delay_ms: int = 1500) -> None:
        """启动后延迟一点，把所有组合一条一条烘焙完。

        分条做、每条之间让出一次事件循环：一次烘 12 条会卡住界面半秒多，
        用户看到的就是"刚开软件时点不动"。
        """
        combos = []
        scfg = getattr(self.bank, "scfg", None)
        if scfg is not None:
            combos = list(scfg.combos.values())
        self._warm_queue = combos
        if self._warm_timer is None:
            self._warm_timer = QTimer()
            self._warm_timer.setInterval(60)
            self._warm_timer.timeout.connect(self._warm_tick)
        QTimer.singleShot(max(0, int(delay_ms)), self._warm_timer.start)

    def _warm_tick(self) -> None:
        if not self._warm_queue:
            if self._warm_timer is not None:
                self._warm_timer.stop()
            return
        try:
            cdef = self._warm_queue.pop(0)
            n = self.warm_combo(cdef)
            if DEBUG:
                _log(f"[warm] 预渲染 {getattr(cdef, 'name', '?')}：{n} 项")
        except Exception as exc:
            _log(f"[warm] 预渲染失败: {exc}")

    def combo_preview_clip(self, it) -> np.ndarray | None:
        """编辑器"试听这一项"用：按该项参数算好一段波形（不入缓存）。"""
        return combo_item_clip(it, self.fmt, float(self.cfg.get("fade_ms", 6)))

    def play_preview(self, it) -> bool:
        """试听组合里的某一项（只响这一下，不排程）。"""
        clip = self.combo_preview_clip(it)
        if clip is None:
            return False
        ok = False
        for mix in (self._active_mixers() or self._mixers_all()):
            ok = mix.trigger(clip, 1.0) or ok
        return ok

    def play_combo(self, cdef: ComboDef, from_row: int | None = None) -> bool:
        """播放一个组合音效。

        步骤只有三步，全部可预期：
          1. 决定这次播哪几项（顺序模式 = 全部；随机模式 = 抽 N 个）
          2. 算出这些项的成品波形与其时长（缺失成员跳过，不中断别人）
          3. 用 combo_plan 一次算出每项的起始帧，交给混音器按帧顺延
        没有定时器、没有线程、没有"播到一半再决定下一步"的回调。

        from_row 给编辑器"从某一行开始试听"用：从那一项起往后排，前面不管。
        """
        if not self._active_mixers():
            self.rebuild()
        items = list(cdef.items)
        if not items:
            return False

        # 冷却：刚按过就先不受理，避免连点把同一条组合叠成一团糊音
        now = time.monotonic()
        cd = float(getattr(cdef, "cooldown_ms", 0)) / 1000.0
        if cd > 0 and now - self._combo_last.get(cdef.cid, -1e9) < cd:
            if DEBUG:
                _log(f"[combo] {cdef.name} 冷却中，忽略")
            return False

        if from_row is not None and 0 <= from_row < len(items):
            order = list(range(from_row, len(items)))
        else:
            n_step = max(1, len(items))
            cur = self._combo_step.get(cdef.cid, 0) % n_step
            order = cdef.play_order(cur)
            # 推游标：只有"按顺序点击 / 累加"模式需要，播满一圈自动绕回第一项
            if cdef.steps_per_trigger():
                self._combo_step[cdef.cid] = (cur + cdef.steps_per_trigger()) % n_step
        if not order:
            return False

        cs, cr = self.combo_random(cdef)
        rate = self.fmt.sampleRate()
        clips: dict[int, np.ndarray] = {}
        durs: dict[int, float] = {}
        for i in order:
            it = items[i]
            ir = float(getattr(it, "rate", 1.0)) * cr
            is_ = float(getattr(it, "semitones", 0.0)) + cs
            # 逐项随机：只抖这一项，别的项不受影响
            rr = float(getattr(it, "rand_rate", 0.0))
            rs = float(getattr(it, "rand_semi", 0.0))
            if rr > 0:
                ir *= 1.0 + random.uniform(-rr, rr)
            if rs > 0:
                is_ += random.uniform(-rs, rs)
            clip = self._combo_clip(cdef.cid, i, it, ir, is_)
            if clip is None:
                if DEBUG:
                    _log(f"[combo] {cdef.name} 第{i + 1}项取不到波形: {items[i].sound}")
                durs[i] = 0.0
                continue
            clips[i] = clip
            durs[i] = len(clip) / float(rate)

        plan = combo_plan(items, order, durs, rate)
        if not plan:
            return False
        self._combo_last[cdef.cid] = now

        # 组合在轮盘上的整体音量（和普通音效共用一套参数）
        vol = 1.0
        scfg = getattr(self.bank, "scfg", None)
        if scfg is not None:
            try:
                vol = max(0.0, float(scfg.setting(COMBO_PREFIX + cdef.cid).volume))
            except Exception:
                vol = 1.0

        max_voices = int(getattr(cdef, "max_voices", 0))
        ok = False
        for i, delay in plan:
            clip = clips.get(i)
            it = items[i]
            if clip is None:
                continue          # 文件不在：这一项静音，其他项照常
            gain = vol * max(0.0, float(it.gain))
            for mix in self._active_mixers():
                ok = mix.trigger(clip, gain, delay,
                                 group=cdef.cid, max_voices=max_voices) or ok
        if DEBUG:
            _log(f"[combo] {cdef.name}: 排程 {len(plan)} 项 "
                 + ", ".join(f"#{i + 1}@{d / rate:.2f}s" for i, d in plan))
        return ok

    def bake_combo(self, cdef, from_row: int | None = None) -> tuple[np.ndarray, int] | None:
        """把整条组合渲染成一条波形（导出 WAV、试听整体都走这里）。

        和实时播放用同一套参数与排程，所以导出的东西和听到的一模一样。
        这里故意不套用随机抖动：导出的文件应当是可复现的那一版。
        """
        items = list(getattr(cdef, "items", []) or [])
        if not items:
            return None
        if from_row is not None and 0 <= from_row < len(items):
            order = list(range(from_row, len(items)))
        elif cdef.steps_per_trigger():
            # 推进式模式（按顺序点击 / 累加）：导出的是整条成员的完整一轮，
            # 而不是"下一次按会响的那一段"，否则导出的 WAV 只有一个音效
            order = list(range(len(items)))
        else:
            order = cdef.play_order()
        if not order:
            return None
        cs, cr = float(getattr(cdef, "semitones", 0.0)), float(getattr(cdef, "rate", 1.0))
        rate = self.fmt.sampleRate()
        ch = max(1, self.fmt.channelCount())

        clips: dict[int, np.ndarray] = {}
        durs: dict[int, float] = {}
        for i in order:
            it = items[i]
            clip = self._combo_clip(cdef.cid, i, it,
                                    float(getattr(it, "rate", 1.0)) * cr,
                                    float(getattr(it, "semitones", 0.0)) + cs)
            if clip is None:
                durs[i] = 0.0
                continue
            clips[i] = clip
            durs[i] = len(clip) / float(rate)
        plan = combo_plan(items, order, durs, rate)
        if not plan:
            return None

        vol = 1.0
        scfg = getattr(self.bank, "scfg", None)
        if scfg is not None:
            try:
                vol = max(0.0, float(scfg.setting(COMBO_PREFIX + cdef.cid).volume))
            except Exception:
                vol = 1.0

        total = 0
        for i, delay in plan:
            clip = clips.get(i)
            if clip is None:
                continue
            total = max(total, delay + len(clip))
        if total <= 0:
            return None
        total = min(total, rate * 300)      # 上限 5 分钟，防止离谱参数撑爆内存

        out = np.zeros((total, ch), dtype=np.float32)
        for i, delay in plan:
            clip = clips.get(i)
            if clip is None or delay >= total:
                continue
            seg = clip[: total - delay]
            g = vol * max(0.0, float(items[i].gain))
            if g != 1.0:
                seg = seg * g
            out[delay:delay + len(seg)] += seg
        np.clip(out, -1.0, 1.0, out=out)
        return out, rate

    def export_combo_wav(self, cdef, path: Path | str) -> tuple[bool, str]:
        """把组合导出成一个 16bit WAV 文件。返回 (成功, 提示)。"""
        baked = self.bake_combo(cdef)
        if baked is None:
            return False, "这条组合里没有能出声的成员，没有东西可导出。"
        data, rate = baked
        import wave

        try:
            pcm = np.clip(data, -1.0, 1.0)
            pcm = (pcm * 32767.0).astype(np.int16)
            with wave.open(str(path), "wb") as fp:
                fp.setnchannels(int(data.shape[1]))
                fp.setsampwidth(2)
                fp.setframerate(int(rate))
                fp.writeframes(pcm.tobytes())
        except Exception as exc:
            return False, f"写入失败：{exc}"
        return True, f"已导出：{Path(path).name}（{len(data) / float(rate):.2f} 秒）"

    def play_repeat_last(self) -> bool:
        """重复播放上一次的音效。"""
        if self.last_idx is None:
            return False
        return self.play(self.last_idx)

    def play_next(self) -> bool:
        """按槽位顺序播放下一个，到末尾回到开头。"""
        n = len(self.bank)
        if n == 0:
            return False
        self._cycle = (self._cycle + 1) % n
        return self.play(self._cycle)

    def play_named(self, name: str) -> bool:
        """按配置键触发（快捷键用）。

        组合没上轮盘时也该能被专属热键按响，所以找不到槽位时再查一次
        组合表——热键的意义本来就是"不占格子也能用"。
        """
        idx = self.bank.index_of_name(name)
        if idx >= 0:
            return self.play(idx)
        scfg = getattr(self.bank, "scfg", None)
        if scfg is not None and is_combo_key(name):
            cdef = scfg.combos.get(name[len(COMBO_PREFIX):])
            if cdef is not None:
                return self.play_combo(cdef)
        return False

    def _roll_random(self, idx: int, amp: float) -> float:
        """抽一个整数半音，落在 [-amp, +amp] 内，并避开上一次抽到的值。

        用整数而不是小数：小数听着是"飘"，整数半音是"准准地跑调"，
        连按起来才是鬼畜那种效果。
        """
        top = int(round(max(0.0, float(amp))))
        choices = [float(s) for s in range(-top, top + 1)]
        prev = self._rnd_pitch.get(idx)
        pick = random.choice(choices)
        for _ in range(8):
            if prev is None or abs(pick - prev) > 0.01:
                break
            pick = random.choice(choices)
        self._rnd_pitch[idx] = pick
        return pick

    def _stretched(self, idx: int, clip: np.ndarray, rate: float) -> np.ndarray:
        """取"这一档速度"拉伸好的波形，结果缓存。

        拉伸比变调贵（要做波形相似度搜索），但同一档速度的结果永远一样，
        所以连按同一速度时第二次起就是直接取缓存，按键零延迟。
        """
        key = (idx, round(rate, 4))
        hit = self._stretch_cache.get(key)
        if hit is not None:
            return hit
        out = time_stretch(clip, rate)
        self._stretch_cache[key] = out
        # 上限 24 档（约 20~30MB）：最多也就 6 秒的音效，不会无限长
        while len(self._stretch_cache) > 24:
            self._stretch_cache.pop(next(iter(self._stretch_cache)))
        return out

    def reset_pitch(self) -> None:
        """清空连击状态（换音效、重新加载后调用，避免残留偏移）。"""
        self._last_at.clear()
        self._pitch_now.clear()
        self._rnd_pitch.clear()
        self._speed_now.clear()

    def stop_all(self) -> None:
        """把正在响的声音立刻掐掉（中空区域松手时用）。两个出口都要掐。"""
        for mix in self._mixers_all():
            mix.stop_all()

    @property
    def playing(self) -> bool:
        return any(mix.playing for mix in self._mixers_all())

    def __len__(self) -> int:
        return len(self.clips)


# ---------------------------------------------------------------- 轮盘窗口

class WheelWidget(QWidget):
    """覆盖在游戏上方的环形轮盘。

    整窗样式为 WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE：
    画得出来、鼠标完全穿透、永不抢焦点。

    选择判定不依赖这个窗口接收任何鼠标事件，而是靠 Raw Input 旁听到的
    位移驱动一个"虚拟光标"，所以对游戏输入零干扰。
    """

    def __init__(self, cfg: dict, embedded: bool = False) -> None:
        """embedded=True 时按普通子控件建，供配置窗口内嵌预览用：
        不能置顶、不能鼠标穿透，否则在设置界面里点不到扇区。"""
        if embedded:
            super().__init__(None)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setFocusPolicy(Qt.StrongFocus)
        else:
            super().__init__(
                None,
                Qt.Tool
                | Qt.FramelessWindowHint
                | Qt.WindowStaysOnTopHint
                | Qt.WindowDoesNotAcceptFocus,
            )
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.setAttribute(Qt.WA_ShowWithoutActivating, True)
            self.setFocusPolicy(Qt.NoFocus)
        self.embedded = embedded
        self.cfg = cfg
        self.bank: SoundBank | None = None
        self.selected: int | None = None
        self.vx = 0.0
        self.vy = 0.0
        self.raw_ok = True
        # 供中空区域的提示文案用：有声音在响时，松手是"停"而不是"取消"
        self.playing = False
        # 程序是不是处于"用户暂停"状态：中心提示要变成"松开恢复"
        self.paused = False
        # 这套轮盘自己的颜色（(r,g,b) 或 "#rrggbb"）；None = 跟随应用主题色
        self.accent_rgb = None
        # ---- 动画状态 ----
        # anim_scale / anim_alpha 只在动画进行时偏离 1.0，
        # 静止时保持 1.0 → paintEvent 走"直接画"的零开销路径。
        self.anim_scale = 1.0
        self.anim_alpha = 1.0
        # True = 正在播"释放音效"的闪出：整盘不画，只画选中那一格
        self.anim_flash = False
        self._anim_open: QVariantAnimation | None = None
        self._anim_close: QVariantAnimation | None = None
        # 关窗动画播到一半又被叫去显示时，靠这个代号让旧的回调失效
        self._anim_gen = 0
        # 动画期间把绘制目标换成离屏图，静止时是 None（直接画到控件上）
        self._paint_to = None

    # ---- 动画 ----
    def anim_on(self) -> bool:
        return bool(self.cfg.get("animations", True))

    def anim_busy(self) -> bool:
        return self.anim_scale < 0.999 or self.anim_alpha < 0.999

    def stop_anims(self) -> None:
        """立刻掐掉正在跑的动画。

        必须先让旧代号失效再 stop()：QAbstractAnimation.stop() 在 Qt 里
        会照常发出 finished，不拦一下的话，"关窗动画"会在新一次弹出之后
        把刚显示的轮盘又藏起来。
        """
        self._anim_gen += 1
        for a in (self._anim_open, self._anim_close):
            if a is not None:
                a.stop()
        self._anim_open = None
        self._anim_close = None
        self.anim_scale = 1.0
        self.anim_alpha = 1.0
        self.anim_flash = False

    def play_open_anim(self) -> None:
        """弹出：从略小、全透明长到正常大小。快起慢收，约 0.15 秒。"""
        self.stop_anims()
        if not self.anim_on():
            self.update()
            return
        self.anim_scale = 0.86
        self.anim_alpha = 0.0

        a = QVariantAnimation(self)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setDuration(150)
        a.setEasingCurve(QEasingCurve.OutCubic)

        def on_tick(v) -> None:
            t = float(v)
            self.anim_scale = 0.86 + 0.14 * t
            self.anim_alpha = min(1.0, t * 1.35)   # 透明度比尺寸先到位，观感更利索
            self.update()

        def on_done() -> None:
            if gen != self._anim_gen:
                return
            self.anim_scale = 1.0
            self.anim_alpha = 1.0
            self._anim_open = None
            self.update()

        gen = self._anim_gen
        a.valueChanged.connect(on_tick)
        a.finished.connect(on_done)
        self._anim_open = a
        a.start()

    def play_close_anim(self, on_done) -> None:
        """释放/收起：整体轻微涨大同时淡出，约 0.18 秒。

        选中格保持高亮不动，涨大那一下看起来像"把音效甩出去"。
        """
        self.stop_anims()
        if not self.anim_on():
            on_done()
            return

        # 涨大必须留够窗口余量：窗口尺寸是"最外缘 ×2 + 48"，四周只有 24px 空地。
        # 轮盘调大之后固定 5% 会溢出被裁，所以按当前实际半径算出可用的最大幅度。
        count = len(self.bank) if self.bank is not None else 0
        extent = ring_layout(self.cfg, count, self.paint_scale())["extent"]
        grow_max = min(0.05, 16.0 / max(1.0, extent))

        a = QVariantAnimation(self)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setDuration(180)
        a.setEasingCurve(QEasingCurve.OutQuad)

        def on_tick(v) -> None:
            t = float(v)
            self.anim_scale = 1.0 + grow_max * t
            self.anim_alpha = max(0.0, 1.0 - t * 1.15)
            self.update()

        def on_finish() -> None:
            if gen != self._anim_gen:
                return          # 已经被新一次弹出接管，别把轮盘藏掉
            self.anim_scale = 1.0
            self.anim_alpha = 1.0
            self._anim_close = None
            on_done()

        gen = self._anim_gen
        a.valueChanged.connect(on_tick)
        a.finished.connect(on_finish)
        self._anim_close = a
        a.start()

    def play_flash_anim(self, on_done) -> None:
        """释放音效：整盘立刻消失，只留选中那一格涨大淡出，约 0.2 秒。

        和 play_close_anim 的区别是"画什么"：那个是整盘一起涨大淡出，
        这个是 anim_flash=True 后 _paint_body 只画选中扇区——其余部分
        当帧就没了，视觉上是"从轮盘里抽出一片甩出去"。
        """
        self.stop_anims()
        if not self.anim_on() or self.selected is None:
            on_done()
            return

        self.anim_flash = True
        self.anim_scale = 1.0
        self.anim_alpha = 1.0

        # 和收起动画同理：窗口四周只有 24px 余量，按当前半径定涨大上限，
        # 免得轮盘调到 140% 之后最外缘被窗口裁掉一条边。
        count = len(self.bank) if self.bank is not None else 0
        extent = ring_layout(self.cfg, count, self.paint_scale())["extent"]
        grow_max = min(0.06, 18.0 / max(1.0, extent))

        a = QVariantAnimation(self)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setDuration(200)
        # 用线性推进，两条曲线自己算：整体缓动的话，形状刚看清就已经淡没了
        a.setEasingCurve(QEasingCurve.Linear)

        def on_tick(v) -> None:
            t = float(v)
            grow = 1.0 - (1.0 - t) ** 2      # 尺寸前快后慢，像"甩"出去
            self.anim_scale = 1.0 + grow_max * grow
            self.anim_alpha = max(0.0, 1.0 - t * t)   # 前段几乎不透明，后段才化掉
            self.update()

        def on_finish() -> None:
            if gen != self._anim_gen:
                return          # 已经被新一次弹出接管，别把轮盘藏掉
            self.anim_flash = False
            self.anim_scale = 1.0
            self.anim_alpha = 1.0
            self._anim_close = None
            on_done()

        gen = self._anim_gen
        a.valueChanged.connect(on_tick)
        a.finished.connect(on_finish)
        self._anim_close = a
        self.update()            # 先把整盘擦掉，别等第一帧
        a.start()

    def user_scale(self) -> float:
        """「整体大小」那一项（1.0 = 100%）。"""
        return wheel_scale_of(self.cfg)

    def paint_scale(self) -> float:
        """这一帧轮盘所有像素尺寸的总缩放：预览适配 × 用户整体大小。"""
        return self.view_scale() * self.user_scale()

    def view_scale(self) -> float:
        """配置窗口里的预览要整体等比缩放。

        外圈一出现轮盘就变大（内圈尺寸不动），预览区放不下，
        所以按比例缩；游戏里的轮盘永远 1.0，所见即所得。

        预览框有多大就用多大（不设 1.0 上限）：100% 时占满框的
        1/PREVIEW_SCALE_MAX，刚好给「整体大小」留出拖到 140% 的余量。
        以前这里既乘 0.74 又夹了 min(1.0, …)，框做大也没用，轮盘永远
        只有小小一圈。
        """
        if not getattr(self, "embedded", False):
            return 1.0
        count = len(self.bank) if self.bank is not None else 0
        extent = ring_layout(self.cfg, count, 1.0)["extent"]
        room = min(self.width(), self.height()) / 2.0 - 6.0
        if extent <= 0 or room <= 0:
            return 1.0
        return room / (extent * PREVIEW_SCALE_MAX)

    def slot_pairs(self, geo: dict) -> list[tuple[int, int]]:
        """[(槽位号, 音效下标)]，按槽位号升序。外圈空着的位置不在里面。

        槽位号是"位置"：0~7 内圈，8~19 外圈 12 个固定位置。
        音效下标是"第几个音效"。外圈能留空，所以这两个必须分开看。
        """
        count = len(self.bank) if self.bank is not None else 0
        pairs = [(i, i) for i in range(min(int(geo["inner_n"]), count))]
        if geo["two_ring"]:
            for pos, idx in enumerate(outer_index_map_of(self.bank)):
                if idx is not None:
                    pairs.append((INNER_MAX + pos, idx))
        return pairs

    def apply_style(self) -> None:
        if getattr(self, "embedded", False):
            return   # 内嵌预览不能设 Win32 穿透/置顶
        try:
            hwnd = int(self.winId())
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception as exc:
            _log(f"[wheel] 设置窗口样式失败: {exc}")

    # ---- 绘制 ----
    def paintEvent(self, event) -> None:  # noqa: N802
        if self.bank is None:
            return
        if not self.anim_busy():
            # 静止状态：直接画到控件上，跟没加动画时完全一样，零额外开销
            theme.push_accent(self.accent_rgb)
            try:
                self._paint_body(event)
            finally:
                theme.pop_accent()
            return
        # 动画中：先画一张同样大小的离屏图，再带透明度/缩放贴回控件。
        # 只在动画那零点二秒里走这条路，平时跑不到这里。
        pm = QPixmap(self.size())
        pm.fill(Qt.transparent)
        theme.push_accent(self.accent_rgb)
        try:
            self._paint_to = pm
            self._paint_body(event)
        finally:
            self._paint_to = None
            theme.pop_accent()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setOpacity(max(0.0, min(1.0, self.anim_alpha)))
        if abs(self.anim_scale - 1.0) > 1e-4:
            cx, cy = self.width() / 2.0, self.height() / 2.0
            p.translate(cx, cy)
            p.scale(self.anim_scale, self.anim_scale)
            p.translate(-cx, -cy)
        p.drawPixmap(0, 0, pm)
        p.end()

    def _paint_slot_names(self, p: QPainter, cx: float, cy: float, geo: dict,
                          radius: float, only_idx: int | None = None) -> None:
        """画扇区上的音效名。only_idx 给了就只画那一个音效的（闪出动画用）。"""
        if not self.cfg.get("show_names", True):
            return
        selected = self.selected
        s = max(0.55, self.paint_scale())
        font = QFont(UI_FONT)
        font.setPointSizeF(max(6.0, 9.0 * s))
        font.setWeight(QFont.DemiBold)
        p.setFont(font)
        fm = QFontMetrics(font)
        for sid, idx in self.slot_pairs(geo):
            if only_idx is not None and idx != only_idx:
                continue
            geom = slot_geometry(geo, sid)
            if geom is None:
                continue
            r0, r1, start_deg, span = geom
            tr = (r0 + r1) / 2.0
            # 扇形在切向上的可用宽度（弦长）
            tangent_w = 2.0 * tr * math.sin(math.radians(span / 2.0)) * 0.92
            rad = math.radians(start_deg - span / 2.0)
            tx = cx + tr * math.cos(rad)
            ty = cy - tr * math.sin(rad)
            # 文字是水平排布的，除了受扇形弦长限制，还必须夹在轮盘的
            # 左右边缘以内。只有 2 个音效时扇区宽 180°，文字中心几乎
            # 贴着轮盘边缘，不夹住就会画出窗口被裁掉半截。
            edge_room = min(tx - (cx - radius + 8.0 * s), (cx + radius - 8.0 * s) - tx)
            label_w = max(28.0 * s, min(tangent_w, max(0.0, edge_room) * 2.0))
            raw = self.bank.name_at(idx)
            text = fm.elidedText(raw, Qt.ElideRight, int(label_w))
            # 选中扇区是亮色填充，文字必须反过来用深色，否则糊成一片
            color = (
                QColor(14, 42, 24, 255)
                if idx == selected
                else QColor(198, 202, 212, 235)
            )
            p.setPen(QPen(color))
            p.drawText(
                QRectF(tx - label_w / 2, ty - 9 * s, label_w, 18 * s),
                Qt.AlignCenter,
                text,
            )

    def _paint_flash_sector(self, p: QPainter, cx: float, cy: float,
                            geo: dict, selected: int) -> None:
        """只画"松开手时选中的那一格"。释放动画专用。

        轮盘本体在这一帧已经全部不画了，所以这里不能依赖任何别的绘制，
        自己把填充、描边、外发光都补齐。
        """
        for sid, idx in self.slot_pairs(geo):
            if idx != selected:
                continue
            geom = slot_geometry(geo, sid)
            if geom is None:
                return
            r0, r1, start_deg, span = geom
            path = ring_sector_path(cx, cy, r0, r1, start_deg, span)
            s = max(0.55, self.paint_scale())
            # 外发光：同一条路径先用粗半透明笔画一遍，边缘有一点溢出的感觉
            glow = accent_light(70)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(glow, 7.0 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(path)
            p.setBrush(accent(240))
            p.setPen(QPen(accent_light(255), 2.2 * s))
            p.drawPath(path)
            self._paint_slot_names(p, cx, cy, geo, geo["extent"], only_idx=idx)
            return

    def _paint_body(self, event) -> None:
        cfg = self.cfg
        cx, cy = self.width() / 2.0, self.height() / 2.0
        opacity = float(cfg["opacity"])

        p = QPainter(self._paint_to if self._paint_to is not None else self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        count = len(self.bank)
        # 「整体大小」乘在预览适配比例上：所有半径、厚度、字号都吃这一个值，
        # 判定那边用 wheel_scale_of() 拿到同一个数，两边永远对得上。
        scale = self.paint_scale()
        geo = ring_layout(cfg, count, scale)
        radius = geo["extent"]
        inner = geo["hole"]
        s = max(0.55, scale)          # 像素常量（行距、光点、描边）统一跟着缩
        n = max(1, count)
        selected = self.selected

        # 释放动画：轮盘本体已经"整盘消失"，只剩选中那一格在涨大淡出。
        # 放在最前面短路掉，后面那些扇区/中心圆/文字一个都不画。
        if self.anim_flash and selected is not None:
            self._paint_flash_sector(p, cx, cy, geo, selected)
            p.end()
            return

        if count == 0:
            # 一个音效都没有：画个虚线圈提示可以拖，别画一个写着"空槽位"的扇区
            p.setPen(QPen(QColor(110, 118, 134, 190), 2.0, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
            f = QFont(UI_FONT)
            f.setPointSizeF(max(6.0, 10.0 * s))
            p.setFont(f)
            p.setPen(QPen(QColor(150, 158, 172, 235)))
            p.drawText(
                QRectF(cx - radius, cy - 12, radius * 2, 24),
                Qt.AlignCenter,
                "把音效拖到这里",
            )
            p.end()
            return

        for sid, idx in self.slot_pairs(geo):
            geom = slot_geometry(geo, sid)
            if geom is None:
                continue
            r0, r1, start_deg, span = geom
            # 第 sid 格覆盖数学角度 [90 - sid*span, 90 - (sid+1)*span]，
            # 即从正上方开始顺时针排布，与 index_from_delta 完全一致。
            path = ring_sector_path(cx, cy, r0, r1, start_deg, span)
            if idx == selected:
                fill = accent(238)
                border = accent_light(255)
            else:
                fill = QColor(22, 24, 31, int(215 * opacity))
                border = QColor(122, 128, 142, 200)
            p.setBrush(fill)
            p.setPen(QPen(border, (1.2 if idx != selected else 2.0) * s))
            p.drawPath(path)

        # 中心圆：和普通格子用同一套填充/描边，不然中间会像塌下去一块黑。
        p.setBrush(QColor(22, 24, 31, int(215 * opacity)))
        p.setPen(QPen(QColor(122, 128, 142, 200), 1.2 * s))
        p.drawEllipse(QRectF(cx - inner, cy - inner, inner * 2, inner * 2))

        # 扇区文字（内圈外圈各一遍，位置都由 slot_geometry 决定）
        self._paint_slot_names(p, cx, cy, geo, radius)

        # 中心提示
        f1 = QFont(UI_FONT)
        f1.setPointSizeF(max(6.0, 10.0 * s))
        f1.setWeight(QFont.DemiBold)
        p.setFont(f1)
        p.setPen(QPen(QColor(238, 240, 246, 240)))
        fm1 = QFontMetrics(f1)
        if getattr(self, "embedded", False):
            # 配置窗口里的预览：文案要讲"编辑"，不能讲"松开播放"
            if selected is None:
                main_hint = "点击扇区"
                sub_hint = f"共 {n} 个音效"
            else:
                main_hint = fm1.elidedText(
                    self.bank.name_at(selected), Qt.ElideRight, int(inner * 1.6)
                )
                sub_hint = "正在编辑这一个"
            # 预览会把"拖到中心要干什么"塞到这一行（例如“＋ 添加到末尾”），
            # 免得另起一行文字和音效名挤在一起
            sub_hint = getattr(self, "center_hint", "") or sub_hint
        elif not self.raw_ok:
            main_hint = "鼠标输入不可用"
            sub_hint = "请查看 sr_roulette.log"
        elif selected is None:
            main_hint = "移动鼠标选择"
            # 中心松手现在既是"停"也是"暂停"，文案要把这层意思说清楚
            if getattr(self, "paused", False):
                sub_hint = "松开恢复"
            else:
                sub_hint = "松开停止并暂停" if self.playing else "松开暂停"
        else:
            main_hint = fm1.elidedText(
                self.bank.name_at(selected), Qt.ElideRight, int(inner * 1.6)
            )
            sub_hint = "松开播放"
        p.drawText(
            QRectF(cx - inner, cy - 38 * s, inner * 2, 22 * s),
            Qt.AlignCenter, main_hint,
        )

        f2 = QFont(UI_FONT)
        f2.setPointSizeF(max(5.5, 8.0 * s))
        p.setFont(f2)
        p.setPen(QPen(QColor(152, 158, 172, 225)))
        p.drawText(
            QRectF(cx - inner, cy + 14 * s, inner * 2, 18 * s),
            Qt.AlignCenter, sub_hint,
        )

        # 虚拟光标：这是"你手当前指哪儿"的唯一可视化，让所见即所选
        dotx = cx + self.vx
        doty = cy + self.vy
        dist = math.hypot(self.vx, self.vy)
        # 只有真的推离中空区才发光晕；停在中心时发光会盖住上面的提示文字。
        # 阈值和判定同一个口径（中空半径），光标一离开白圈就有反馈。
        if dist > inner:
            glow = QRadialGradient(QPointF(dotx, doty), 20.0 * s)
            glow.setColorAt(0.0, accent_light(170))
            glow.setColorAt(1.0, accent(0))
            p.setBrush(glow)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(dotx, doty), 20.0 * s, 20.0 * s)

        # 选中态用浅色实心 + 深绿描边，在高亮扇区上也能一眼看见
        if selected is not None:
            p.setBrush(QColor(234, 255, 243, 255))
            p.setPen(QPen(accent_dark(255), 2.0))
        else:
            p.setBrush(QColor(210, 214, 224, 235))
            p.setPen(QPen(QColor(255, 255, 255, 235), 2.0))
        p.drawEllipse(QPointF(dotx, doty), 7.0 * s, 7.0 * s)

        # 从内圈外缘到光标的一条指示线，帮助看清当前指向。
        # 必须从内圈边缘起画，否则会横穿中心文字，把提示糊成一条划线。
        if dist > inner * 0.95:
            ux, uy = self.vx / dist, self.vy / dist
            p.setPen(QPen(accent(150), 2.0 * s, Qt.DashLine))
            p.drawLine(
                QPointF(cx + ux * inner * 0.95, cy + uy * inner * 0.95),
                QPointF(dotx, doty),
            )

        p.end()


# ---------------------------------------------------------------- 切换轮盘的轮盘


class WheelSwitchWidget(QWidget):
    """切换轮盘用的"轮盘的轮盘"：只一圈，每格是一套轮盘。

    刻意做成独立窗口，不复用主轮盘：主轮盘那套东西（内圈/外圈/空位/
    组合条目）都是为了"播放音效"，这里只需要"选一个名字"，
    硬塞进去反而会让两边都变难改。
    """

    def __init__(self, cfg: dict, embedded: bool = False) -> None:
        if embedded:
            super().__init__(None)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setFocusPolicy(Qt.StrongFocus)
        else:
            super().__init__(
                None,
                Qt.Tool
                | Qt.FramelessWindowHint
                | Qt.WindowStaysOnTopHint
                | Qt.WindowDoesNotAcceptFocus,
            )
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.setAttribute(Qt.WA_ShowWithoutActivating, True)
            self.setFocusPolicy(Qt.NoFocus)
        self.embedded = embedded
        self.cfg = cfg
        # [(wid, 名字, 颜色)]，颜色空字符串 = 跟随主题色
        self.entries: list[tuple[str, str, str]] = []
        self.current = ""
        self.selected: int | None = None
        self.vx = 0.0
        self.vy = 0.0
        self.raw_ok = True
        # 扇区路径缓存：光标每帧都在动，但几何不是每帧都变，
        # 不缓存的话每一帧都要重建 N 条贝塞尔曲线，白白吃掉帧时间
        self._paths: list = []
        self._paths_key: tuple = ()

    def set_entries(self, entries: list[tuple[str, str, str]], current: str) -> None:
        self.entries = list(entries)
        self.current = current
        self.selected = None
        self._paths_key = ()
        self.update()

    def _entry_paint(self, color: str) -> dict:
        """某套轮盘自己的颜色 -> 选中态要用的几个 QColor。

        没设过颜色（color 为空 / 读不出来）时返回空 dict，
        调用方退回应用主题色——这就是"跟随主题色"那条路。
        """
        rgb = theme.parse_rgb(color)
        if rgb is None:
            return {}
        base, light, dark = theme.derive(rgb)
        return {
            "base": QColor(base[0], base[1], base[2], 200),
            "fill": QColor(base[0], base[1], base[2], 238),
            "line": QColor(light[0], light[1], light[2], 255),
            "light": QColor(light[0], light[1], light[2], 238),
            "dark": QColor(dark[0], dark[1], dark[2], 255),
            # 亮底压深字、暗底放白字，免得用户挑了个深蓝导致名字看不见
            "text": (QColor(16, 18, 24, 250) if theme.is_light(base)
                     else QColor(246, 250, 255, 250)),
        }

    def radius(self) -> float:
        return (
            float(self.cfg.get("wheel_radius", 180))
            * 0.86
            * wheel_scale_of(self.cfg)
        )

    def hole_radius(self) -> float:
        """中空半径 = 画出来那个中心圆。

        选中判定必须用它，不能再用固定像素死区：以前这里是 24px，
        而画出来的白圈半径有 70 多，手感就是"手还在中间、格子已经亮了"。
        """
        return self.radius() * 0.50

    def apply_style(self) -> None:
        if getattr(self, "embedded", False):
            return
        try:
            hwnd = int(self.winId())
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception as exc:
            _log(f"[switch] 设置窗口样式失败: {exc}")

    def slot_geom(self, k: int, n: int) -> tuple[float, float, float, float]:
        radius = self.radius()
        inner = self.hole_radius()
        span = 360.0 / max(1, n)
        return inner, radius, 90.0 - k * span, span

    def paintEvent(self, event) -> None:  # noqa: N802
        cx, cy = self.width() / 2.0, self.height() / 2.0
        radius = self.radius()
        inner = self.hole_radius()
        n = len(self.entries)
        opacity = float(self.cfg.get("opacity", 0.94))
        # 「整体大小」也管这个选择器：半径变了，字号和线宽得跟着变，
        # 不然 140% 时字显得特别小、70% 时又糊成一团
        ws = wheel_scale_of(self.cfg)

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        if n == 0:
            p.setPen(QPen(QColor(110, 118, 134, 190), 2.0, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
            p.end()
            return

        font = QFont(UI_FONT)
        font.setPointSizeF(max(6.0, 9.0 * ws))
        font.setWeight(QFont.DemiBold)
        p.setFont(font)
        fm = QFontMetrics(font)

        # 几何没变就复用上一帧的路径
        key = (n, round(radius, 2), round(cx, 2), round(cy, 2))
        if key != self._paths_key or len(self._paths) != n:
            self._paths = [
                ring_sector_path(cx, cy, *self.slot_geom(k, n)) for k in range(n)
            ]
            self._paths_key = key

        sel_own: dict = {}     # 当前瞄准那套轮盘的颜色（给中心圆和光标用）
        for k, (wid, name, color) in enumerate(self.entries):
            r0, r1, start_deg, span = self.slot_geom(k, n)
            path = self._paths[k]
            is_sel = k == self.selected
            is_cur = wid == self.current
            own = self._entry_paint(color)
            if is_sel:
                # 瞄准这套时点亮的颜色 = 这套轮盘自己的颜色；
                # 没单独设过颜色才跟随应用主题色
                sel_own = own
                fill = own.get("fill") or accent(238)
                border = own.get("line") or accent_light(255)
            elif is_cur:
                fill = QColor(30, 34, 43, int(225 * opacity))
                border = own.get("base") if own else accent(180)
            else:
                fill = QColor(22, 24, 31, int(215 * opacity))
                border = QColor(122, 128, 142, 200)
            p.setBrush(fill)
            p.setPen(QPen(border, 2.0 if (is_sel or is_cur) else 1.2))
            p.drawPath(path)

            # 文字：放在扇区中线
            tr = (r0 + r1) / 2.0
            tangent_w = 2.0 * tr * math.sin(math.radians(span / 2.0)) * 0.92
            rad = math.radians(start_deg - span / 2.0)
            tx = cx + tr * math.cos(rad)
            ty = cy - tr * math.sin(rad)
            edge = min(tx - (cx - radius + 8.0 * ws), (cx + radius - 8.0 * ws) - tx)
            label_w = max(28.0 * ws, min(tangent_w, max(0.0, edge) * 2.0))
            text = fm.elidedText(name, Qt.ElideRight, int(label_w))
            if is_sel:
                text_color = own.get("text") if own else (
                    QColor(16, 18, 24, 250) if theme.is_light(theme.ACCENT_RGB)
                    else QColor(246, 250, 255, 250)
                )
            else:
                text_color = QColor(214, 218, 228, 240)
            p.setPen(QPen(text_color))
            p.drawText(QRectF(tx - label_w / 2.0, ty - 10 * ws, label_w, 20 * ws),
                       Qt.AlignCenter, text)

        # 中心圆
        p.setBrush(QColor(22, 24, 31, int(215 * opacity)))
        p.setPen(QPen(QColor(122, 128, 142, 200), 1.2 * ws))
        p.drawEllipse(QRectF(cx - inner, cy - inner, inner * 2, inner * 2))

        f1 = QFont(UI_FONT)
        f1.setPointSizeF(max(6.0, 9.0 * ws))
        p.setFont(f1)
        fm1 = QFontMetrics(f1)
        if self.selected is None:
            main = "移到某套轮盘"
            sub = "松开切换"
            main_color = QColor(226, 230, 238, 245)
        else:
            main = fm1.elidedText(self.entries[self.selected][1], Qt.ElideRight,
                                  int(inner * 1.6))
            sub = "当前这套" if self.entries[self.selected][0] == self.current else "松开切换"
            # 中心文字跟着瞄中的那套走：深色内圆上用它提亮过的那一档，保证看得清
            main_color = sel_own.get("light") or QColor(226, 230, 238, 245)
        p.setPen(QPen(main_color))
        p.drawText(QRectF(cx - inner, cy - 20 * ws, inner * 2, 20 * ws), Qt.AlignCenter, main)
        f2 = QFont(UI_FONT)
        f2.setPointSizeF(max(5.5, 8.0 * ws))
        p.setFont(f2)
        p.setPen(QPen(QColor(152, 158, 172, 225)))
        p.drawText(QRectF(cx - inner, cy + 4 * ws, inner * 2, 18 * ws), Qt.AlignCenter, sub)

        # 虚拟光标：白心 + 瞄中那套的深色描边（没瞄中就是主题色）
        dotx, doty = cx + self.vx, cy + self.vy
        if self.selected is not None:
            p.setBrush(QColor(234, 255, 243, 255))
            p.setPen(QPen(sel_own["dark"] if sel_own else accent_dark(255), 2.0 * ws))
        else:
            p.setBrush(QColor(210, 214, 224, 235))
            p.setPen(QPen(QColor(255, 255, 255, 235), 2.0 * ws))
        p.drawEllipse(QPointF(dotx, doty), 6.0 * ws, 6.0 * ws)
        p.end()


class WheelSwitchController(QObject):
    """显示/隐藏"切换轮盘的轮盘"，并把选择结果落到配置上。"""

    def __init__(self, cfg: dict, scfg, raw: RawMouse) -> None:
        super().__init__()
        self.cfg = cfg
        self.scfg = scfg
        self.raw = raw
        self.active = False
        self.selected: int | None = None
        self.vx = 0.0
        self.vy = 0.0
        self.widget = WheelSwitchWidget(cfg)
        self._center = (0, 0)
        self._synced = False

    # ---- 数据 ----
    def entries(self) -> list[tuple[str, str, str]]:
        if self.scfg is None:
            return []
        return [(w.wid, w.name or w.wid, w.color or "") for w in self.scfg.wheels]

    def reload_entries(self) -> None:
        self.widget.set_entries(self.entries(), self.scfg.current if self.scfg else "")

    # ---- 显示 ----
    def show_wheel(self) -> None:
        if self.active:
            return
        self.reload_entries()
        if not self.widget.entries:
            # 这套轮盘一格都没有：以前是静默返回，用户只看到"按了没反应"。
            # 至少留一行日志，排查时能看出是这里挡住的。
            _log("[wheel] 当前这套轮盘是空的，不弹出")
            return
        self.active = True
        self.selected = None
        self.vx = self.vy = 0.0
        self.raw.drop()

        radius = self.widget.radius()
        size = int(radius * 2 + 40)
        size += size % 2
        half = size // 2

        sx, sy = cursor_pos()
        screen = QApplication.screenAt(QPoint(sx, sy)) or QApplication.primaryScreen()
        geo = screen.geometry() if screen else QRectF(0, 0, 1920, 1080).toRect()
        if str(self.cfg.get("wheel_anchor", "screen")).lower() == "cursor":
            ccx, ccy = sx, sy
        else:
            ccx, ccy = geo.center().x(), geo.center().y()
        ccx = min(max(ccx, geo.left() + half), geo.right() - half)
        ccy = min(max(ccy, geo.top() + half), geo.bottom() - half)
        self._center = (ccx, ccy)

        self.widget.setGeometry(ccx - half, ccy - half, size, size)
        self.widget.vx = self.widget.vy = 0.0
        self.widget.selected = None
        self.widget.raw_ok = self.raw.registered
        self.widget.apply_style()
        self.widget.show()
        self.widget.raise_()
        self.widget.update()
        if DEBUG:
            _log(f"[switch] 显示于 {ccx},{ccy} 共 {len(self.widget.entries)} 套")

    def hide_wheel(self) -> None:
        self.active = False
        self.widget.hide()
        self.selected = None

    def poll_selection(self) -> None:
        if not self.active:
            return
        cfg = self.cfg
        dx, dy = self.raw.take()
        if abs(dx) + abs(dy) > float(cfg.get("noise_floor", 2)):
            sens = float(cfg.get("sensitivity", 0.85))
            self.vx += dx * sens
            self.vy += dy * sens
            self.vx, self.vy = clamp_offset(
                self.vx, self.vy, self.widget.radius() * float(cfg.get("max_offset_ratio", 0.9))
            )
            self.widget.vx, self.widget.vy = self.vx, self.vy
        else:
            dx = dy = 0.0

        n = len(self.widget.entries)
        # 中心区判定跟着画出来的中空圆走（不再是固定 24px 死区）
        idx = sector_from_delta(self.vx, self.vy, n, self.widget.hole_radius())
        # 只要光标动了就重画，别等"跨过扇区"才画一次：
        # 之前那样光标在同一个扇区里移动时画面是冻住的，跨线才跳一下，
        # 用手推的时候就是一顿一顿的。主轮盘一直是"动了就画"，两边现在一致了。
        if idx != self.selected or self.widget.selected != idx or dx or dy:
            self.selected = idx
            self.widget.selected = idx
            self.widget.update()

    def commit(self) -> str:
        """松手：返回选中的轮盘 id（没选到返回空字符串）。"""
        # 以 widget 上的选中为准：绘制和判定都作用在它上面，
        # 控制器那份只是给 tick 用的镜像，两边偶尔会差一帧。
        k = self.widget.selected
        self.hide_wheel()
        if k is None or not (0 <= k < len(self.widget.entries)):
            return ""
        return self.widget.entries[k][0]


# ---------------------------------------------------------------- 轮盘控制

class PauseToast(QWidget):
    """暂停 / 恢复时在屏幕中间闪一下的小提示。

    播完就消失，不会在屏幕上留常驻标识（用户要的是"只放动画不留痕迹"）。
    和轮盘一样是置顶 + 整窗鼠标穿透 + 不抢焦点，绝不会挡住游戏里的操作。

    为什么要给这个提示：进入暂停后所有快捷键都不响应，屏幕上什么都不提示的话，
    用户只会觉得"程序卡死了"，然后去任务管理器把它杀掉。
    """

    STYLE_MS = 950

    def __init__(self, cfg: dict) -> None:
        super().__init__(
            None,
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.cfg = cfg
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedSize(306, 108)
        self.paused = True
        self.t = 0.0
        self._anim: QVariantAnimation | None = None

    def apply_style(self) -> None:
        try:
            hwnd = int(self.winId())
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception as exc:
            _log(f"[pause] 设置提示窗样式失败: {exc}")

    def flash(self, paused: bool) -> None:
        """播一次提示。动画关掉时直接不闪——
        这种提示的全部信息都在动画里，没动画就只剩一个突然出现的方块。"""
        self.paused = bool(paused)
        if not bool(self.cfg.get("animations", True)):
            self.hide()
            return
        sx, sy = cursor_pos()
        screen = QApplication.screenAt(QPoint(sx, sy)) or QApplication.primaryScreen()
        geo = screen.geometry() if screen else None
        if geo is not None:
            x = geo.center().x() - self.width() // 2
            # 屏幕自上往下 3/4 的位置：正中间是玩家盯得最紧的区域（准星附近），
            # 之前画在正中偏上，一暂停就像被人贴了张膏药。挪到下面这条"视线边缘"，
            # 余光能看见，又不压住任何要害。
            y = geo.top() + int(geo.height() * 0.75) - self.height() // 2
            self.setGeometry(x, y, self.width(), self.height())

        if self._anim is not None:
            self._anim.stop()
        self.apply_style()
        self.t = 0.0
        self.show()
        self.raise_()

        a = QVariantAnimation(self)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setDuration(self.STYLE_MS)
        a.setEasingCurve(QEasingCurve.Linear)
        a.valueChanged.connect(self._on_tick)
        a.finished.connect(self.hide)
        self._anim = a
        a.start()

    def _on_tick(self, v) -> None:
        self.t = float(v)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        t = max(0.0, min(1.0, self.t))
        # 三段：0~0.16 冒出来，0.16~0.72 停住，0.72~1 淡出
        if t < 0.16:
            k = t / 0.16
            appear = 1.0 - (1.0 - k) ** 3          # 快起慢收
            alpha = k
            rise = (1.0 - appear) * 10.0
        elif t > 0.72:
            k = (t - 0.72) / 0.28
            appear = 1.0
            alpha = 1.0 - k
            rise = k * 6.0
        else:
            appear = 1.0
            alpha = 1.0
            rise = 0.0
        if alpha <= 0.003:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        # 和轮盘同款透明度：轮盘「不透明度」调到多少，这条提示就透到多少。
        # 以前这里恒定 240/255，设成 40% 也只是轮盘半透明、提示照样一块实心板。
        ui_opacity = float(self.cfg.get("opacity", 0.94) or 0.94)
        p.setOpacity(max(0.05, min(1.0, alpha * ui_opacity)))

        cx, cy = self.width() / 2.0, self.height() / 2.0
        scale = 0.90 + 0.10 * appear
        p.translate(cx, cy + rise)
        p.scale(scale, scale)
        p.translate(-cx, -cy)

        # ---- 胶囊底板 ----
        pill = QRectF(10, 30, self.width() - 20, 52)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawRoundedRect(pill.adjusted(-1, 3, 1, 4), 26, 26)
        p.setBrush(QColor(18, 20, 26, 240))
        p.setPen(QPen(accent(210), 1.6))
        p.drawRoundedRect(pill, 26, 26)

        # ---- 图标 ----
        ix = pill.left() + 27
        iy = pill.center().y()
        if self.paused:
            p.setPen(Qt.NoPen)
            p.setBrush(accent(245))
            p.drawRoundedRect(QRectF(ix - 6, iy - 9, 4.6, 18), 2.0, 2.0)
            p.drawRoundedRect(QRectF(ix + 1.4, iy - 9, 4.6, 18), 2.0, 2.0)
        else:
            p.setBrush(accent(245))
            p.setPen(Qt.NoPen)
            tri = QPolygonF([
                QPointF(ix - 5, iy - 9),
                QPointF(ix - 5, iy + 9),
                QPointF(ix + 8, iy),
            ])
            p.drawPolygon(tri)

        # ---- 文字 ----
        f = QFont(UI_FONT)
        f.setPointSize(12)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QPen(QColor(238, 242, 248, 250)))
        title = "已暂停" if self.paused else "已恢复"
        p.drawText(
            QRectF(pill.left() + 48, pill.top() + 6, pill.width() - 60, 24),
            Qt.AlignLeft | Qt.AlignVCenter,
            title,
        )

        f2 = QFont(UI_FONT)
        f2.setPointSize(9)
        p.setFont(f2)
        p.setPen(QPen(QColor(150, 158, 172, 240)))
        hint = "快捷键暂时失效，长按轮盘键可恢复" if self.paused else "快捷键可以用了"
        p.drawText(
            QRectF(pill.left() + 48, pill.top() + 26, pill.width() - 58, 20),
            Qt.AlignLeft | Qt.AlignVCenter,
            hint,
        )
        p.end()


class WheelController(QObject):
    """负责显示/隐藏、虚拟光标推进、选中判定。"""

    def __init__(self, cfg: dict, bank: SoundBank, raw: RawMouse,
                 audio: AudioEngine | None = None) -> None:
        super().__init__()
        self.cfg = cfg
        self.bank = bank
        self.raw = raw
        self.audio = audio
        self.active = False
        self.selected: int | None = None
        self.vx = 0.0
        self.vy = 0.0
        self._center = (0, 0)
        self.widget = WheelWidget(cfg)
        self.widget.bank = bank

    def refresh_theme(self) -> None:
        """按当前那套轮盘的颜色更新绘制色（空 = 跟随应用主题色）。"""
        color = ""
        scfg = getattr(self.bank, "scfg", None)
        if scfg is not None:
            try:
                color = scfg.wheel_color()
            except Exception:
                color = ""
        self.widget.accent_rgb = color or None

    def show_wheel(self) -> None:
        if self.active:
            return
        self.refresh_theme()
        self.active = True
        self.selected = None
        self.vx = self.vy = 0.0
        self.raw.drop()  # 丢掉打开前的残余位移，保证从正中起步

        # 外圈出现后轮盘变大，窗口尺寸按"最外缘"算，不是按内圈半径
        extent = ring_layout(
            self.cfg, len(self.bank), wheel_scale_of(self.cfg)
        )["extent"]
        size = int(extent * 2 + 48)
        size += size % 2  # 边长取偶数：奇数时绘制中心会落在半像素上，导致轻微偏移
        half = size // 2

        sx, sy = cursor_pos()
        screen = QApplication.screenAt(QPoint(sx, sy)) or QApplication.primaryScreen()
        geo = screen.geometry() if screen else QRectF(0, 0, 1920, 1080).toRect()

        # 默认固定在屏幕正中：轮盘弹出位置与"鼠标停在哪"完全解耦。
        # v0.2 用的是光标位置，游戏里光标被限制在别处时会弹到屏幕边上。
        if str(self.cfg.get("wheel_anchor", "screen")).lower() == "cursor":
            ccx, ccy = sx, sy
        else:
            ccx, ccy = geo.center().x(), geo.center().y()

        # 中心夹到屏幕内，但无论夹到哪儿，判定基准都用这个点，绝不错位
        ccx = min(max(ccx, geo.left() + half), geo.right() - half)
        ccy = min(max(ccy, geo.top() + half), geo.bottom() - half)
        self._center = (ccx, ccy)

        # 坐标取整，避免 GUI 缩放不是 100% 时窗口中心与整数坐标差半像素
        self.widget.setGeometry(ccx - half, ccy - half, size, size)
        self.widget.vx = 0.0
        self.widget.vy = 0.0
        self.widget.selected = None
        self.widget.raw_ok = self.raw.registered
        # 打开那一刻就同步"有没有声音在响"，中空区域的提示文案才不会说反
        self.widget.playing = bool(self.audio.playing) if self.audio else False
        self.widget.apply_style()
        # 先把动画状态摆好再 show：否则第一帧会以"完整大小"闪一下再缩小重来
        self.widget.play_open_anim()
        self.widget.show()
        self.widget.raise_()
        self.widget.update()
        if DEBUG:
            _log(f"[wheel] 显示于 {ccx},{ccy} window={self.widget.geometry()}")

    def hide_wheel(self, animate: bool = True, keep_flash: bool = False) -> None:
        """收起轮盘。

        animate=True 先播一段动画再真正隐藏：
          · keep_flash=True（选中了音效松手）→ 整盘立刻消失，只留那一格涨大淡出
          · keep_flash=False（取消 / 切换轮盘）→ 整盘一起涨大淡出
        active 立刻置 False：动画期间输入逻辑认为轮盘已经关了，
        否则那零点二秒里继续读鼠标会误判选中。
        """
        self.active = False
        self.selected = None
        if not keep_flash:
            self.widget.selected = None
        if not self.widget.isVisible():
            return
        if animate and keep_flash and self.widget.selected is not None:
            self.widget.play_flash_anim(self.widget.hide)
        elif animate:
            self.widget.play_close_anim(self.widget.hide)
        else:
            self.widget.stop_anims()
            self.widget.hide()

    def poll_selection(self) -> None:
        if not self.active:
            return

        cfg = self.cfg
        dx, dy = self.raw.take()
        omap = outer_index_map_of(self.bank)
        # 整体大小：绘制、限位、判定三处必须吃同一个缩放，否则又会"看着大、选着小"
        ws = wheel_scale_of(cfg)
        # 噪声门限：玩家手搭在鼠标上时，静止状态也会持续报 1~2 mickey 的微动，
        # 不滤掉的话虚拟光标会缓慢自己漂到别的扇区去。
        if abs(dx) + abs(dy) > float(cfg.get("noise_floor", 2)):
            sens = float(cfg.get("sensitivity", 0.85))
            prev = (self.vx, self.vy)      # 墙在哪儿要看上一帧站的位置
            self.vx += dx * sens
            self.vy += dy * sens
            limit = ring_layout(cfg, len(self.bank), ws)["extent"] * float(
                cfg.get("max_offset_ratio", 0.9)
            )
            self.vx, self.vy = clamp_offset(self.vx, self.vy, limit)
            # 外圈有空位时不能把光标推进空白格，也不许跨过空白去够远处的格子
            self.vx, self.vy = clamp_to_filled(
                self.vx, self.vy, cfg, len(self.bank), ws,
                outer_map=omap, prev=prev
            )
            self.widget.vx = self.vx
            self.widget.vy = self.vy
        else:
            dx = dy = 0.0

        idx = index_from_delta(
            self.vx, self.vy, len(self.bank), 0.0, cfg, ws,
            outer_map=omap,
        )

        # 中空区域的提示要区分"取消"和"停止播放"，先同步一下现在有没有声音在响
        if self.audio is not None:
            playing = self.audio.playing
            if playing != self.widget.playing:
                self.widget.playing = playing
                self.widget.update()   # 文案变了，让它重画

        if idx != self.selected or self.widget.selected != idx or dx or dy:
            if DEBUG and idx != self.selected:
                _log(f"[select] {idx} v=({self.vx:.0f},{self.vy:.0f})")
            self.selected = idx
            self.widget.selected = idx
            self.widget.update()

    def commit(self) -> int | None:
        idx = self.selected
        # 选中了就把那一格留着高亮播释放动画；空手松手就正常收起
        self.hide_wheel(keep_flash=idx is not None)
        return idx


# ---------------------------------------------------------------- 输入轮询

def settings_blocks_hotkey(win) -> bool:
    """设置窗口是不是正"占着键盘"（占了就先别响应热键）。

    以前判的是「窗口可见」。可程序默认启动就打开设置窗口
    （open_settings_on_start 默认 True），用户切到游戏后那个窗口仍留在后台
    "可见"，热键就被永久判定成暂停 —— 表现就是轮盘怎么按都不出来。
    现在只认「窗口在前台且没最小化」：切到游戏，它自动让路。
    """
    if win is None:
        return False
    try:
        return (
            bool(win.isVisible())
            and not win.isMinimized()
            and bool(win.isActiveWindow())
        )
    except RuntimeError:          # 窗口对象已经被销毁
        return False


class InputPoller(QObject):
    """GetAsyncKeyState 轮询。全程无钩子，不阻断游戏输入。"""

    def __init__(self, cfg: dict, wheel: WheelController, audio: AudioEngine,
                 switcher: "WheelSwitchController | None" = None) -> None:
        super().__init__()
        self.cfg = cfg
        self.wheel = wheel
        self.audio = audio
        self.switcher = switcher
        # 切换轮盘的那个键：单独一套按下/松手状态，和主热键互不干扰
        self._sw_prev = False
        self._sw_at = 0.0
        # 用户选中了另一套轮盘时调这里（由主程序接上"真的去切"）
        self.on_switch_wheel: object = None
        self.hotkey_name = norm_spec(cfg["hotkey"]) or "y"
        self.vk = vk_of(self.hotkey_name)
        self._prev = False
        self._press_at = 0.0
        self._held_to_wheel = False   # 这次按住有没有弹出过轮盘（区分长按/轻按）
        # 这次按住已经被鼠标键取消过了：松手前不许再弹出来
        self._canceled = False
        # 左/右键的上一帧状态：只在"刚按下"那一下取消，按住不放不会反复触发
        self._mouse_prev = {m: False for m in WHEEL_CANCEL_KEYS}
        self._timer = QTimer()
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(max(4, int(cfg.get("poll_ms", 8))))
        self._timer.timeout.connect(self.tick)
        self._extra: list[tuple[int, object]] = []
        self._extra_prev: dict[int, bool] = {}
        # 返回 True 时暂停响应按键（配置窗口打开时用，免得打字把轮盘弹出来）
        self.paused: object = None
        # 用户自己按出来的暂停（轮盘中心松手）。和上面那个"设置窗口占着键盘"
        # 的临时让路是两回事：这个必须用户再操作一次才会解除。
        self.user_paused = False
        # 暂停状态变了通知外面（主程序用它播暂停/恢复动画）
        self.on_pause_changed: object = None
        self.rebuild_bindings()

    def run_tap_action(self) -> bool:
        """轻按热键时执行的动作（长按才是弹轮盘）。"""
        action = str(self.cfg.get("tap_action", "none") or "none").lower()
        if action == "repeat_last":
            return self.audio.play_repeat_last()
        if action == "next":
            return self.audio.play_next()
        return False

    def set_user_pause(self, on: bool) -> None:
        """进入/退出用户暂停。

        暂停期间只挡"轻按动作"和额外快捷键，**轮盘本身照常能长按打开**。
        这是故意留的活路：如果连轮盘都挡住，用户被自己暂停了就再也没办法
        用键盘解除，只能去托盘右键退出程序。
        """
        on = bool(on)
        if on == self.user_paused:
            return
        self.user_paused = on
        _log(f"[pause] {'暂停' if on else '恢复'}")
        if callable(self.on_pause_changed):
            self.on_pause_changed(on)

    def _tick_switch(self) -> None:
        """按住"切换轮盘的键"弹出小轮盘，划到哪套松手就切过去。

        和主热键同一套手感：要按满 hold_ms 才弹，轻点一下不会弹
        （这个键没有"轻按动作"，误触比漏触更烦人）。
        """
        sw = self.switcher
        key = norm_spec(self.cfg.get("switch_key", ""))
        if sw is None or not key or key == self.hotkey_name:
            self._sw_prev = False
            return
        if self.user_paused or (self.paused is not None and self.paused()):
            self._sw_prev = self._down(key)
            self._sw_at = time.monotonic()
            return

        down = self._down(key)
        now = time.monotonic()
        if down and not self._sw_prev:
            self._sw_at = now
        elif down and not sw.active:
            if (now - self._sw_at) * 1000.0 >= float(self.cfg["hold_ms"]):
                if self.wheel.active:
                    self.wheel.hide_wheel()   # 主轮盘开着就先关掉，一次只显示一个
                sw.show_wheel()
        elif not down and self._sw_prev and sw.active:
            wid = sw.commit()
            if wid and callable(self.on_switch_wheel):
                self.on_switch_wheel(wid)
        self._sw_prev = down

        if sw.active:
            sw.poll_selection()

    def set_hotkey(self, name: str) -> None:
        """换呼出键。键盘、鼠标、组合键都支持。"""
        self.hotkey_name = norm_spec(name) or "y"
        self.vk = vk_of(self.hotkey_name)
        self._prev = self._down(self.hotkey_name)
        self._press_at = time.monotonic()

    def _down(self, name: str) -> bool:
        """这个绑定现在是不是按着。

        支持单键（"y" / "mouse_4"）和组合键（"ctrl+shift+y"）：
        组合键要求每一部分同时按着才算，少一个都不行。
        """
        parts = spec_parts(name)
        if not parts:
            return False
        raw = getattr(self.wheel, "raw", None)
        raw_ok = raw is not None and getattr(raw, "registered", False)
        for p in parts:
            if p in MOUSE_KEYS and raw_ok:
                if not raw.button_down(p):
                    return False
            elif not is_down(vk_of(p)):
                return False
        return True

    def rebuild_bindings(self) -> None:
        """重建"额外快捷键"绑定。改了快捷键或增删音效后调用一次。

        绑定存的是**按键名**（"y" / "f1" / "mouse_4"），不是虚拟键码，
        这样鼠标按键和键盘按键能用同一套逻辑，也不会出现两个不同的键
        映射到同一个码时互相顶掉。
        """
        bindings: list[tuple[str, object]] = []
        seen: set[str] = {norm_spec(self.cfg.get("hotkey", "y"))}

        rk = norm_spec(self.cfg.get("repeat_last_key", ""))
        if rk and rk not in seen:
            bindings.append((rk, self.audio.play_repeat_last))
            seen.add(rk)

        ck = norm_spec(self.cfg.get("cycle_key", ""))
        if ck and ck not in seen:
            bindings.append((ck, self.audio.play_next))
            seen.add(ck)

        sk = norm_spec(self.cfg.get("switch_key", ""))
        if sk:
            seen.add(sk)      # 切换轮盘的键不参与"播放音效"绑定，这里只是占位防冲突

        scfg = getattr(self.audio.bank, "scfg", None)
        if scfg is not None:
            for key, name in scfg.hotkey_map().items():
                key = norm_spec(key)
                if not key or key in seen:
                    continue
                bindings.append((key, lambda n=name: self.audio.play_named(n)))
                seen.add(key)

        self._extra = bindings
        # 记下当前状态，避免刚绑定就立刻误触发
        self._extra_prev = {k: self._down(k) for k, _a in bindings}

    def start(self) -> None:
        self._timer.start()

    def tick(self) -> None:
        # 鼠标左右键的"刚按下"检测每帧都要跑：暂停期间也要跟上状态，
        # 否则恢复时第一次点击会被当成新按下
        mouse_pressed = False
        for name in WHEEL_CANCEL_KEYS:
            d = self._down(name)
            if d and not self._mouse_prev.get(name, False):
                mouse_pressed = True
            self._mouse_prev[name] = d

        if self.paused is not None and self.paused():
            # 暂停期间同步状态，恢复时不会把"暂停前按住"当成新按下
            self._prev = self._down(self.hotkey_name)
            self._press_at = time.monotonic()
            for key, _a in self._extra:
                self._extra_prev[key] = self._down(key)
            # 轮盘正弹着的时候切到设置窗口：先把它收掉。
            # 这里每帧会直接 return，不收的话轮盘会一直挂在屏幕上下不来。
            if self.wheel.active:
                self.wheel.hide_wheel()
                self._held_to_wheel = True
            return

        down = self._down(self.hotkey_name)
        now = time.monotonic()

        if down and not self._prev:
            self._press_at = now
            self._held_to_wheel = False
            self._canceled = False        # 新的一次按住：清掉上次的取消标记
        elif down and not self.wheel.active and not self._canceled:
            if (now - self._press_at) * 1000.0 >= float(self.cfg["hold_ms"]):
                if DEBUG:
                    _log("[tick] 触发轮盘")
                self.wheel.show_wheel()
                self._held_to_wheel = True
        elif not down and self._prev:
            if self.wheel.active:
                self._held_to_wheel = True
                idx = self.wheel.commit()
                if idx is not None:
                    if DEBUG:
                        _log(f"[play] {idx}")
                    self.audio.play(idx)
                    # 选了音效 = 本来就在干活，顺手退出暂停
                    if self.user_paused:
                        self.set_user_pause(False)
                else:
                    # 指回中空区域松手：先掐掉正在响的声音，再切换暂停状态。
                    # 同一个动作既进也出：暂停中再做一次就是恢复，
                    # 这是用户能把自己救出来的两条路之一（另一条是选音效）。
                    if DEBUG:
                        _log("[stop] 中空区域松手，停止播放")
                    self.audio.stop_all()
                    self.set_user_pause(not self.user_paused)
            elif not self._held_to_wheel:
                # 轻按热键：没长到弹轮盘，就执行配置的"轻按动作"。
                # 暂停期间这一下要挡掉，否则暂停就名不副实了。
                if not self.user_paused:
                    self.run_tap_action()
        self._prev = down

        # 轮盘弹着的时候按鼠标左键/右键 = 立刻取消这次呼出。
        # 只是取消，不播任何东西、也不掐正在响的声音（那是指回中空松手的事）。
        if mouse_pressed and self.wheel.active:
            if DEBUG:
                _log("[wheel] 鼠标键取消呼出")
            self.wheel.hide_wheel()
            self._held_to_wheel = True    # 松手时别再走"轻按动作"
            self._canceled = True         # 松手前不再弹出来

        if self.wheel.active:
            self.wheel.poll_selection()

        self._tick_switch()

        # 额外快捷键：只在"按下的那一下"触发，按住不会连发
        for key, action in self._extra:
            d = self._down(key)
            if d and not self._extra_prev.get(key, False) and not self.user_paused:
                action()
            self._extra_prev[key] = d


# ---------------------------------------------------------------- 托盘

def make_icon() -> QIcon:
    """与 exe 图标保持一致：特征色圆环 + 深色内圆 + 播放三角。"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setBrush(accent(255))
    p.setPen(QPen(accent_light(255), 6))
    p.drawEllipse(QRectF(6, 6, 52, 52))
    p.setBrush(QColor(20, 22, 28, 255))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QRectF(21, 21, 22, 22))
    p.setBrush(accent_light(255))
    tri = QPolygonF([
        QPointF(28, 26.5),
        QPointF(28, 37.5),
        QPointF(38, 32),
    ])
    p.drawPolygon(tri)
    p.end()
    return QIcon(pm)


# ---------------------------------------------------------------- 主程序

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.restype = wintypes.HANDLE
_MUTEX = None


def acquire_single_instance() -> bool:
    """只允许开一个实例。否则双击两次会有两个进程同时读键，音效播两遍。"""
    global _MUTEX
    _MUTEX = _kernel32.CreateMutexW(None, False, "Local\\SRVoiceoverRoulette")
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def main() -> int:
    if not acquire_single_instance():
        ctypes.windll.user32.MessageBoxW(
            None,
            "SR Voiceover Roulette 已经在运行了（看右下角托盘里那个带播放三角的圆环图标）。",
            APP_NAME,
            0x40,
        )
        return 0

    def _excepthook(exc_type, exc, tb) -> None:
        import traceback

        _log("".join(traceback.format_exception(exc_type, exc, tb)))

    sys.excepthook = _excepthook

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    cfg = load_config()
    save_config(cfg)
    sync_autostart(cfg)   # exe 挪过位置时顺手把注册表里的路径更新掉
    set_accent(str(cfg.get("accent_color") or theme.DEF_ACCENT))

    raw = RawMouse()
    raw_ok = raw.start(app)

    scfg = SoundsConfig(SOUNDS_CONFIG_PATH)
    scfg.load()

    bank = SoundBank(MAX_SLOTS, scfg)   # 内 8 + 外 12，上限写死在 sounds_config
    # 首次运行会把磁盘上的音效全数上盘，这里立刻落盘固化，
    # 否则每次启动都当作"首次"，用户对轮盘的改动会被全量上盘盖掉
    scfg.save()
    audio = AudioEngine(bank, cfg)
    audio.start()
    # 启动后隔一会儿把组合音效预渲染进缓存（一条一条来，不卡启动）
    audio.warm_all_async(1800)

    wheel = WheelController(cfg, bank, raw, audio)
    wheel.widget.raw_ok = raw_ok
    switcher = WheelSwitchController(cfg, scfg, raw)
    poller = InputPoller(cfg, wheel, audio, switcher)
    poller.paused = lambda: settings_blocks_hotkey(_settings_holder.get("win"))

    # 用户暂停/恢复：改轮盘中心的提示文案，再在屏幕上闪一下
    pause_toast = PauseToast(cfg)

    def on_user_pause(on: bool) -> None:
        wheel.widget.paused = bool(on)
        if wheel.widget.isVisible():
            wheel.widget.update()
        pause_toast.flash(bool(on))

    poller.on_pause_changed = on_user_pause
    icon = make_icon()
    app.setWindowIcon(icon)
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip(f"{APP_NAME} {APP_VERSION}\n长按 {spec_label(cfg['hotkey'])} 打开轮盘")

    # 链路出问题直接弹气泡：设置窗口关着、人在游戏里，也能第一时间知道
    # （以前只写进设置页那行小字，用户永远看不见，还以为一切正常）
    def on_audio_problem(msg: str) -> None:
        tray.showMessage(f"{APP_NAME} · 音频", msg, QSystemTrayIcon.Warning, 8000)

    audio.problem.connect(on_audio_problem)
    # 托盘图标这会儿还没 show()，气泡会被丢掉，等主循环转起来再补报
    QTimer.singleShot(1500, audio.announce_now)

    menu = QMenu()

    _settings_holder: dict[str, object] = {"win": None}

    def switch_wheel(wid: str) -> None:
        """切到另一套轮盘：换布局、换参数、换颜色，正在响的音效不会被打断。"""
        target = scfg.wheel_by_id(wid)
        if target is None or wid == scfg.current:
            return
        name = target.name or wid
        if not scfg.switch_wheel(wid):
            return
        scfg.save()
        bank.reload()
        audio.load(stop_playing=False)
        wheel.refresh_theme()
        poller.rebuild_bindings()      # 新轮盘上的音效快捷键可能不是同一批
        win = _settings_holder.get("win")
        if win is not None and hasattr(win, "on_wheel_switched"):
            win.on_wheel_switched()
        act_count.setText(f"已加载音效：{len(audio)} 个（上限 {MAX_SLOTS}）")
        tray.showMessage(APP_NAME, f"已切换到「{name}」",
                         QSystemTrayIcon.Information, 1500)

    poller.on_switch_wheel = switch_wheel

    def open_settings() -> None:
        # 延迟导入：settings_window 反过来要 import 本模块，顶层导入会循环
        from settings_window import SettingsWindow

        win = _settings_holder.get("win")
        if win is None:
            win = SettingsWindow(cfg, scfg, bank, audio)

            def on_settings_changed() -> None:
                # 槽位顺序或数量变了：重新解码、重绑快捷键、刷新托盘
                audio.load()
                poller.set_hotkey(str(cfg["hotkey"]))
                poller.rebuild_bindings()
                set_accent(str(cfg.get("accent_color") or theme.DEF_ACCENT))
                icon = make_icon()
                app.setWindowIcon(icon)
                tray.setIcon(icon)
                act_count.setText(f"已加载音效：{len(audio)} 个（上限 {MAX_SLOTS}）")
                tray.setToolTip(
                    f"{APP_NAME} {APP_VERSION}\n长按 {spec_label(cfg['hotkey'])} 打开轮盘"
                )

            def on_params_changed() -> None:
                # 只改了某个音效的音量/变调/按键：不用重解码，重绑按键即可
                audio.reset_pitch()
                poller.set_hotkey(str(cfg["hotkey"]))
                poller.rebuild_bindings()

            def on_audio_changed() -> None:
                # 麦克风那套参数变了：只重建音频链路，音效不用重新解码
                audio.apply_audio_cfg()

            win.changed.connect(on_settings_changed)
            win.params_changed.connect(on_params_changed)
            win.audio_changed.connect(on_audio_changed)
            win.wheel_switch_requested.connect(switch_wheel)
            win.preview_requested.connect(audio.play_named)

            # 关掉设置窗口后重绑一次按键：确保轮询用的是最新的热键与音效快捷键
            def on_settings_closed() -> None:
                poller.rebuild_bindings()

            win.closed.connect(on_settings_closed)
            _settings_holder["win"] = win
        win.show()
        win.raise_()
        win.activateWindow()

    act_settings = QAction("设置…", menu)
    act_settings.triggered.connect(open_settings)
    menu.addAction(act_settings)
    menu.addSeparator()

    act_count = QAction(f"已加载音效：{len(audio)} 个（上限 {MAX_SLOTS}）", menu)
    act_count.setEnabled(False)
    menu.addAction(act_count)
    menu.addSeparator()

    act_reload = QAction("重新扫描 sounds 目录", menu)

    def do_reload() -> None:
        bank.reload()
        audio.load()
        act_count.setText(f"已加载音效：{len(audio)} 个（上限 {MAX_SLOTS}）")
        tray.showMessage(
            APP_NAME, f"已重新载入 {len(audio)} 个音效",
            QSystemTrayIcon.Information, 2500,
        )

    act_reload.triggered.connect(do_reload)
    menu.addAction(act_reload)

    act_open = QAction("打开 sounds 目录", menu)

    def do_open() -> None:
        SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(SOUNDS_DIR))  # noqa: S606

    act_open.triggered.connect(do_open)
    menu.addAction(act_open)

    menu.addSeparator()
    act_quit = QAction("退出", menu)
    act_quit.triggered.connect(app.quit)
    menu.addAction(act_quit)

    tray.setContextMenu(menu)

    def on_tray(reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            open_settings()

    tray.activated.connect(on_tray)
    tray.show()

    poller.start()

    # 带 --settings 启动就直接把配置窗口打开（方便做桌面快捷方式，也方便自检）
    # 平时也默认启动就打开配置窗口 —— 打开软件通常就是为了调轮盘摆位；
    # 嫌烦可以在「快捷键」页把"启动时自动打开"关掉。
    if "--settings" in sys.argv or bool(cfg.get("open_settings_on_start", True)):
        QTimer.singleShot(300, open_settings)

    # 打印机/耳机插拔后设备可能变化，定期看一眼要不要重建输出
    dev_watch = QTimer()
    dev_watch.setInterval(3000)
    dev_watch.timeout.connect(audio.restart_sink)
    dev_watch.start()

    if len(audio) == 0:
        tray.showMessage(
            APP_NAME,
            "sounds 目录里还没有可用音效。放几个 wav/mp3 进去，再点托盘菜单的「重新扫描」。",
            QSystemTrayIcon.Warning, 6000,
        )
    else:
        tray.showMessage(
            APP_NAME,
            f"已就绪，长按 {spec_label(cfg['hotkey'])} 打开轮盘（{len(audio)} 个音效）",
            QSystemTrayIcon.Information, 3000,
        )

    if not raw_ok:
        tray.showMessage(
            APP_NAME,
            "鼠标原始输入注册失败，轮盘将无法选择音效。详情见 sr_roulette.log。",
            QSystemTrayIcon.Critical, 8000,
        )

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
