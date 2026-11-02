"""配色单一来源。

两层配色，互不干扰：
  1. **应用主题色** —— 托盘图标、设置界面的高亮/滑块/选中态用它。
     由 set_accent() 设置，可以是任意 RGB，不再局限于下面那几个预设。
  2. **轮盘颜色** —— 每套轮盘各自一个颜色（存在 sounds.json 里）。
     画轮盘时用 push_accent()/pop_accent() 临时盖住主题色，
     画完自动还原，所以轮盘和界面可以不同色。

推导规则：给一个主色，自动算出「高亮描边」和「深色描边」两个配套色，
用户只挑一个颜色就够，不用自己配三档。
"""

from PySide6.QtGui import QColor

# 预设色：只是取色面板上的快捷入口，不再是唯一可选的四档
PALETTES: dict[str, tuple[int, int, int]] = {
    "green": (46, 211, 108),
    "orange": (255, 122, 69),
    "blue": (58, 160, 255),
    "purple": (168, 120, 255),
}

PALETTE_LABELS = {
    "green": "绿",
    "orange": "橙",
    "blue": "蓝",
    "purple": "紫",
}

DEF_ACCENT = PALETTES["green"]

ACCENT_RGB = DEF_ACCENT          # 主特征色：选中扇区填充
ACCENT_LIGHT_RGB = (186, 248, 210)   # 高亮描边 / 图标内圈 / 光标光晕
ACCENT_DARK_RGB = (20, 128, 62)      # 深色描边：光标选中态的圈线

# 画轮盘期间压在上面的临时颜色栈（空 = 用主题色）
_OVERRIDE: list[tuple[int, int, int]] = []


# ---------------------------------------------------------------- 颜色换算

def _clamp8(v: float) -> int:
    return int(max(0, min(255, round(v))))


def derive(rgb: tuple[int, int, int]) -> tuple[tuple[int, int, int], ...]:
    """由一个主色推出 (主色, 高亮色, 深色色)。

    高亮：往白色混 62%（不是简单加法，暗色也能提亮）；
    深色：往黑色压 42%，保证在深色背景上还看得出是同一个颜色。
    """
    r, g, b = (_clamp8(x) for x in rgb)
    light = tuple(_clamp8(c + (255 - c) * 0.62) for c in (r, g, b))
    dark = tuple(_clamp8(c * 0.58) for c in (r, g, b))
    return (r, g, b), light, dark


def parse_rgb(value) -> tuple[int, int, int] | None:
    """严格解析颜色：读不出来就返回 None。

    和 hex_to_rgb 的区别是**不兜底**——用来区分"用户没给这套轮盘设颜色"
    和"设了一个等于默认值的颜色"，前者要跟随主题色，后者要按自己的来。
    """
    s = str(value or "").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        return None
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return None


def hex_to_rgb(value: str, default: tuple[int, int, int] | None = None) -> tuple[int, int, int]:
    """'#2ed36c' / '2ed36c' / '#2ed' 都能读，读不出来给默认值。"""
    rgb = parse_rgb(value)
    if rgb is not None:
        return rgb
    return default if default is not None else DEF_ACCENT


def is_light(rgb, threshold: float = 150.0) -> bool:
    """这个颜色够不够亮——亮底上要压深色字，暗底上要放浅色字。"""
    r, g, b = (float(x) for x in rgb[:3])
    return (0.299 * r + 0.587 * g + 0.114 * b) >= threshold


def rgb_to_hex(rgb) -> str:
    r, g, b = (_clamp8(x) for x in rgb)
    return "#%02x%02x%02x" % (r, g, b)


# ---------------------------------------------------------------- 主题色

def set_accent(rgb) -> None:
    """设置应用主题色。接受 RGB 三元组或 '#rrggbb' 字符串。"""
    global ACCENT_RGB, ACCENT_LIGHT_RGB, ACCENT_DARK_RGB
    if isinstance(rgb, str):
        rgb = hex_to_rgb(rgb)
    ACCENT_RGB, ACCENT_LIGHT_RGB, ACCENT_DARK_RGB = derive(tuple(rgb))


def set_palette(name: str) -> str:
    """按预设名切主题色。保留旧接口，配置里存的 accent_theme 还能用。"""
    key = str(name or "").strip()
    if key not in PALETTES:
        key = "green"
    set_accent(PALETTES[key])
    return key


def accent_hex() -> str:
    return rgb_to_hex(ACCENT_RGB)


def accent_dim_hex() -> str:
    """次级色：列表选中、拖放提示底这类"淡一档"的填充。"""
    return rgb_to_hex(tuple(c * 0.62 for c in ACCENT_RGB))


# ---------------------------------------------------------------- 绘制期覆盖

def push_accent(rgb=None) -> None:
    """画轮盘期间临时改用某个颜色。rgb 为 None 时压一份当前主题色（等于不变）。"""
    if rgb is None:
        _OVERRIDE.append(tuple(ACCENT_RGB))
    elif isinstance(rgb, str):
        _OVERRIDE.append(hex_to_rgb(rgb, tuple(ACCENT_RGB)))
    else:
        _OVERRIDE.append(tuple(int(x) for x in rgb))


def pop_accent() -> None:
    if _OVERRIDE:
        _OVERRIDE.pop()


def _current() -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    if _OVERRIDE:
        return derive(_OVERRIDE[-1])
    return ACCENT_RGB, ACCENT_LIGHT_RGB, ACCENT_DARK_RGB


def accent(alpha: int = 255) -> QColor:
    r, g, b = _current()[0]
    return QColor(r, g, b, alpha)


def accent_light(alpha: int = 255) -> QColor:
    r, g, b = _current()[1]
    return QColor(r, g, b, alpha)


def accent_dark(alpha: int = 255) -> QColor:
    r, g, b = _current()[2]
    return QColor(r, g, b, alpha)
