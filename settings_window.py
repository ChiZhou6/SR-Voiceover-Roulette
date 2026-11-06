"""配置窗口：左边多层标签页，右边可视化轮盘。

当前版本先把布局和控件位置摆好，功能逐步接上。
视觉沿用轮盘那套深色 + 特征色，和主程序保持一致。
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import (
    QMimeData,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDrag,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import sr_roulette as sr
from sounds_config import (
    CM_ACC,
    CM_RAND,
    CM_SEQ,
    CM_STEP,
    COMBO_MODE_LABEL,
    COMBO_MODE_TIP,
    COMBO_MODES,
    COMBO_PREFIX,
    ComboDef,
    ComboItem,
    DELAY_MAX_MS,
    DELAY_MIN_MS,
    MAX_COMBO_ITEMS,
    PITCH_FIXED,
    PITCH_MODE_LABEL,
    PITCH_MODES,
    PITCH_NONE,
    PITCH_RANDOM,
    REPEAT_MS_MAX,
    REPEAT_MS_MIN,
    SPEED_MODE_LABEL,
    SPEED_MODES,
    SPEED_NONE,
    TRIG_COMBO,
    TRIG_LABEL,
    TRIG_PREV_END,
    TRIGS,
    TRIGGER_HOLD,
    TRIGGER_MODE_LABEL,
    TRIGGER_MODE_TIP,
    TRIGGER_MODES,
    TRIGGER_REPEAT,
    UNLOCK_COUNT_MAX,
    UNLOCK_KEY,
    UNLOCK_MODE_LABEL,
    UNLOCK_MODES,
    UNLOCK_MS_MAX,
    is_combo_key,
)
import theme
from theme import accent, accent_dark, accent_light

UI_FONT = "Microsoft YaHei UI"

# 拖放的数据类型：从音效库拖出来 vs 轮盘内部拖动
MIME_LIB = "application/x-sr-lib"     # 数据 = 文件名
MIME_SLOT = "application/x-sr-slot"   # 数据 = 槽位号（0~7 内圈 / 8~19 外圈位置）
# 拖放落点用 -1 表示"丢到中心 = 追加到末尾"（0 及以上的整数是格子下标）
ADD_TO_END = -1

# ---------------------------------------------------------------- 样式

def accent_hex() -> str:
    """当前主题色的十六进制值。每次取值都现算，换色后才能跟着变。"""
    return theme.accent_hex()


def accent_dim() -> str:
    return theme.accent_dim_hex()


def build_qss() -> str:
    """按当前主题色生成整窗样式表。

    做成函数而不是常量：主题色可以自由调，改完重设一次样式表，
    滑块、选中态、按钮这些全都跟着换，不用一个个控件去改。
    """
    ACCENT_HEX = accent_hex()
    ACCENT_DIM = accent_dim()
    # 主题色当底色时，字用深色还是白色得看底色亮不亮（绿色底配白字几乎看不清）
    ACCENT_ON = "#0f1218" if theme.is_light(theme.ACCENT_RGB) else "#ffffff"
    ACCENT_LIGHT = theme.rgb_to_hex(theme.ACCENT_LIGHT_RGB)
    return f"""
* {{
    font-family: "{UI_FONT}";
    outline: none;
}}
QWidget#Root {{
    background: #14161b;
    border: 1px solid #262a34;
    border-radius: 12px;
}}
QWidget#TitleBar {{
    background: transparent;
    border: none;
}}
QLabel {{
    color: #e8eaf0;
    background: transparent;
}}
QLabel#AppTitle {{
    font-size: 13px;
    font-weight: 600;
    color: #f2f4f8;
}}
QLabel#AppVersion {{
    font-size: 11px;
    color: #6f7686;
}}
QLabel#Hint {{
    font-size: 11px;
    color: #767d8d;
}}
QLabel#SectionLabel {{
    font-size: 12px;
    font-weight: 600;
    color: #c8cddb;
}}
QLabel#CardTitle {{
    font-size: 13px;
    font-weight: 600;
    color: #f2f4f8;
}}

QPushButton#FoldHead {{
    text-align: left;
    background: #1a1d24;
    border: 1px solid #262a34;
    border-radius: 10px;
    padding: 9px 12px;
    font-size: 12px;
    font-weight: 600;
    color: #e8eaf0;
}}
QPushButton#FoldHead:hover {{
    background: #22262f;
    border-color: #3a4152;
}}
QPushButton#FoldHead:checked {{
    color: #ffffff;
    border-bottom-left-radius: 0px;
    border-bottom-right-radius: 0px;
}}
/* 重点那一节（常见问题）用应用主题色标出来，一眼能找到 */
QPushButton#FoldHead[hot="true"] {{
    background: {ACCENT_HEX};
    border-color: {ACCENT_HEX};
    color: {ACCENT_ON};
    font-size: 13px;
}}
QPushButton#FoldHead[hot="true"]:hover {{
    background: {ACCENT_LIGHT};
    border-color: {ACCENT_LIGHT};
    color: {ACCENT_ON};
}}
QPushButton#FoldHead[hot="true"]:checked {{
    background: {ACCENT_HEX};
    border-color: {ACCENT_HEX};
    color: {ACCENT_ON};
}}
QFrame#FoldBody[hot="true"] {{
    border-color: {ACCENT_HEX};
}}
QFrame#FoldBody {{
    background: #171a21;
    border: 1px solid #262a34;
    border-top: none;
    border-bottom-left-radius: 10px;
    border-bottom-right-radius: 10px;
}}
QLabel#DocHead {{
    font-size: 12px;
    font-weight: 600;
    color: #dfe3ec;
}}
QLabel#DocText {{
    font-size: 12px;
    color: #b6bccb;
}}

QFrame#Card {{
    background: #1a1d24;
    border: 1px solid #262a34;
    border-radius: 12px;
}}
/* ---- 首次启动那张提示卡（盖在设置窗口上的浮层） ---- */
QWidget#TipMask {{
    background: rgba(8, 10, 14, 190);
}}
QFrame#TipCard {{
    background: #1a1d24;
    border: 1px solid {ACCENT_HEX};
    border-radius: 12px;
}}
QLabel#TipTitle {{
    font-size: 15px;
    font-weight: 600;
    color: {ACCENT_HEX};
}}
QLabel#TipText {{
    font-size: 12px;
    color: #b6bccb;
}}
QFrame#Cell {{
    background: #21252e;
    border: 1px solid #2e333f;
    border-radius: 9px;
}}
QFrame#Cell:hover {{
    border: 1px solid {ACCENT_HEX};
    background: #262b35;
}}
QFrame#Divider {{
    background: #262a34;
    border: none;
    max-height: 1px;
    min-height: 1px;
}}

QTabWidget::pane {{
    border: none;
    background: transparent;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: #8b93a3;
    padding: 8px 16px;
    margin-right: 4px;
    border: none;
    border-radius: 8px;
    font-size: 12px;
}}
QTabBar::tab:hover {{
    color: #d6dae4;
    background: #1d212a;
}}
QTabBar::tab:selected {{
    color: #ffffff;
    background: {ACCENT_DIM};
}}

QPushButton {{
    background: #232830;
    color: #dfe3ec;
    border: 1px solid #313744;
    border-radius: 8px;
    padding: 6px 14px;
    font-size: 12px;
}}
QPushButton:hover {{
    background: #2b313b;
    border-color: #3d4453;
}}
QPushButton#Primary {{
    background: {ACCENT_HEX};
    color: #0d1a11;
    border: none;
    font-weight: 600;
}}
QPushButton#Primary:hover {{
    background: {ACCENT_HEX};
}}
QPushButton#WinBtn {{
    background: transparent;
    border: none;
    color: #9aa2b2;
    padding: 0px;
    border-radius: 6px;
    font-size: 14px;
}}
QPushButton#WinBtn:hover {{
    background: #262b35;
    color: #ffffff;
}}
QPushButton#KeyClear {{
    background: transparent;
    border: none;
    color: #8b93a3;
    padding: 0px;
    border-radius: 6px;
    font-size: 12px;
}}
QPushButton#KeyClear:hover {{
    background: #332026;
    color: #ff8f8f;
}}
QPushButton#KeyClear:disabled {{
    color: #3a414f;
}}

/* QDoubleSpinBox 必须单独列出来：不写它就退回系统默认的浅色样式，
   在深色表格里就是一块刺眼的白（变调那一列踩过这个坑） */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: #171a21;
    border: 1px solid #2b303b;
    border-radius: 7px;
    padding: 5px 9px;
    color: #e8eaf0;
    font-size: 12px;
    selection-background-color: {ACCENT_DIM};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {ACCENT_HEX};
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: #1a1d24;
    border: 1px solid #2b303b;
    color: #e8eaf0;
    selection-background-color: {ACCENT_DIM};
    outline: none;
}}

QSlider::groove:horizontal {{
    height: 4px;
    background: #2b303b;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT_HEX};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 13px;
    height: 13px;
    margin: -5px 0;
    border-radius: 7px;
    background: #f2f4f8;
    border: 2px solid {ACCENT_HEX};
}}

QCheckBox {{
    color: #c8cddb;
    font-size: 12px;
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid #3a414f;
    background: #171a21;
}}
QCheckBox::indicator:checked {{
    background: {ACCENT_HEX};
    border-color: {ACCENT_HEX};
}}
/* 音效卡片里「快捷键」右边那个小勾选框：那一行本来就排满了，
   用紧凑一档，免得把按键框挤扁 */
QCheckBox#GlobalChk {{
    color: #c8cddb;
    font-size: 11px;
    spacing: 4px;
}}
QCheckBox#GlobalChk::indicator {{
    width: 13px;
    height: 13px;
    border-radius: 3px;
    border: 1px solid #3a414f;
    background: #171a21;
}}
QCheckBox#GlobalChk::indicator:checked {{
    background: {ACCENT_HEX};
    border-color: {ACCENT_HEX};
}}

/* 滚动区、它的 viewport 和里面那层 holder 都必须显式透明，
   否则会露出 Qt 默认的白色底，深色界面上就是一块刺眼的白 */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollArea > QWidget {{ background: transparent; }}
/* 独立弹出的对话框不会自动继承主窗口的深底，必须显式给 */
QDialog {{
    background: #14161b;
    color: #e8eaf0;
}}
QListWidget {{
    background: #171a21;
    border: 1px solid #2b303b;
    border-radius: 7px;
    color: #e8eaf0;
    font-size: 12px;
    outline: none;
    padding: 4px;
}}
QListWidget::item {{
    padding: 5px 8px;
    border-radius: 5px;
    margin: 1px 2px;
}}
QListWidget::item:hover {{ background: #232833; }}
QListWidget::item:selected {{
    background: {ACCENT_DIM};
    color: #ffffff;
}}
/* 组合成员表：表头、网格线、选中行全部走深色，缺一项就是一块白 */
QTableWidget {{
    background: #171a21;
    alternate-background-color: #171a21;
    color: #e8eaf0;
    gridline-color: #262a34;
    border: 1px solid #2b303b;
    border-radius: 7px;
    font-size: 12px;
    outline: none;
    selection-background-color: {ACCENT_DIM};
    selection-color: #ffffff;
}}
QTableWidget::item {{ padding: 4px 6px; border: none; }}
QTableWidget::item:selected {{ background: {ACCENT_DIM}; }}
QHeaderView::section {{
    background: #1d212a;
    color: #c8cddb;
    border: none;
    border-bottom: 1px solid #2b303b;
    padding: 6px 8px;
    font-size: 12px;
}}
QTableCornerButton::section {{
    background: #1d212a;
    border: none;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: #333a46;
    border-radius: 4px;
    min-width: 28px;
}}
QScrollBar::handle:horizontal:hover {{ background: #414a59; }}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #333a46;
    border-radius: 4px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: #414a59; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""


# ---------------------------------------------------------------- 小部件

_QT_TO_KEY = {
    Qt.Key_Space: "space",
    Qt.Key_Tab: "tab",
    Qt.Key_Return: "enter",
    Qt.Key_Enter: "enter",
    Qt.Key_Escape: "esc",
    Qt.Key_Shift: "shift",
    Qt.Key_Control: "ctrl",
    Qt.Key_Alt: "alt",
    Qt.Key_CapsLock: "capslock",
    Qt.Key_Comma: "comma",
    Qt.Key_Period: "period",
    Qt.Key_Slash: "slash",
    Qt.Key_Semicolon: "semicolon",
    Qt.Key_Apostrophe: "quote",
}


_QT_BUTTON_TO_KEY = {
    Qt.LeftButton: "mouse_left",
    Qt.RightButton: "mouse_right",
    Qt.MiddleButton: "mouse_middle",
    Qt.BackButton: "mouse_4",      # 侧键 1
    Qt.ForwardButton: "mouse_5",   # 侧键 2
}

# 显示用短名。鼠标键不能直接显示 "MOUSE_4"，框里放不下也看不懂
_KEY_LABEL = {
    "mouse_left": "鼠标左键",
    "mouse_right": "鼠标右键",
    "mouse_middle": "鼠标中键",
    "mouse_4": "侧键1",
    "mouse_5": "侧键2",
    "space": "空格",
    "enter": "回车",
    "esc": "Esc",
    "capslock": "Caps",
    "ctrl": "Ctrl",
    "shift": "Shift",
    "alt": "Alt",
    "win": "Win",
}


def key_label(name: str) -> str:
    """绑定名 -> 框里显示的短名，支持组合键。

    组合键不写空格（"Ctrl+Shift+Y" 而不是 "Ctrl + Shift + Y"）：
    按键框宽度有限，带空格会被截成 "Ctrl + Shif…"，反而看不清绑的是什么。
    """
    parts = sr.spec_parts(name)
    if not parts:
        return ""
    return "+".join(_KEY_LABEL.get(p, p.upper()) for p in parts)


def _mods_prefix(mods) -> str:
    """Qt 修饰键状态 -> "ctrl+alt+shift+win" 的前半段（保持固定顺序）。"""
    parts = []
    if mods & Qt.ControlModifier:
        parts.append("ctrl")
    if mods & Qt.AltModifier:
        parts.append("alt")
    if mods & Qt.ShiftModifier:
        parts.append("shift")
    if mods & Qt.MetaModifier:
        parts.append("win")
    return "+".join(parts)


def key_name_of(ev) -> str:
    """Qt 按键事件 -> config 里的按键名（vk_of 能认的那种）。"""
    k = ev.key()
    if k in _QT_TO_KEY:
        return _QT_TO_KEY[k]
    if Qt.Key_A <= k <= Qt.Key_Z:
        return chr(k).lower()
    if Qt.Key_0 <= k <= Qt.Key_9:
        return chr(k)
    if Qt.Key_F1 <= k <= Qt.Key_F24:
        return f"f{k - Qt.Key_F1 + 1}"
    return ""


class _KeyEdit(QLineEdit):
    """真正接键盘/鼠标的那个输入框：按哪个键就绑哪个键。

    原来这里是普通输入框，得手动输 "f1" 再按回车才生效，
    大部分人点了进去打几个字发现没反应，就以为功能坏了。
    """

    key_changed = Signal(str)

    def __init__(self, value: str = "", width: int = 96) -> None:
        super().__init__()
        self.key_name = ""
        self.setFixedWidth(width)
        self.setAlignment(Qt.AlignCenter)
        self.setPlaceholderText("未绑定")
        self.setReadOnly(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.NoContextMenu)
        self.set_key(value)

    # ---- 取值/显示 ----
    def set_key(self, name: str) -> None:
        """外部设置绑定（不会回头触发 key_changed，避免回环）。"""
        self.key_name = sr.norm_spec(name)
        self.setText(key_label(self.key_name))
        self.setToolTip(self._tip())

    def _tip(self) -> str:
        return (
            "点一下，然后按键盘键或鼠标键；右侧 ✕ 或 Delete 取消绑定\n"
            "要绑组合键就这样：按住 Ctrl / Shift / Alt，再按主键\n"
            "（要绑鼠标左键请双击这个框，单击左键只是选中框）"
        )

    # ---- 录入 ----
    def keyPressEvent(self, ev) -> None:  # noqa: N802
        if ev.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self._apply("")
            return
        if ev.key() in (Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta):
            # 单按修饰键不当作绑定目标，避免误绑
            return
        name = key_name_of(ev)
        if name:
            prefix = _mods_prefix(ev.modifiers())
            self._apply(f"{prefix}+{name}" if prefix else name)

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        prefix = _mods_prefix(ev.modifiers())
        if ev.button() == Qt.LeftButton and not prefix:
            # 单击左键只用来聚焦，不然每次点框都会把自己绑成左键
            self.setFocus(Qt.MouseFocusReason)
            ev.accept()
            return
        name = _QT_BUTTON_TO_KEY.get(ev.button())
        if name is None:
            super().mousePressEvent(ev)
            return
        self._apply(f"{prefix}+{name}" if prefix else name)
        ev.accept()

    def mouseDoubleClickEvent(self, ev) -> None:  # noqa: N802
        prefix = _mods_prefix(ev.modifiers())
        if ev.button() == Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason)
            self._apply(f"{prefix}+mouse_left" if prefix else "mouse_left")
            ev.accept()
            return
        super().mouseDoubleClickEvent(ev)

    def _apply(self, name: str) -> None:
        self.key_name = sr.norm_spec(name)
        self.setText(key_label(self.key_name))
        self.setToolTip(self._tip())
        self.key_changed.emit(self.key_name)

    def focusInEvent(self, ev) -> None:  # noqa: N802
        super().focusInEvent(ev)
        self.selectAll()


class KeyBox(QWidget):
    """按键绑定框 = 输入框 + 一个看得见的清除按钮。

    以前只有"按 Delete 清除"，写在悬停提示里，绝大多数人根本不会发现，
    表现出来就是"绑上去以后没法取消了"。所以补一个常驻的 ✕：
    空着时灰掉，绑了键就亮起来，点一下立刻解除绑定。
    """

    key_changed = Signal(str)

    def __init__(self, value: str = "", width: int = 128) -> None:
        super().__init__()
        self.setObjectName("KeyBox")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.edit = _KeyEdit(value, max(56, width - 24))
        lay.addWidget(self.edit, 1)

        self.btn_clear = QPushButton("✕")
        self.btn_clear.setObjectName("KeyClear")
        self.btn_clear.setFixedSize(20, 20)
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.setFocusPolicy(Qt.NoFocus)  # 别把焦点从输入框抢走
        lay.addWidget(self.btn_clear, 0, Qt.AlignVCenter)

        self.setFixedWidth(width)
        self.edit.key_changed.connect(self._on_edit)
        self.btn_clear.clicked.connect(self.clear_key)
        self._sync_clear()

    # ---- 取值/显示 ----
    @property
    def key_name(self) -> str:
        return self.edit.key_name

    def set_key(self, name: str) -> None:
        """外部设置绑定（不会回头触发 key_changed，避免回环）。"""
        self.edit.set_key(name)
        self._sync_clear()

    def clear_key(self) -> None:
        """解除绑定。已经是空的就什么也不做（按钮此时本来就是灰的）。"""
        if self.edit.key_name:
            self.edit._apply("")

    def text(self) -> str:
        """兼容旧写法：显示的是按键短名。"""
        return self.edit.text()

    def _tip(self) -> str:
        return self.edit._tip()

    def mark_conflict(self, msg: str) -> None:
        """这个键被别人占了：输入框描红 + 提示原因。"""
        self.edit.setStyleSheet(
            "border:1px solid #ff6b6b;border-radius:6px;color:#ff9d9d;"
        )
        self.setToolTip(msg)
        self.edit.setToolTip(msg)

    def clear_conflict(self) -> None:
        self.edit.setStyleSheet("")
        self.setToolTip(self._tip())
        self.edit.setToolTip(self._tip())

    def _on_edit(self, name: str) -> None:
        self._sync_clear()
        self.key_changed.emit(name)

    def _sync_clear(self) -> None:
        self.btn_clear.setEnabled(bool(self.edit.key_name))


class TitleBar(QWidget):
    """自绘标题栏：拖动窗口、最小化、关闭。"""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(46)
        self._drag_from: QPoint | None = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 0, 12, 0)
        lay.setSpacing(8)

        dot = QLabel()
        dot.setPixmap(_dot_pixmap(12))
        dot.setFixedSize(12, 12)
        lay.addWidget(dot)

        title = QLabel("SR Voiceover Roulette")
        title.setObjectName("AppTitle")
        lay.addWidget(title)

        ver = QLabel(sr.APP_VERSION)
        ver.setObjectName("AppVersion")
        lay.addWidget(ver)
        lay.addStretch(1)

        self.btn_min = QPushButton("—")
        self.btn_min.setObjectName("WinBtn")
        self.btn_min.setFixedSize(30, 26)
        self.btn_min.setCursor(Qt.PointingHandCursor)
        lay.addWidget(self.btn_min)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("WinBtn")
        self.btn_close.setFixedSize(30, 26)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        lay.addWidget(self.btn_close)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton:
            self._drag_from = e.globalPosition().toPoint() - self.window().frameGeometry().topLeft()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._drag_from is not None and e.buttons() & Qt.LeftButton:
            self.window().move(e.globalPosition().toPoint() - self._drag_from)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        self._drag_from = None


def _dot_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(accent(255))
    p.drawEllipse(0, 0, size, size)
    p.setBrush(QColor(20, 22, 28, 255))
    p.drawEllipse(size * 0.33, size * 0.33, size * 0.34, size * 0.34)
    p.end()
    return pm


def _card(title: str = "") -> tuple[QFrame, QVBoxLayout]:
    """返回一个带内边距的卡片容器和它的布局。"""
    frame = QFrame()
    frame.setObjectName("Card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(10)
    if title:
        lab = QLabel(title)
        lab.setObjectName("SectionLabel")
        lay.addWidget(lab)
    return frame, lay


def _row(label: str, widget: QWidget, hint: str = "") -> QWidget:
    """一行设置项：左边标签，右边控件。"""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(12)
    lab = QLabel(label)
    lab.setFixedWidth(96)
    lab.setStyleSheet("color:#a9b0c0;font-size:12px;")
    lay.addWidget(lab)
    lay.addWidget(widget, 1)
    if hint:
        h = QLabel(hint)
        h.setObjectName("Hint")
        lay.addWidget(h)
    return w


def scfg_save(scfg) -> None:
    """保存 sounds.json。失败只记日志——用户正在改东西，弹窗打断更糟。"""
    if scfg is None:
        return
    try:
        scfg.save()
    except Exception as exc:
        sr._log(f"[settings] 保存 sounds.json 失败: {exc}")


def _wrap_row(layout) -> QWidget:
    """把一堆控件横向排好后塞进 _row 的"右侧控件"位。"""
    w = QWidget()
    w.setLayout(layout)
    layout.setContentsMargins(0, 0, 0, 0)
    return w


def _divider() -> QFrame:
    d = QFrame()
    d.setObjectName("Divider")
    d.setFrameShape(QFrame.HLine)
    return d


class _WrapLabel(QLabel):
    """会自己撑高的自动换行标签。

    QLabel 开了 wordWrap 之后，布局拿到的 sizeHint 是按"一行"算的，
    多行长文本会被压扁成半截。这里每次宽度变化都按 heightForWidth
    把最小高度顶回去，文字再长也不会被切掉。
    """

    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self.setWordWrap(True)

    def resizeEvent(self, ev) -> None:  # noqa: N802
        super().resizeEvent(ev)
        self._fit()

    def setText(self, text: str) -> None:  # noqa: N802
        super().setText(text)
        self._fit()

    def _fit(self) -> None:
        """按当前宽度量一遍文字实际要多高。

        不用 QLabel.heightForWidth()：它在布局还没定宽的时候会给出偏小的值，
        结果多行文字被切掉半截。直接用字体度量按"自动换行"框一遍最稳。
        """
        w = self.width()
        if w <= 0 or not self.text():
            return
        fm = self.fontMetrics()
        rect = fm.boundingRect(
            QRect(0, 0, w, 10000),
            Qt.TextWordWrap | Qt.AlignLeft | Qt.TextExpandTabs,
            self.text(),
        )
        need = rect.height() + 2
        if need != self.minimumHeight():
            self.setMinimumHeight(need)


# ---------------------------------------------------------------- 左侧页

class LibraryPage(QWidget):
    """音效库：矩形格子列出 sounds 目录里的全部音效。

    自己也是拖放目标：从轮盘上把音效拖回这里 = 从轮盘移除。
    最下面一节是组合音效（内置编辑器，可拖到轮盘）。
    """

    slot_removed = Signal(int)
    combo_new = Signal()
    combo_edit = Signal(str)     # cid
    combo_delete = Signal(str)   # cid

    def __init__(self, bank: sr.SoundBank, scfg=None) -> None:
        super().__init__()
        self.bank = bank
        self.scfg = scfg
        self.setAcceptDrops(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 12, 0, 0)
        root.setSpacing(10)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索音效…")
        self.search.setClearButtonEnabled(True)
        bar.addWidget(self.search, 1)
        self.btn_folder = QPushButton("打开文件夹")
        self.btn_folder.setCursor(Qt.PointingHandCursor)
        self.btn_folder.clicked.connect(self._open_folder)
        bar.addWidget(self.btn_folder)
        root.addLayout(bar)

        hint = QLabel("拖动格子到右侧轮盘添加；把轮盘上的音效拖回这里可移除")
        hint.setObjectName("Hint")
        root.addWidget(hint)
        self.search.textChanged.connect(lambda _t: self.refresh())

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        self.grid = QGridLayout(holder)
        self.grid.setContentsMargins(0, 0, 6, 0)
        self.grid.setSpacing(8)
        self.grid.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(holder)
        root.addWidget(self.scroll, 1)

        # ---- 组合音效 ----
        divider = QFrame()
        divider.setObjectName("Divider")
        root.addWidget(divider)

        chead = QHBoxLayout()
        chead.setSpacing(8)
        ctitle = QLabel("组合音效")
        ctitle.setObjectName("SectionLabel")
        chead.addWidget(ctitle)
        chead.addStretch(1)
        self.btn_combo_new = QPushButton("＋ 新建组合")
        self.btn_combo_new.setCursor(Qt.PointingHandCursor)
        self.btn_combo_new.clicked.connect(self.combo_new.emit)
        chead.addWidget(self.btn_combo_new)
        self.btn_combo_edit = QPushButton("编辑")
        self.btn_combo_edit.setCursor(Qt.PointingHandCursor)
        self.btn_combo_edit.clicked.connect(self._edit_selected_combo)
        chead.addWidget(self.btn_combo_edit)
        self.btn_combo_del = QPushButton("删除")
        self.btn_combo_del.setCursor(Qt.PointingHandCursor)
        self.btn_combo_del.clicked.connect(self._delete_selected_combo)
        chead.addWidget(self.btn_combo_del)
        root.addLayout(chead)

        self.combo_list = _ComboList(self)
        self.combo_list.setFixedHeight(104)
        self.combo_list.edit_requested.connect(self.combo_edit.emit)
        self.combo_list.delete_requested.connect(self.combo_delete.emit)
        root.addWidget(self.combo_list)

        chint = QLabel("双击组合可编辑；把组合拖到右侧轮盘，就能像普通音效一样用")
        chint.setObjectName("Hint")
        chint.setWordWrap(True)
        root.addWidget(chint)

        self.refresh()

    def refresh(self) -> None:
        self.refresh_combos()      # 先刷组合区：下面早退也不会漏
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 递归扫描：子文件夹里的音效也列出来，用户可以用文件夹分类整理
        found = sr.scan_sound_files()
        total = len(found)
        kw = self.search.text().strip().lower()

        # 轮盘上已经有的（按相对路径比，子文件夹里的同名文件不会互相顶替）
        on_wheel = {
            sr.sound_key(p) for p in self.bank.items if isinstance(p, Path)
        } if (self.scfg is not None and len(self.bank) > 0) else set()

        if not found:
            empty = QLabel(
                "sounds 目录里还没有音效。\n"
                "点上面的「打开文件夹」，把音频文件放进去，再回来就能看到了。"
            )
            empty.setObjectName("Hint")
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            self.grid.addWidget(empty, 0, 0, 1, 2)
            return

        # 按文件夹分组。key 里的 "/" 前面那段就是分组名，顶层的归一组
        groups: dict[str, list[tuple[str, Path]]] = {}
        for key, path in found:
            if kw and kw not in path.stem.lower():
                continue
            group = key.rsplit("/", 1)[0] if "/" in key else ""
            groups.setdefault(group, []).append((key, path))

        if not groups:
            empty = QLabel(f"没有匹配「{kw}」的音效。")
            empty.setObjectName("Hint")
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            self.grid.addWidget(empty, 0, 0, 1, 2)
            return

        row = 0
        num = 0
        for group in sorted(groups, key=lambda g: (g != "", g.lower())):
            items = groups[group]
            if group or len(groups) > 1:
                head = QLabel(
                    f"{group or '根目录'}    {len(items)} 个"
                )
                head.setObjectName("SectionLabel")
                head.setStyleSheet(
                    f"color:{accent_hex()};font-size:12px;font-weight:600;"
                    "padding:6px 2px 2px 2px;background:transparent;"
                )
                self.grid.addWidget(head, row, 0, 1, 2)
                row += 1
            for col, (key, path) in enumerate(items):
                cell = _SoundCell(num, path, key in on_wheel)
                self.grid.addWidget(cell, row + col // 2, col % 2)
                num += 1
            row += (len(items) + 1) // 2

        self.refresh_combos()

    def refresh_combos(self) -> None:
        """刷新底部组合列表：名字、成员数、播放方式、是否已在轮盘。"""
        self.combo_list.clear()
        if self.scfg is None:
            return
        on_wheel = {sr.sound_key(p) for p in self.bank.items if isinstance(p, Path)}
        for c in self.scfg.combos.values():
            mode = COMBO_MODE_LABEL.get(c.mode, c.mode)
            tail = f"{len(c.items)} 项 · {mode}"
            if self.scfg.combo_key(c.cid) in on_wheel:
                tail += " · 已在轮盘"
            it = QListWidgetItem(f"◆{c.name}    {tail}")
            it.setData(Qt.UserRole, c.cid)
            if self.scfg.combo_key(c.cid) in on_wheel:
                it.setForeground(accent())
            self.combo_list.addItem(it)
        if not self.scfg.combos:
            it = QListWidgetItem("还没有组合音效。点「＋ 新建组合」开始搭一个。")
            it.setFlags(Qt.NoItemFlags)
            it.setForeground(QColor("#767d8d"))
            self.combo_list.addItem(it)

    def _selected_cid(self) -> str:
        it = self.combo_list.currentItem()
        return str(it.data(Qt.UserRole) or "") if it else ""

    def _edit_selected_combo(self) -> None:
        cid = self._selected_cid()
        if cid:
            self.combo_edit.emit(cid)

    def _delete_selected_combo(self) -> None:
        cid = self._selected_cid()
        if cid:
            self.combo_delete.emit(cid)

    def _open_folder(self) -> None:
        """在资源管理器里打开 sounds 目录。目录不存在就先建出来。"""
        try:
            sr.SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
            os.startfile(str(sr.SOUNDS_DIR))  # noqa: S606
        except Exception as exc:
            sr._log(f"[settings] 打开 sounds 目录失败: {exc}")

    def _drop_hint(self, on: bool) -> None:
        # 这里不能用空字符串还原：那会把背景交还给 Qt 默认的白色
        vp = self.scroll.viewport()
        vp.setStyleSheet(
            "background: rgba(46,211,108,26);" if on else "background: transparent;"
        )

    # ---- 从轮盘拖回音效库 = 移除 ----
    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasFormat(MIME_SLOT):
            self._drop_hint(True)
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasFormat(MIME_SLOT):
            e.acceptProposedAction()

    def dragLeaveEvent(self, e) -> None:  # noqa: N802
        self._drop_hint(False)

    def dropEvent(self, e) -> None:  # noqa: N802
        self._drop_hint(False)
        md = e.mimeData()
        if md.hasFormat(MIME_SLOT):
            idx = int(bytes(md.data(MIME_SLOT)).decode("utf-8"))
            self.slot_removed.emit(idx)
            e.acceptProposedAction()


def _duration_text(path: Path) -> str:
    """读音频时长。wav 读文件头，mp3/ogg/flac/m4a 让解码器读流信息，读不出显示 —。"""
    dur = sr.audio_duration(path)
    return f"{dur:.2f} 秒" if dur > 0 else "—"


class _SoundCell(QFrame):
    """音效库里的一格。按住拖到右边轮盘即可上盘。"""

    def __init__(self, index: int, path: Path, on_wheel: bool = False) -> None:
        super().__init__()
        self.setObjectName("Cell")
        self.setFixedHeight(62)
        self.setCursor(Qt.OpenHandCursor)
        self.path = path
        self.on_wheel = on_wheel
        self._press: QPoint | None = None
        if on_wheel:
            self.setStyleSheet(
                "QFrame#Cell{border:1px solid %s;}" % accent_dim()
            )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 12, 8)
        lay.setSpacing(10)

        num = QLabel(f"{index + 1:02d}")
        num.setFixedWidth(22)
        num.setStyleSheet(
            f"color:{accent_hex()};font-size:11px;font-weight:600;"
            "background:transparent;"
        )
        lay.addWidget(num)

        col = QVBoxLayout()
        col.setSpacing(2)
        name = QLabel(path.stem)
        name.setStyleSheet("font-size:12px;color:#e8eaf0;background:transparent;")
        col.addWidget(name)
        tail = " · 已在轮盘" if on_wheel else ""
        meta = QLabel(f"{path.suffix.upper().lstrip('.')} · {_duration_text(path)}{tail}")
        meta.setObjectName("Hint")
        if on_wheel:
            meta.setStyleSheet(f"color:{accent_hex()};font-size:11px;background:transparent;")
        col.addWidget(meta)
        lay.addLayout(col, 1)

    # ---- 拖出去 ----
    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton:
            self._press = e.position().toPoint()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._press is None or not (e.buttons() & Qt.LeftButton):
            return
        if (e.position().toPoint() - self._press).manhattanLength() < 10:
            return
        self._press = None
        mime = QMimeData()
        # 用相对路径当键：子文件夹里的音效拖到轮盘后能正确定位到文件
        mime.setData(MIME_LIB, sr.sound_key(self.path).encode("utf-8"))
        mime.setText(self.path.stem)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(_drag_pixmap(self.path.stem))
        drag.exec(Qt.CopyAction)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        self._press = None


class _ComboList(QListWidget):
    """组合列表：双击编辑，拖出去就落到轮盘上。

    用标准 QListWidget 而不是自绘：滚动、选中、键盘操作都是现成的，
    少一处自绘就少一处错位的可能（v0.7 的自绘音轨就是教训）。
    """

    edit_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.itemDoubleClicked.connect(self._on_double)

    def _cid_of(self, item) -> str:
        return str(item.data(Qt.UserRole) or "") if item is not None else ""

    def _on_double(self, item) -> None:
        cid = self._cid_of(item)
        if cid:
            self.edit_requested.emit(cid)

    def startDrag(self, actions) -> None:  # noqa: N802
        item = self.currentItem()
        cid = self._cid_of(item)
        if not cid:
            return
        key = COMBO_PREFIX + cid
        mime = QMimeData()
        mime.setData(MIME_LIB, key.encode("utf-8"))
        mime.setText(key)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(_drag_pixmap(item.text().split("    ")[0]))
        drag.exec(Qt.CopyAction)


class _ComboTimeline(QWidget):
    """只读时间条：每项一根横条，起点 = 什么时候响，长度 = 响多久。

    刻意做成只读：不能拖、不能改，纯粹是"一眼看出谁压着谁、哪一段是空的"。
    v0.7 那套可编辑音轨翻车的原因不是"画了个时间轴"，而是拖拽状态机 +
    自绘坐标系在窗口缩放/DPI 变化时会错位；这里没有任何交互与状态，
    也就没有错位和卡死可言。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.spans: list[tuple[int, float, float, bool]] = []
        self.total = 0.0
        self.empty_text = "还没有成员"
        self.setMinimumHeight(86)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_spans(self, spans, total: float) -> None:
        self.spans = list(spans)
        self.total = max(0.0, float(total))
        self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = max(1, self.width()), max(1, self.height())
        p.setPen(QPen(QColor("#2b303b"), 1))
        p.setBrush(QColor("#171a21"))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 7, 7)

        left, right = 12.0, 12.0
        axis_h = 15.0
        plot_w = max(1.0, w - left - right)
        plot_top = 8.0
        plot_h = max(1.0, h - axis_h - plot_top)

        if not self.spans or self.total <= 0.01:
            p.setPen(QPen(QColor("#6f7686")))
            f = QFont(UI_FONT)
            f.setPointSizeF(8.5)
            p.setFont(f)
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, self.empty_text)
            return

        scale = plot_w / self.total

        # 分道：互相重叠的项往下排一行，谁也不会被谁盖住
        lanes: list[float] = []
        placed: list[tuple[int, float, float, bool, int]] = []
        for idx, start, dur, ok in sorted(self.spans, key=lambda s: s[1]):
            lane = None
            for k, end in enumerate(lanes):
                if start >= end - 1e-6:
                    lane = k
                    lanes[k] = max(end, start + dur)
                    break
            if lane is None:
                lanes.append(start + dur)
                lane = len(lanes) - 1
            placed.append((idx, start, dur, ok, lane))

        n_lane = max(1, len(lanes))
        lane_h = max(9.0, (plot_h - (n_lane - 1) * 3.0) / n_lane)

        for idx, start, dur, ok, lane in placed:
            x = left + start * scale
            bw = max(3.0, dur * scale)
            y = plot_top + lane * (lane_h + 3.0)
            p.setPen(Qt.NoPen)
            p.setBrush(accent() if ok else QColor("#a25050"))
            rad = min(4.0, lane_h / 2.0)
            p.drawRoundedRect(QRectF(x, y, bw, lane_h), rad, rad)
            if bw >= 32:
                p.setPen(QPen(QColor("#0f1218")))
                f = QFont(UI_FONT)
                f.setPointSizeF(7.8)
                f.setBold(True)
                p.setFont(f)
                p.drawText(QRectF(x + 2, y, bw - 4, lane_h), Qt.AlignCenter,
                           f"#{idx + 1}")

        # 时间刻度：最多 10 格，自动挑 1/2/5/10 秒一档
        step = 1.0
        while self.total / step > 10:
            step *= 2.0
        f = QFont(UI_FONT)
        f.setPointSizeF(7.5)
        p.setFont(f)
        t = 0.0
        base_y = plot_top + plot_h
        while t <= self.total + 1e-6:
            x = left + t * scale
            p.setPen(QPen(QColor("#39404e"), 1))
            p.drawLine(QPointF(x, base_y), QPointF(x, base_y + 3))
            p.setPen(QPen(QColor("#6f7686")))
            p.drawText(QRectF(x - 22, base_y + 2, 44, axis_h - 2), Qt.AlignCenter,
                       f"{t:.0f}s" if step >= 1.0 else f"{t:.1f}s")
            t += step


class _ProgressDialog(QDialog):
    """重复递进生成器：把选中那一项复制若干份，每份自动错开。

    典型用法（组合音效 1）：选中第一项 → 复制 2 份、每份 +2 半音、
    延迟 +200ms → 直接得到"原版 / 升调版 / 再升一版"的三连，
    不用手填三遍数字、也不会算错先后。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("重复递进生成")
        self.setStyleSheet(build_qss())
        self.setMinimumWidth(420)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)

        tip = QLabel(
            "以选中的这一项为模板，在它后面插入 N 份，每份按下面的增量递进。\n"
            "裁剪、音量、随机抖动会原样复制，只改变调 / 速度 / 延迟。"
        )
        tip.setObjectName("Hint")
        tip.setWordWrap(True)
        root.addWidget(tip)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.spn_copies = QSpinBox()
        self.spn_copies.setRange(1, 12)
        self.spn_copies.setValue(2)
        self.spn_copies.setSuffix(" 份")
        grid.addWidget(QLabel("复制份数"), 0, 0)
        grid.addWidget(self.spn_copies, 0, 1)

        self.spn_semi = QDoubleSpinBox()
        self.spn_semi.setRange(-12.0, 12.0)
        self.spn_semi.setSingleStep(0.5)
        self.spn_semi.setDecimals(1)
        self.spn_semi.setValue(2.0)
        self.spn_semi.setSuffix(" 半音")
        grid.addWidget(QLabel("每份变调"), 1, 0)
        grid.addWidget(self.spn_semi, 1, 1)

        self.spn_rate = QSpinBox()
        self.spn_rate.setRange(-50, 50)
        self.spn_rate.setSingleStep(5)
        self.spn_rate.setValue(0)
        self.spn_rate.setSuffix(" %")
        grid.addWidget(QLabel("每份变速"), 2, 0)
        grid.addWidget(self.spn_rate, 2, 1)

        self.spn_delay = QSpinBox()
        self.spn_delay.setRange(-1000, 5000)
        self.spn_delay.setSingleStep(50)
        self.spn_delay.setValue(200)
        self.spn_delay.setSuffix(" ms")
        grid.addWidget(QLabel("每份延迟"), 3, 0)
        grid.addWidget(self.spn_delay, 3, 1)
        root.addLayout(grid)

        note = QLabel("延迟增量是按参照点算的：想让它叠到前一项的尾巴上就填负数。")
        note.setObjectName("Hint")
        note.setWordWrap(True)
        root.addWidget(note)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def values(self) -> tuple[int, float, int, int]:
        return (
            int(self.spn_copies.value()),
            float(self.spn_semi.value()),
            int(self.spn_rate.value()),
            int(self.spn_delay.value()),
        )


class ComboEditorDialog(QDialog):
    """组合音效编辑器（v0.7.2：表格 + 只读时间条，仍然没有可编辑音轨）。

    为什么用表格而不是自绘音轨：
      · 每一项的"什么时候响"是三个离散选项 + 一个毫秒数，表格能一眼看全，
        也不会因为窗口缩放/字体变化错位（v0.7 的音轨就是在这上面翻车的）
      · 标准控件自带键盘操作、滚动、焦点管理，卡死和错位的概率低一个量级
    改动即时写回 ComboDef 并存盘，没有"取消"——关掉就是保存完了。
    v0.7.2 加了撤销/重做，改错了 Ctrl+Z 退回去，不用手改回来。
    """

    changed = Signal()

    COLS = ("#", "音效", "触发条件", "延迟", "音量", "变调", "速度", "时长")

    def __init__(self, scfg, cdef, engine=None, parent=None, cfg=None) -> None:
        super().__init__(parent)
        self.scfg = scfg
        self.cdef = cdef
        self.engine = engine
        self.cfg = cfg          # 只用来查快捷键冲突，可以不传
        self._loading = False
        self._undo_stack: list[str] = []
        self._redo_stack: list[str] = []
        self.setWindowTitle(f"编辑组合：{cdef.name}")
        self.resize(1120, 812)
        self.setMinimumSize(1000, 720)
        # 主窗口的深色样式表不会自动传给独立对话框，必须自己挂一份
        self.setStyleSheet(build_qss())

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(9)

        # ---- 第一行：名字 + 播放方式 ----
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(QLabel("名字"))
        self.ed_name = QLineEdit(cdef.name)
        self.ed_name.setMinimumWidth(160)
        top.addWidget(self.ed_name, 2)
        top.addWidget(QLabel("播放方式"))
        self.cmb_mode = QComboBox()
        for m in COMBO_MODES:
            self.cmb_mode.addItem(COMBO_MODE_LABEL.get(m, m), m)
        self.cmb_mode.setCurrentIndex(max(0, self.cmb_mode.findData(cdef.mode)))
        top.addWidget(self.cmb_mode, 2)

        self.lbl_count = QLabel("随机项数")
        top.addWidget(self.lbl_count)
        self.spn_count = QSpinBox()
        self.spn_count.setRange(1, MAX_COMBO_ITEMS)
        self.spn_count.setValue(int(cdef.count))
        self.spn_count.setToolTip("每次从成员里随机抽几项（不会重复抽同一项）")
        top.addWidget(self.spn_count)

        self.chk_shuffle = QCheckBox("抽到后打乱顺序")
        self.chk_shuffle.setChecked(bool(cdef.shuffle))
        top.addWidget(self.chk_shuffle)
        root.addLayout(top)

        self.lbl_mode_tip = QLabel()
        self.lbl_mode_tip.setObjectName("Hint")
        self.lbl_mode_tip.setWordWrap(True)
        root.addWidget(self.lbl_mode_tip)

        # ---- 中部：左音效库 / 右成员表 ----
        mid = QHBoxLayout()
        mid.setSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(QLabel("sounds 目录（双击加入）"))
        self.lst_sounds = QListWidget()
        self.lst_sounds.setFixedWidth(188)
        for name in self._sound_names():
            QListWidgetItem(Path(name).stem, self.lst_sounds)
        # 用 UserRole 存全名，列表显示去扩展名的样子
        for k, name in enumerate(self._sound_names()):
            self.lst_sounds.item(k).setData(Qt.UserRole, name)
        self.lst_sounds.itemDoubleClicked.connect(self._add_sound)

        self.ed_find = QLineEdit()
        self.ed_find.setPlaceholderText("搜索音效…")
        self.ed_find.setClearButtonEnabled(True)
        self.ed_find.setToolTip(
            "打几个字就把列表筛出来，并自动滚到第一个匹配的位置。\n"
            "回车直接把当前选中的音效加进组合，清空就恢复全部。"
        )
        self.ed_find.textChanged.connect(self._filter_sounds)
        self.ed_find.returnPressed.connect(self._add_current_sound)
        left.addWidget(self.ed_find)
        left.addWidget(self.lst_sounds, 1)
        tip = QLabel("同一个音效可以重复加入")
        tip.setObjectName("Hint")
        tip.setWordWrap(True)
        left.addWidget(tip)
        mid.addLayout(left)

        right = QVBoxLayout()
        right.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(QLabel("成员（行序 = 播放顺序）"))
        head.addStretch(1)
        for text, fn, tip_text in (
            ("上移", self._move_up, "和上一行交换位置"),
            ("下移", self._move_down, "和下一行交换位置"),
            ("删除这一项", self._remove_item, "从组合里移掉（不删文件）"),
            ("递进复制…", self._progress_copy,
             "把选中项复制几份，每份自动变调/变速/延迟错开"),
        ):
            b = QPushButton(text)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(tip_text)
            b.clicked.connect(fn)
            head.addWidget(b)
        right.addLayout(head)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in range(2, len(self.COLS)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(0, 34)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.itemSelectionChanged.connect(self._sync_detail_bar)
        right.addWidget(self.table, 1)
        mid.addLayout(right, 1)
        root.addLayout(mid, 1)

        # ---- 只读时间条 ----
        row_tl = QHBoxLayout()
        row_tl.setSpacing(8)
        lbl_tl = QLabel("时间条（只读，用来对照谁压着谁）")
        lbl_tl.setObjectName("Hint")
        row_tl.addWidget(lbl_tl)
        row_tl.addStretch(1)
        self.lbl_tl = QLabel()
        self.lbl_tl.setObjectName("Hint")
        row_tl.addWidget(self.lbl_tl)
        root.addLayout(row_tl)
        self.timeline = _ComboTimeline()
        root.addWidget(self.timeline)

        # ---- 选中项细节：裁剪 + 逐项随机 ----
        det = QHBoxLayout()
        det.setSpacing(8)
        self.lbl_sel = QLabel("选中项：—")
        self.lbl_sel.setObjectName("SectionLabel")
        det.addWidget(self.lbl_sel)

        self.spn_start = QSpinBox()
        self.spn_start.setRange(0, 600000)
        self.spn_start.setSingleStep(50)
        self.spn_start.setSuffix(" ms")
        self.spn_start.setPrefix("起点 ")
        self.spn_start.setToolTip("从原音效的第几毫秒开始取；0 = 从头")
        self.spn_start.setMinimumWidth(118)
        det.addWidget(self.spn_start)

        self.spn_len = QSpinBox()
        self.spn_len.setRange(0, 600000)
        self.spn_len.setSingleStep(50)
        self.spn_len.setSuffix(" ms")
        self.spn_len.setPrefix("长度 ")
        self.spn_len.setSpecialValueText("长度 到结尾")
        self.spn_len.setToolTip("只取这么长；0 = 一直放到结尾")
        self.spn_len.setMinimumWidth(118)
        det.addWidget(self.spn_len)

        self.spn_rsemi = QDoubleSpinBox()
        self.spn_rsemi.setRange(0.0, 12.0)
        self.spn_rsemi.setSingleStep(0.5)
        self.spn_rsemi.setDecimals(1)
        self.spn_rsemi.setSuffix(" 半音")
        self.spn_rsemi.setPrefix("随机变调 ±")
        self.spn_rsemi.setToolTip("每次触发在这一项上随机加减，0 = 不变")
        self.spn_rsemi.setMinimumWidth(136)
        det.addWidget(self.spn_rsemi)

        self.spn_rrate = QSpinBox()
        self.spn_rrate.setRange(0, 50)
        self.spn_rrate.setSingleStep(5)
        self.spn_rrate.setSuffix(" %")
        self.spn_rrate.setPrefix("随机变速 ±")
        self.spn_rrate.setToolTip("每次触发在这一项上随机快慢，0 = 不变")
        self.spn_rrate.setMinimumWidth(136)
        det.addWidget(self.spn_rrate)

        det.addStretch(1)
        self.btn_preview_one = QPushButton("试听这一项")
        self.btn_preview_one.setCursor(Qt.PointingHandCursor)
        self.btn_preview_one.clicked.connect(self._preview_item)
        det.addWidget(self.btn_preview_one)
        self.btn_preview_from = QPushButton("从这行开始试听")
        self.btn_preview_from.setCursor(Qt.PointingHandCursor)
        self.btn_preview_from.setToolTip("从选中的这一项开始往后播，前面的跳过")
        self.btn_preview_from.clicked.connect(self._preview_from_row)
        det.addWidget(self.btn_preview_from)
        root.addLayout(det)

        # ---- 组合整体参数 ----
        lbl_glob = QLabel("整体参数")
        lbl_glob.setObjectName("SectionLabel")
        self.spn_orate = self._pct_spin(50, 200, "速度", "全组合一起变速，乘在每项自己的速度上")
        self.spn_osemi = QDoubleSpinBox()
        self.spn_osemi.setRange(-24.0, 24.0)
        self.spn_osemi.setSingleStep(1.0)
        self.spn_osemi.setDecimals(1)
        self.spn_osemi.setSuffix(" 半音")
        self.spn_osemi.setPrefix("变调 ")
        self.spn_osemi.setToolTip("全组合一起变调，叠在每项自己的变调上")
        self.spn_osemi.setMinimumWidth(126)
        self.spn_orrate = self._pct_spin(0, 80, "随机速度 ±", "每次触发整体随机快慢一点，全组合共用同一个值")
        self.spn_osemi_r = QDoubleSpinBox()
        self.spn_osemi_r.setRange(0.0, 12.0)
        self.spn_osemi_r.setSingleStep(0.5)
        self.spn_osemi_r.setDecimals(1)
        self.spn_osemi_r.setSuffix(" 半音")
        self.spn_osemi_r.setPrefix("随机变调 ±")
        self.spn_osemi_r.setToolTip("每次触发整体随机变调一点，全组合共用同一个值")
        self.spn_osemi_r.setMinimumWidth(142)
        self.spn_cool = self._plain_spin(0, 60000, 50, " ms", "冷却 ", "触发后这么久之内再按无效，防连按叠成一团")
        self.spn_voices = self._plain_spin(0, 16, 1, " 条", "最多同时 ", "同一条组合最多几条声音一起响，0 = 不限")

        row_a = QHBoxLayout()
        row_a.setSpacing(8)
        row_a.addWidget(lbl_glob)
        row_a.addWidget(self.spn_orate)
        row_a.addWidget(self.spn_osemi)
        row_a.addWidget(self.spn_orrate)
        row_a.addWidget(self.spn_osemi_r)
        row_a.addStretch(1)
        root.addLayout(row_a)

        lbl_lim = QLabel("限流")
        lbl_lim.setObjectName("SectionLabel")
        lbl_lim.setToolTip("防连按叠音：冷却时间内不再响应，同时发声数超了先掐最早的")
        row_b = QHBoxLayout()
        row_b.setSpacing(8)
        row_b.addWidget(lbl_lim)
        row_b.addWidget(self.spn_cool)
        row_b.addWidget(self.spn_voices)
        row_b.addWidget(QLabel("专属热键"))
        self.key_combo = KeyBox(self.scfg.combo_setting(cdef.cid).hotkey, 128)
        self.key_combo.setToolTip("这个组合不必占轮盘格子，单手一个键直接触发")
        row_b.addWidget(self.key_combo)
        row_b.addStretch(1)
        hint = QLabel("整体参数叠在每项自己的参数上；逐项随机只抖那一项")
        hint.setObjectName("Hint")
        row_b.addWidget(hint)
        root.addLayout(row_b)

        # ---- 底部 ----
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.lbl_total = QLabel()
        self.lbl_total.setObjectName("Hint")
        self.btn_undo = QPushButton("撤销")
        self.btn_undo.setCursor(Qt.PointingHandCursor)
        self.btn_undo.clicked.connect(self._undo)
        self.btn_redo = QPushButton("重做")
        self.btn_redo.setCursor(Qt.PointingHandCursor)
        self.btn_redo.clicked.connect(self._redo)
        bottom.addWidget(self.btn_undo)
        bottom.addWidget(self.btn_redo)
        self.btn_export = QPushButton("导出 WAV")
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.setToolTip("把这条组合渲染成一条音频文件")
        self.btn_export.clicked.connect(self._export_wav)
        bottom.addWidget(self.btn_export)
        bottom.addStretch(1)
        b_all = QPushButton("试听整个组合")
        b_all.setCursor(Qt.PointingHandCursor)
        b_all.clicked.connect(self._preview_all)
        bottom.addWidget(b_all)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bottom.addWidget(bb)
        root.addLayout(bottom)
        root.addWidget(self.lbl_total)

        if self.engine is None:
            for w in (self.btn_preview_one, self.btn_preview_from, b_all, self.btn_export):
                w.setEnabled(False)
                w.setToolTip("引擎未就绪，暂时无法试听/导出")

        # ---- 信号 ----
        self.ed_name.textEdited.connect(self._push_name)
        self.cmb_mode.currentIndexChanged.connect(self._push_mode)
        self.spn_count.valueChanged.connect(self._push_params)
        self.chk_shuffle.toggled.connect(self._push_params)
        for w in (self.spn_orate, self.spn_osemi, self.spn_orrate,
                  self.spn_osemi_r, self.spn_cool, self.spn_voices):
            w.valueChanged.connect(self._push_combo_params)
        self.key_combo.key_changed.connect(self._push_hotkey)
        for w in (self.spn_start, self.spn_len):
            w.valueChanged.connect(self._on_trim_changed)
        for w in (self.spn_rsemi, self.spn_rrate):
            w.valueChanged.connect(self._on_item_random_changed)

        # Ctrl+Z / Ctrl+Y（Ctrl+Shift+Z 也认）
        sc_undo = QShortcut(QKeySequence.StandardKey.Undo, self)
        sc_undo.activated.connect(self._undo)
        sc_redo = QShortcut(QKeySequence("Ctrl+Y"), self)
        sc_redo.activated.connect(self._redo)
        sc_redo2 = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        sc_redo2.activated.connect(self._redo)

        self._sync_combo_widgets()
        self.reload_table()
        self._sync_mode_widgets()
        self._sync_detail_bar()
        self._sync_undo_buttons()
        self._check_hotkey_conflict()

    # ---- 小工具 ----
    @staticmethod
    def _pct_spin(lo: int, hi: int, prefix: str, tip: str) -> QSpinBox:
        box = QSpinBox()
        box.setRange(lo, hi)
        box.setSingleStep(5)
        box.setSuffix(" %")
        box.setPrefix(prefix + " ")
        box.setToolTip(tip)
        box.setMinimumWidth(126)
        return box

    @staticmethod
    def _plain_spin(lo: int, hi: int, step: int, suffix: str,
                    prefix: str, tip: str) -> QSpinBox:
        box = QSpinBox()
        box.setRange(lo, hi)
        box.setSingleStep(step)
        box.setSuffix(suffix)
        box.setPrefix(prefix)
        box.setToolTip(tip)
        box.setMinimumWidth(120)
        return box

    def _sound_names(self) -> list[str]:
        """音效库里的全部音效（配置键：相对路径，子文件夹算在内）。"""
        return [key for key, _p in sr.scan_sound_files()]

    # ---- 音效搜索 ----
    def _filter_sounds(self, text: str) -> None:
        """边打边筛：只留匹配项，并把滚动条直接带到第一个命中上。

        左侧列表宽度固定，音效一多就得翻好几屏才能找到目标。
        所以搜索框不只是"过滤"，还要把视线直接送到第一个匹配的位置，
        否则筛完还得自己往下翻，问题只解决了一半。
        """
        kw = (text or "").strip().lower()
        first = None
        for i in range(self.lst_sounds.count()):
            it = self.lst_sounds.item(i)
            hit = (not kw) or (kw in it.text().lower())
            it.setHidden(not hit)
            if hit and first is None:
                first = it
        self.lst_sounds.clearSelection()
        if first is None:
            return
        self.lst_sounds.setCurrentItem(first)
        self.lst_sounds.scrollToItem(first, QAbstractItemView.PositionAtCenter)

    def _add_current_sound(self) -> None:
        """搜索框里按回车 = 把当前选中的音效加进组合。"""
        it = self.lst_sounds.currentItem()
        if it is None or it.isHidden():
            return
        self._add_sound(it)


    def _member_duration(self, it) -> float:
        """这一项处理后的时长（秒）：裁剪后长度 ÷（这项速度 × 整体速度）。

        变调也会改变长度，但那是重采样的副作用，量级不到一秒的零头，
        这里按"变速"估算就够看时间条了；真正播放用的是实测长度。
        """
        base = sr.item_src_duration(it)
        if base <= 0.0:
            return 0.0
        return base / max(0.01, float(it.rate) * float(self.cdef.rate))

    # ---- 表格 ----
    def reload_table(self) -> None:
        """重建成员表。只在成员增删/换序/换模式时调用，改数值不重建。"""
        prev = self._loading
        self._loading = True
        try:
            sel = self._current_row()
            self.table.setRowCount(0)
            names = self._sound_names()
            for row, it in enumerate(self.cdef.items):
                self.table.insertRow(row)
                num = QTableWidgetItem(str(row + 1))
                num.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, 0, num)

                self.table.setCellWidget(row, 1, self._make_sound_box(row, it, names))

                trig = QComboBox()
                for t in TRIGS:
                    trig.addItem(TRIG_LABEL.get(t, t), t)
                # 第一项的触发点必须是"组合开始时"，否则它没有上一项可参照
                if row == 0:
                    trig.setCurrentIndex(max(0, trig.findData(TRIG_COMBO)))
                    trig.setEnabled(False)
                    trig.setToolTip("第一项固定在组合触发那一刻开始")
                else:
                    trig.setCurrentIndex(max(0, trig.findData(it.trig)))
                    trig.currentIndexChanged.connect(
                        lambda _i, r=row, w=trig: self._on_trig_changed(r, w)
                    )
                self.table.setCellWidget(row, 2, trig)

                delay = QSpinBox()
                delay.setRange(DELAY_MIN_MS, DELAY_MAX_MS)
                delay.setSingleStep(50)
                delay.setSuffix(" ms")
                delay.setValue(int(it.delay_ms))
                delay.setToolTip(
                    "相对上面那个参照点的延迟。\n"
                    "正数 = 晚一点开始；负数 = 提前开始（会压到上一项的尾巴上）"
                )
                delay.valueChanged.connect(lambda v, r=row: self._on_delay_changed(r, v))
                self.table.setCellWidget(row, 3, delay)

                gain = QSpinBox()
                gain.setRange(0, 200)
                gain.setSingleStep(5)
                gain.setSuffix(" %")
                gain.setValue(int(round(it.gain * 100)))
                gain.valueChanged.connect(lambda v, r=row: self._on_gain_changed(r, v))
                self.table.setCellWidget(row, 4, gain)

                semi = QDoubleSpinBox()
                semi.setRange(-24.0, 24.0)
                semi.setSingleStep(1.0)
                semi.setDecimals(1)
                semi.setSuffix(" 半音")
                semi.setValue(float(it.semitones))
                semi.valueChanged.connect(lambda v, r=row: self._on_semi_changed(r, v))
                self.table.setCellWidget(row, 5, semi)

                rate = QSpinBox()
                rate.setRange(50, 200)
                rate.setSingleStep(5)
                rate.setSuffix(" %")
                rate.setValue(int(round(it.rate * 100)))
                rate.setToolTip("只改快慢不改音调；两行同一音效可以做\"快版/慢版\"对照")
                rate.valueChanged.connect(lambda v, r=row: self._on_rate_changed(r, v))
                self.table.setCellWidget(row, 6, rate)

                dur = QTableWidgetItem("")
                dur.setFlags(Qt.ItemIsEnabled)
                self.table.setItem(row, 7, dur)
                self._refresh_dur_cell(row)
            self.table.resizeRowsToContents()
            if sel is not None and 0 <= sel < self.table.rowCount():
                self.table.selectRow(sel)
        finally:
            self._loading = prev
        self._update_total()

    def _make_sound_box(self, row: int, it, names: list[str]) -> QComboBox:
        """音效列做成下拉框：文件被删/改名后一眼能看见，也顺手能换掉。"""
        box = QComboBox()
        if not it.sound:
            box.addItem("（未选音效）", "")
        elif it.sound not in names:
            box.addItem(f"⚠ 缺失：{Path(it.sound).stem}", it.sound)
        for n in names:
            # 带文件夹的显示成「整活/冰冰冰」，否则两首同名歌在列表里长得一样
            box.addItem(Path(n).with_suffix("").as_posix(), n)
        idx = box.findData(it.sound)
        box.setCurrentIndex(max(0, idx))
        if it.sound and it.sound not in names:
            box.setToolTip("这个文件已经不在 sounds 目录里了：换一个，或者把文件放回去")
        else:
            box.setToolTip("换这一项用的音效")
        box.currentIndexChanged.connect(
            lambda _i, r=row, b=box: self._on_sound_changed(r, b)
        )
        return box

    def _refresh_dur_cell(self, row: int) -> None:
        it = self._item_at(row)
        cell = self.table.item(row, 7)
        if it is None or cell is None:
            return
        dur = self._member_duration(it)
        if sr.lib_duration(it.sound) <= 0.0:
            cell.setText("缺失")          # 文件不在 sounds 目录里
            cell.setForeground(QColor("#ff8f8f"))
        elif dur <= 0.0:
            cell.setText("裁空了")        # 起点填到了结尾之后
            cell.setForeground(QColor("#ffb86b"))
        else:
            cell.setText(f"{dur:.2f} 秒")
            cell.setForeground(QColor("#c8cddb"))

    def _update_total(self) -> None:
        """底部一句话 + 时间条：几项、多长、缺几项、会不会叠音。"""
        items = self.cdef.items
        if not items:
            self.lbl_total.setText("还没有成员：左边双击音效加入")
            self.lbl_tl.setText("")
            self.timeline.set_spans([], 0.0)
            return
        plan = self._preview_plan()
        spans: list[tuple[int, float, float, bool]] = []
        total = 0.0
        for i, start in plan:
            dur = self._member_duration(items[i])
            ok = dur > 0.0
            spans.append((i, start, dur if ok else 0.0, ok))
            total = max(total, start + (dur if ok else 0.0))
        self.timeline.set_spans(spans, total)
        self.lbl_tl.setText(f"总时长 {total:.2f} 秒")

        miss = sum(1 for it in items if sr.lib_duration(it.sound) <= 0.0)
        empty = sum(1 for it in items
                    if sr.lib_duration(it.sound) > 0.0 and sr.item_src_duration(it) <= 0.0)
        mode = COMBO_MODE_LABEL.get(self.cdef.mode, self.cdef.mode)
        if self.cdef.mode == CM_STEP:
            # 点击式一次只响 1 项，但时间条画的是完整一轮，
            # 否则这里永远只有一根条，"谁压着谁"就看不出来了
            text = (f"{len(items)} 项 · {mode} · 一整轮约 {total:.2f} 秒"
                    f" · 每次点只响其中 1 项")
        else:
            text = (
                f"{len(items)} 项 · {mode} · 按当前条件约 {total:.2f} 秒"
                f" · {len(plan)} 项会响"
            )
        if self.cdef.mode == CM_ACC:
            text += " · 第 N 次叠前 N 项"
        if self.cdef.cooldown_ms:
            text += f" · 冷却 {self.cdef.cooldown_ms} ms"
        if self.cdef.max_voices:
            text += f" · 最多同时 {self.cdef.max_voices} 条"
        if miss:
            text += f" · ⚠ {miss} 项文件缺失"
        if empty:
            text += f" · {empty} 项被裁空"
        self.lbl_total.setText(text)

    def _preview_plan(self) -> list[tuple[int, int]]:
        """按当前设置算一遍排程（48kHz 换算，纯用来显示时间/项数）。

        随机模式这里用"前 N 项"代表一次典型抽样：真随机会让总时长
        每点一下就跳，数字看着让人心慌。
        """
        rate = 48000
        durs = {i: self._member_duration(it) for i, it in enumerate(self.cdef.items)}
        n = len(self.cdef.items)
        if self.cdef.mode == CM_RAND:
            order = list(range(min(max(1, int(self.cdef.count)), n)))
        else:
            # 顺序 / 点击 / 累加 都画完整一轮：点击式虽然一次只响 1 项，
            # 但时间条要能看出各成员怎么接龙、谁压着谁
            order = list(range(n))
        return [(i, d / rate) for i, d in
                sr.combo_plan(self.cdef.items, order, durs, rate)]

    def _sync_mode_widgets(self) -> None:
        rand = self.cdef.mode == CM_RAND
        self.lbl_count.setVisible(rand)
        self.spn_count.setVisible(rand)
        self.chk_shuffle.setVisible(rand)
        self.lbl_mode_tip.setText(COMBO_MODE_TIP.get(self.cdef.mode, ""))
        if rand and len(self.cdef.items):
            self.spn_count.setMaximum(max(1, len(self.cdef.items)))

    def _sync_combo_widgets(self) -> None:
        """把组合整体参数刷到控件上（不动 _loading 外的任何东西）。"""
        prev = self._loading
        self._loading = True
        try:
            self.spn_orate.setValue(int(round(float(self.cdef.rate) * 100)))
            self.spn_osemi.setValue(float(self.cdef.semitones))
            self.spn_orrate.setValue(int(round(float(self.cdef.rand_rate) * 100)))
            self.spn_osemi_r.setValue(float(self.cdef.rand_semi))
            self.spn_cool.setValue(int(self.cdef.cooldown_ms))
            self.spn_voices.setValue(int(self.cdef.max_voices))
            self.key_combo.set_key(self.scfg.combo_setting(self.cdef.cid).hotkey)
        finally:
            self._loading = prev

    def _sync_detail_bar(self) -> None:
        """选中行 -> 细节条（裁剪 + 逐项随机）。没选中就禁用。"""
        row = self._current_row()
        it = self._item_at(row) if row is not None else None
        prev = self._loading
        self._loading = True
        try:
            for w in (self.spn_start, self.spn_len, self.spn_rsemi, self.spn_rrate):
                w.setEnabled(it is not None)
            if it is None:
                self.lbl_sel.setText("选中项：—")
                self.spn_start.setValue(0)
                self.spn_len.setValue(0)
                self.spn_rsemi.setValue(0.0)
                self.spn_rrate.setValue(0)
            else:
                src = sr.item_src_duration(it)
                full = sr.lib_duration(it.sound)
                self.lbl_sel.setText(f"选中项 #{row + 1}")
                # 上限取"音效长度"和"已经填的起点"里更大的那个：
                # 换过更短的音效之后，控件不会把已有的值悄悄夹小、显示得跟实际不一致
                self.spn_start.setMaximum(max(int(it.clip_start_ms), int(full * 1000)))
                self.spn_len.setMaximum(max(int(it.clip_len_ms), int(full * 1000)))
                self.spn_start.setValue(int(it.clip_start_ms))
                self.spn_len.setValue(int(it.clip_len_ms))
                self.spn_rsemi.setValue(float(it.rand_semi))
                self.spn_rrate.setValue(int(round(float(it.rand_rate) * 100)))
                tip = f"原长 {full:.2f} 秒"
                if src > 0:
                    tip += f"，裁完剩 {src:.2f} 秒"
                self.spn_start.setToolTip(tip)
        finally:
            self._loading = prev

    # ---- 撤销 / 重做 ----
    def _snapshot(self) -> str:
        return json.dumps(asdict(self.cdef), ensure_ascii=False, sort_keys=True)

    def _push_undo(self) -> None:
        if self._loading:
            return
        snap = self._snapshot()
        if self._undo_stack and self._undo_stack[-1] == snap:
            return
        self._undo_stack.append(snap)
        if len(self._undo_stack) > 80:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._sync_undo_buttons()

    def _restore(self, snap: str) -> None:
        """把 cdef 就地还原成快照里的样子。

        必须原地改（不能换对象）：SettingsWindow 和 sounds.json 都握着
        同一个 ComboDef 实例，换掉就等于没保存。
        """
        try:
            data = json.loads(snap)
        except Exception:
            return
        allowed = ComboItem.__dataclass_fields__
        prev = self._loading
        self._loading = True
        try:
            self.cdef.name = str(data.get("name") or self.cdef.name)
            self.cdef.mode = str(data.get("mode") or CM_SEQ)
            self.cdef.count = int(data.get("count", self.cdef.count))
            self.cdef.shuffle = bool(data.get("shuffle", self.cdef.shuffle))
            self.cdef.rate = float(data.get("rate", 1.0))
            self.cdef.semitones = float(data.get("semitones", 0.0))
            self.cdef.rand_rate = float(data.get("rand_rate", 0.0))
            self.cdef.rand_semi = float(data.get("rand_semi", 0.0))
            self.cdef.cooldown_ms = int(data.get("cooldown_ms", 0))
            self.cdef.max_voices = int(data.get("max_voices", 0))
            self.cdef.items = [
                ComboItem(**{k: v for k, v in raw.items() if k in allowed}).clamped()
                for raw in (data.get("items") or [])
                if isinstance(raw, dict)
            ]
            self.ed_name.setText(self.cdef.name)
            self.cmb_mode.setCurrentIndex(max(0, self.cmb_mode.findData(self.cdef.mode)))
            self.spn_count.setValue(int(self.cdef.count))
            self.chk_shuffle.setChecked(bool(self.cdef.shuffle))
            self._sync_combo_widgets()
            self.reload_table()
            self._sync_mode_widgets()
            self._sync_detail_bar()
            self._update_total()
        finally:
            self._loading = prev
        self.setWindowTitle(f"编辑组合：{self.cdef.name}")
        self._commit()

    def _undo(self) -> None:
        if not self._undo_stack:
            return
        self._redo_stack.append(self._snapshot())
        self._restore(self._undo_stack.pop())
        self._sync_undo_buttons()

    def _redo(self) -> None:
        if not self._redo_stack:
            return
        self._undo_stack.append(self._snapshot())
        self._restore(self._redo_stack.pop())
        self._sync_undo_buttons()

    def _sync_undo_buttons(self) -> None:
        self.btn_undo.setEnabled(bool(self._undo_stack))
        self.btn_redo.setEnabled(bool(self._redo_stack))
        self.btn_undo.setToolTip(
            f"Ctrl+Z（还能退 {len(self._undo_stack)} 步）" if self._undo_stack
            else "没有可撤销的改动了"
        )
        self.btn_redo.setToolTip(
            f"Ctrl+Y（还能重做 {len(self._redo_stack)} 步）" if self._redo_stack
            else "没有可重做的改动了"
        )

    # ---- 顶部参数 ----
    def _push_name(self) -> None:
        if self._loading:
            return
        self._push_undo()
        self.cdef.name = self.ed_name.text().strip() or "未命名组合"
        self.setWindowTitle(f"编辑组合：{self.cdef.name}")
        self._commit()

    def _push_mode(self) -> None:
        if self._loading:
            return
        self._push_undo()
        self.cdef.mode = str(self.cmb_mode.currentData() or CM_SEQ)
        self._sync_mode_widgets()
        self.reload_table()
        self._commit()

    def _push_params(self) -> None:
        if self._loading:
            return
        self._push_undo()
        self.cdef.count = int(self.spn_count.value())
        self.cdef.shuffle = bool(self.chk_shuffle.isChecked())
        self._update_total()
        self._commit()

    def _push_combo_params(self) -> None:
        if self._loading:
            return
        self._push_undo()
        self.cdef.rate = max(0.5, min(2.0, self.spn_orate.value() / 100.0))
        self.cdef.semitones = round(float(self.spn_osemi.value()), 1)
        self.cdef.rand_rate = self.spn_orrate.value() / 100.0
        self.cdef.rand_semi = round(float(self.spn_osemi_r.value()), 1)
        self.cdef.cooldown_ms = int(self.spn_cool.value())
        self.cdef.max_voices = int(self.spn_voices.value())
        # 整体速度变了，每一项的时长都得跟着变
        for row in range(self.table.rowCount()):
            self._refresh_dur_cell(row)
        self._update_total()
        self._commit()

    def _push_hotkey(self, key: str) -> None:
        if self._loading:
            return
        self.scfg.combo_setting(self.cdef.cid).hotkey = sr.norm_spec(key)
        self._check_hotkey_conflict()
        self._commit()

    def _check_hotkey_conflict(self) -> None:
        """撞键要说出来，不能让用户按了半天没反应还以为坏了。

        自己的键不可能被别人抢走 —— 绑定表是按"先到先得"建的，
        呼出轮盘用的键优先级最高，所以这里必须显式告诉用户。
        """
        key = sr.norm_spec(self.key_combo.key_name)
        if not key:
            self.key_combo.clear_conflict()
            return
        wheel_key = sr.norm_spec((self.cfg or {}).get("hotkey", ""))
        if wheel_key and key == wheel_key:
            self.key_combo.mark_conflict(
                f"{key_label(key)} 是呼出轮盘的键，这个组合按不出来")
            return
        mine = self.scfg.combo_key(self.cdef.cid)
        for name in self.scfg.order:
            if name == mine:
                continue
            hk = sr.norm_spec(self.scfg.setting(name).hotkey)
            if hk and hk == key:
                self.key_combo.mark_conflict(
                    f"{key_label(key)} 已经被「{self.scfg.display_name(name)}」占用"
                )
                return
        self.key_combo.clear_conflict()

    # ---- 成员操作 ----
    def _add_sound(self, item) -> None:
        if len(self.cdef.items) >= MAX_COMBO_ITEMS:
            QMessageBox.information(self, "组合音效",
                                    f"一个组合最多 {MAX_COMBO_ITEMS} 项。")
            return
        name = str(item.data(Qt.UserRole) or "")
        if not name:
            return
        self._push_undo()
        it = ComboItem(sound=name, trig=TRIG_PREV_END, delay_ms=0).clamped()
        self.cdef.items.append(it)
        self.reload_table()
        self._sync_mode_widgets()
        self.table.selectRow(len(self.cdef.items) - 1)
        self._sync_detail_bar()
        self._commit()

    def _remove_item(self) -> None:
        row = self._current_row()
        if row is None:
            return
        self._push_undo()
        self.cdef.items.pop(row)
        self.reload_table()
        self._sync_mode_widgets()
        self._sync_detail_bar()
        self._commit()

    def _move_up(self) -> None:
        self._move(-1)

    def _move_down(self) -> None:
        self._move(1)

    def _move(self, delta: int) -> None:
        row = self._current_row()
        if row is None:
            return
        dst = row + delta
        if not (0 <= dst < len(self.cdef.items)):
            return
        self._push_undo()
        items = self.cdef.items
        items[row], items[dst] = items[dst], items[row]
        self.reload_table()
        self.table.selectRow(dst)
        self._sync_detail_bar()
        self._commit()

    def _current_row(self) -> int | None:
        model = self.table.selectionModel()
        rows = model.selectedRows() if model is not None else []
        if rows:
            r = rows[0].row()
            if 0 <= r < len(self.cdef.items):
                return r
        return None

    def _progress_copy(self) -> None:
        """重复递进生成器：一次生成"逐级升调/加速/延后"的一串。"""
        row = self._current_row()
        if row is None:
            QMessageBox.information(self, "递进复制", "先在表格里选一项当模板。")
            return
        room = MAX_COMBO_ITEMS - len(self.cdef.items)
        if room <= 0:
            QMessageBox.information(self, "递进复制",
                                    f"一个组合最多 {MAX_COMBO_ITEMS} 项，已经满了。")
            return
        dlg = _ProgressDialog(self)
        dlg.spn_copies.setMaximum(max(1, room))
        dlg.spn_copies.setValue(min(2, room))
        if dlg.exec() != QDialog.Accepted:
            return
        copies, dsemi, drate, ddelay = dlg.values()
        copies = max(1, min(copies, room))

        self._push_undo()
        base = self.cdef.items[row]
        new_items = []
        for k in range(1, copies + 1):
            it = ComboItem(**{k2: v for k2, v in asdict(base).items()
                              if k2 in ComboItem.__dataclass_fields__})
            it.semitones = max(-24.0, min(24.0, base.semitones + dsemi * k))
            it.rate = max(0.5, min(2.0, base.rate + drate / 100.0 * k))
            it.delay_ms = max(DELAY_MIN_MS, min(DELAY_MAX_MS, base.delay_ms + ddelay * k))
            new_items.append(it.clamped())
        self.cdef.items[row + 1:row + 1] = new_items
        self.reload_table()
        self._sync_mode_widgets()
        self.table.selectRow(row + copies)
        self._sync_detail_bar()
        self._commit()

    # ---- 逐项参数 ----
    def _item_at(self, row: int):
        if row is not None and 0 <= row < len(self.cdef.items):
            return self.cdef.items[row]
        return None

    def _on_sound_changed(self, row: int, box: QComboBox) -> None:
        if self._loading:
            return
        it = self._item_at(row)
        if it is None:
            return
        name = str(box.currentData() or "")
        if name == it.sound:
            return
        self._push_undo()
        it.sound = name
        # 下拉框是在自己的信号回调里被改的：这里重建表格会把正在发信号的
        # 控件删掉，Qt 里会直接崩。推迟到下一轮事件循环再重建。
        QTimer.singleShot(0, lambda r=row: self._after_sound_change(r))

    def _after_sound_change(self, row: int) -> None:
        self.reload_table()
        if 0 <= row < self.table.rowCount():
            self.table.selectRow(row)
        self._sync_detail_bar()
        self._commit()

    def _on_trig_changed(self, row: int, box: QComboBox) -> None:
        if self._loading:
            return
        it = self._item_at(row)
        if it is None:
            return
        self._push_undo()
        it.trig = str(box.currentData() or TRIG_PREV_END)
        self._update_total()
        self._commit()

    def _on_delay_changed(self, row: int, value: int) -> None:
        if self._loading:
            return
        it = self._item_at(row)
        if it is None:
            return
        self._push_undo()
        it.delay_ms = int(value)
        self._update_total()
        self._commit()

    def _on_gain_changed(self, row: int, value: int) -> None:
        if self._loading:
            return
        it = self._item_at(row)
        if it is None:
            return
        self._push_undo()
        it.gain = max(0.0, min(2.0, value / 100.0))
        self._commit()

    def _on_semi_changed(self, row: int, value: float) -> None:
        if self._loading:
            return
        it = self._item_at(row)
        if it is None:
            return
        self._push_undo()
        it.semitones = round(float(value), 1)
        self._refresh_dur_cell(row)
        self._update_total()
        self._commit()

    def _on_rate_changed(self, row: int, value: int) -> None:
        if self._loading:
            return
        it = self._item_at(row)
        if it is None:
            return
        self._push_undo()
        it.rate = max(0.5, min(2.0, value / 100.0))
        self._refresh_dur_cell(row)
        self._update_total()
        self._commit()

    def _on_trim_changed(self) -> None:
        row = self._current_row()
        it = self._item_at(row)
        if self._loading or it is None:
            return
        self._push_undo()
        it.clip_start_ms = int(self.spn_start.value())
        it.clip_len_ms = int(self.spn_len.value())
        self._refresh_dur_cell(row)
        self._update_total()
        self._commit()

    def _on_item_random_changed(self) -> None:
        row = self._current_row()
        it = self._item_at(row)
        if self._loading or it is None:
            return
        self._push_undo()
        it.rand_semi = round(float(self.spn_rsemi.value()), 1)
        it.rand_rate = self.spn_rrate.value() / 100.0
        self._commit()

    # ---- 试听 / 导出 ----
    def _preview_item(self) -> None:
        row = self._current_row()
        if row is None:
            QMessageBox.information(self, "试听", "先在表格里选一项。")
            return
        it = self._item_at(row)
        if it is None:
            return
        if self.engine is None or not self.engine.play_preview(it):
            QMessageBox.warning(self, "试听", "这项的音效文件不在 sounds 目录里。")

    def _preview_from_row(self) -> None:
        row = self._current_row()
        if row is None:
            QMessageBox.information(self, "试听", "先在表格里选一项。")
            return
        if self.engine is None:
            return
        if not self.engine.play_combo(self.cdef, from_row=row):
            QMessageBox.warning(self, "试听", "这一行往后都没有能出声的成员。")

    def _preview_all(self) -> None:
        if self.engine is None:
            return
        if not self.cdef.items:
            QMessageBox.information(self, "试听", "组合里还没有成员。")
            return
        # 推进式模式（按顺序点击 / 累加）下，"整个组合"指的是完整一轮：
        # 走 from_row=0 的全量分支，顺带不推进游标，试听不会打乱真实接龙位置
        if self.cdef.steps_per_trigger():
            self.engine.play_combo(self.cdef, from_row=0)
        else:
            self.engine.play_combo(self.cdef)

    def _export_wav(self) -> None:
        if self.engine is None:
            return
        if not self.cdef.items:
            QMessageBox.information(self, "导出", "组合里还没有成员。")
            return
        safe = "".join(c for c in self.cdef.name if c not in '\\/:*?"<>|').strip()
        default = str(Path(self.scfg.path).parent / f"{safe or 'combo'}.wav")
        path, _ = QFileDialog.getSaveFileName(
            self, "导出为 WAV", default, "WAV 音频 (*.wav)"
        )
        if not path:
            return
        ok, msg = self.engine.export_combo_wav(self.cdef, path)
        if ok:
            QMessageBox.information(self, "导出", msg)
        else:
            QMessageBox.warning(self, "导出", msg)

    def _commit(self) -> None:
        self.scfg.save()
        self.changed.emit()


class HotkeyPage(QWidget):
    """快捷键：轮盘热键 + 快捷动作。"""

    changed = Signal()

    def __init__(self, cfg: dict, bank: sr.SoundBank, scfg=None) -> None:
        super().__init__()
        self.cfg = cfg
        self.scfg = scfg
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 12, 0, 0)
        root.setSpacing(12)

        card1, l1 = _card("轮盘")
        self.key_wheel = KeyBox(str(cfg.get("hotkey", "y")))
        l1.addWidget(_row("呼出轮盘", self.key_wheel, "长按弹出"))
        self.hold = QSpinBox()
        self.hold.setRange(50, 1000)
        self.hold.setSingleStep(10)
        self.hold.setValue(int(cfg.get("hold_ms", 180)))
        self.hold.setSuffix(" ms")
        self.hold.setFixedWidth(110)
        l1.addWidget(_row("长按时长", self.hold, "低于此值不弹出"))

        self.tap = QComboBox()
        for label, value in (
            ("什么都不做", "none"),
            ("重复播放上一个", "repeat_last"),
            ("顺序播放下一个", "next"),
        ):
            self.tap.addItem(label, value)
        cur = str(cfg.get("tap_action", "none") or "none")
        idx = self.tap.findData(cur)
        self.tap.setCurrentIndex(max(0, idx))
        l1.addWidget(_row("轻按热键", self.tap, "短按不弹轮盘时执行"))
        tip = QLabel(
            "所有按键框都能绑鼠标：点进框里按右键 / 中键 / 侧键即可；"
            "要绑鼠标左键请双击框；点框右侧的 ✕ 取消绑定。\n"
            "想绑组合键：按住 Ctrl / Shift / Alt 再按主键，框里会显示成「Ctrl+Shift+Y」。\n"
            "呼出轮盘的框不能空着：清掉会自动退回上一个可用键。"
        )
        tip.setObjectName("Hint")
        tip.setWordWrap(True)
        l1.addWidget(tip)
        root.addWidget(card1)

        card2, l2 = _card("快捷动作")
        self.key_repeat = KeyBox(str(cfg.get("repeat_last_key", "") or ""))
        l2.addWidget(_row("重复上一个", self.key_repeat, "再按一次就再播一次"))

        self.key_cycle = KeyBox(str(cfg.get("cycle_key", "") or ""))
        l2.addWidget(_row("顺序播放", self.key_cycle, "每按一次播下一个"))

        self.key_switch = KeyBox(str(cfg.get("switch_key", "") or ""))
        l2.addWidget(_row("切换轮盘", self.key_switch,
                          "按住弹出各套轮盘，划到哪套松手切过去"))
        hint_switch = QLabel(
            "「切换轮盘」这个键是用来在存好的几套轮盘之间快速换的："
            "按住它弹出一个小轮盘，格子上写的是你存过的轮盘名，"
            "鼠标划到哪个松手就切到哪套。不设也能用——在「轮盘 → 轮盘库」里点切换。"
        )
        hint_switch.setObjectName("Hint")
        hint_switch.setWordWrap(True)
        l2.addWidget(hint_switch)
        root.addWidget(card2)

        card_start, l_start = _card("启动")
        self.chk_autosettings = QCheckBox("打开软件时自动显示这个窗口")
        self.chk_autosettings.setChecked(bool(cfg.get("open_settings_on_start", True)))
        l_start.addWidget(self.chk_autosettings)
        hint_start = QLabel(
            "勾上就是每次启动都先弹配置窗口（方便调轮盘摆位）；"
            "不勾则只在托盘里待着，要改设置就双击托盘图标。"
        )
        hint_start.setObjectName("Hint")
        hint_start.setWordWrap(True)
        l_start.addWidget(hint_start)

        # ---- 开机自启 ----
        self.chk_autostart = QCheckBox("开机自动启动")
        self.chk_autostart.setChecked(bool(cfg.get("autostart", False)))
        if not sr.autostart_supported():
            self.chk_autostart.setEnabled(False)
            self.chk_autostart.setToolTip(
                "只有打包成 exe 的版本支持开机自启；源码模式运行时不用这个。"
            )
        l_start.addWidget(self.chk_autostart)
        hint_auto = QLabel(
            "勾上后往系统注册表（当前用户的 Run 项）写一条启动记录，"
            "开机就自动进托盘。取消勾选会立刻删掉这条记录。"
            "程序挪过位置后，下次启动会自动把记录更新成新路径。"
        )
        hint_auto.setObjectName("Hint")
        hint_auto.setWordWrap(True)
        l_start.addWidget(hint_auto)
        root.addWidget(card_start)

        self.lbl_conflict = QLabel()
        self.lbl_conflict.setWordWrap(True)
        self.lbl_conflict.setStyleSheet("color:#ff8f8f;font-size:12px;")
        self.lbl_conflict.hide()
        root.addWidget(self.lbl_conflict)

        card3, l3 = _card("音效直按键")
        hint = QLabel(
            "每个音效可以单独绑一个键，按下直接播放，不用开轮盘。\n"
            "在右下角那张音效卡片的「快捷键」里设置，下面两行「触发 / 条件」\n"
            "决定它是按下就响、按住才响、松手才响，还是要先按解锁键。\n"
            "同一个键可以挂好几个音效（比如长按左键播组合、松手左键播另一句），\n"
            "各自的触发方式分别生效。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        l3.addWidget(hint)
        root.addWidget(card3)
        root.addStretch(1)

        self.key_wheel.key_changed.connect(lambda _v: self._push())
        self.key_repeat.key_changed.connect(lambda _v: self._push())
        self.key_cycle.key_changed.connect(lambda _v: self._push())
        self.key_switch.key_changed.connect(lambda _v: self._push())
        self.hold.valueChanged.connect(self._push)
        self.tap.currentIndexChanged.connect(self._push)
        self.chk_autosettings.toggled.connect(self._push)
        self.chk_autostart.toggled.connect(self._on_autostart)
        self.refresh_conflicts()

    def _bindings(self) -> list[tuple[str, KeyBox]]:
        return [
            ("呼出轮盘", self.key_wheel),
            ("重复上一个", self.key_repeat),
            ("顺序播放", self.key_cycle),
            ("切换轮盘", self.key_switch),
        ]

    def refresh_conflicts(self) -> None:
        """把"这个键已经被别人占了"显示出来。

        轮询器遇到重复绑定时会跳过后者，用户不知道就以为功能坏了
        （真实案例：重复上一个和呼出轮盘都绑成了 Y，按 Y 什么都不发生）。

        v0.9 起**音效之间共用一个键是正常用法**：像"长按左键播 AAA、
        松手左键播 B"本来就该挂在同一个键上，各自按自己的触发方式走。
        所以只在"音效撞上四个全局键"时才提示——那种情况音效会被让路。
        """
        globals_ = [(label, box.key_name) for label, box in self._bindings()
                    if box.key_name]
        # 每个键上挂了哪些音效（同一键多个是正常的，这里只是收集）
        sounds: dict[str, list[str]] = {}
        if self.scfg is not None:
            # 当前轮盘上的 + 勾了「全局通用」的（它们在任何轮盘上都会响应，
            # 撞上呼出轮盘这类全局键一样会被让路，所以必须一起算）
            groups: dict[str, list[str]] = {}
            try:
                for k, v in (self.scfg.hotkey_groups() or {}).items():
                    groups.setdefault(k, []).extend(v)
                for k, v in (self.scfg.global_hotkey_groups() or {}).items():
                    bucket = groups.setdefault(k, [])
                    for n in v:
                        if n not in bucket:
                            bucket.append(n)
            except Exception:
                groups = {}
            for key, names in groups.items():
                hk = sr.norm_spec(key)
                if not hk:
                    continue
                for n in names:
                    sounds.setdefault(hk, []).append(self.scfg.display_name(n))

        # 1) 全局键之间互相撞：只有第一个生效（老规矩）
        by_key: dict[str, list[str]] = {}
        for label, k in globals_:
            by_key.setdefault(k, []).append(label)

        lines: list[str] = []
        boxmap = dict(self._bindings())
        for label, k in globals_:
            box = boxmap[label]
            if not k:
                box.clear_conflict()
                continue
            mates = by_key.get(k, [])
            mine = mates.index(label) if label in mates else 0
            hit: list[str] = []
            if mine > 0:
                hit.append(f"「{key_label(k)}」已经被{mates[0]}占用，这里不会生效")
            if k in sounds:
                # 全局键优先，音效会让路
                hit.append(
                    f"「{key_label(k)}」上还挂着 {len(sounds[k])} 个音效"
                    f"（{'、'.join(sounds[k][:3])}{'…' if len(sounds[k]) > 3 else ''}），"
                    "全局键优先，这些音效按不出来"
                )
            if hit:
                box.mark_conflict("；".join(hit) + "。换一个键，或者把那边改掉。")
            else:
                box.clear_conflict()

        for k, names in by_key.items():
            if len(names) > 1:
                lines.append("按键冲突：" + "、".join(names)
                             + f" 都绑成了「{key_label(k)}」，只有第一个生效。")
        # 音效之间共用同一个键不算冲突，但值得说一声，免得用户以为自己设错了
        shared = {k: v for k, v in sounds.items() if len(v) > 1 and k not in by_key}
        for k, names in shared.items():
            lines.append("共用「" + key_label(k) + "」：" + "、".join(names)
                         + "（各自的触发方式分别生效，这是允许的）")

        if lines:
            self.lbl_conflict.setText("\n".join(lines))
            self.lbl_conflict.setStyleSheet("color:#ff8f8f;font-size:12px;")
            self.lbl_conflict.show()
        else:
            self.lbl_conflict.hide()

    def _on_autostart(self, on: bool) -> None:
        """开关自启：注册表立刻生效，配置里也记一份（下次启动对齐用）。"""
        self.cfg["autostart"] = bool(on)
        ok = sr.set_autostart(bool(on))
        if not ok:
            # 写注册表失败（比如被策略拦了）：把勾退回去，别让界面说谎
            self.chk_autostart.blockSignals(True)
            self.chk_autostart.setChecked(not on)
            self.chk_autostart.blockSignals(False)
            self.cfg["autostart"] = not bool(on)
            QMessageBox.warning(
                self, "开机自启",
                "写入系统注册表失败，开关没有生效。\n"
                "可能被安全软件或组策略拦住了，详情看 sr_roulette.log。"
            )
        self.changed.emit()

    def _push(self) -> None:
        if not self.key_wheel.key_name:
            # 呼出键必须有一个：清空就把框退回上一个可用值。
            # 否则会出现"框里空着、实际上还是 Y"的鬼状态，看着像清除没生效。
            self.key_wheel.set_key(str(self.cfg.get("hotkey", "y") or "y"))
        self.cfg["hotkey"] = self.key_wheel.key_name or "y"
        self.cfg["hold_ms"] = int(self.hold.value())
        self.cfg["repeat_last_key"] = self.key_repeat.key_name
        self.cfg["cycle_key"] = self.key_cycle.key_name
        self.cfg["switch_key"] = self.key_switch.key_name
        self.cfg["tap_action"] = str(self.tap.currentData() or "none")
        self.cfg["open_settings_on_start"] = bool(self.chk_autosettings.isChecked())
        self.refresh_conflicts()
        self.changed.emit()


class WheelPage(QWidget):
    """轮盘外观、手感、配色，以及"存了哪几套轮盘"。

    配色分两层：上面那张卡片调的是**应用主题色**（界面和托盘图标），
    下面轮盘库每套自带一个颜色 —— 两者互不影响，可以做到
    "界面是绿的，这套轮盘是骚粉的"。
    """

    changed = Signal()
    palette_changed = Signal(str)        # 应用主题色变了（#rrggbb）
    wheel_color_changed = Signal(str)    # 当前轮盘颜色变了（"" = 跟随主题色）
    wheel_switch = Signal(str)           # 请求切到某套轮盘（wid）

    def __init__(self, cfg: dict, scfg=None) -> None:
        super().__init__()
        self.cfg = cfg
        self.scfg = scfg
        # 和「麦克风」「说明」两页一样套一层滚动区。
        # 以前这里是 root = QVBoxLayout(self) 直接铺在标签页上，
        # 卡片一多（配色 + 轮盘库 + 手感）窗口不够高时下面就被切掉，
        # 而且没有滚动条可以拉，等于永远看不到——轮盘存多了尤其明显。
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(0, 12, 6, 0)
        root.setSpacing(12)
        scroll.setWidget(body)

        card, lay = _card("外观")

        self.radius = self._slider(int(cfg.get("wheel_radius", 180)), 120, 280, " px")
        lay.addWidget(_row("直径", self.radius, "内圈的直径"))
        self.inner = self._slider(int(float(cfg.get("inner_ratio", 0.42)) * 100), 25, 70, " %")
        lay.addWidget(_row("中空比例", self.inner, "中心留白，也是「不选中」的范围"))
        # 整体大小：内圈、中空、外圈厚度、扇区文字、中心提示一起等比缩放。
        # 和上面「直径」是叠加关系：直径决定基准尺寸，这一项决定整体放大多少。
        self.scale = self._slider(int(float(cfg.get("wheel_scale", 1.0)) * 100), 70, 140, " %")
        self.scale.setToolTip(
            "整个轮盘等比放大/缩小：内圈、外圈厚度、扇区上的文字、中心提示\n"
            "会一起变，选中判定的范围也跟着变，不会出现「看着大、选着小」。\n"
            "100% 是标准大小；屏幕小就用小一点，4K 屏看不清可以调大。\n"
            "右边那个预览不跟着这一项涨缩（它按 100% 画），实际大小以游戏内为准。"
        )
        lay.addWidget(_row("整体大小", self.scale, "内外圈和文字一起缩放"))
        self.opacity = self._slider(int(float(cfg.get("opacity", 0.94)) * 100), 40, 100, " %")
        lay.addWidget(_row("不透明度", self.opacity, "暂停提示也用这个值"))
        # 内圈装满 8 个之后轮盘外面会再长一圈，这一项控制那一圈的厚度。
        # 内圈尺寸不受影响，所以"直径"仍然是内圈的直径。
        self.outer_thick = self._slider(
            int(cfg.get("outer_thickness", 60)), 24, 140, " px"
        )
        lay.addWidget(_row("外圈厚度", self.outer_thick, "内圈满 8 个后才有外圈"))

        self.chk_names = QCheckBox("在扇区上显示音效名")
        self.chk_names.setChecked(bool(cfg.get("show_names", True)))
        lay.addWidget(self.chk_names)

        self.chk_anim = QCheckBox("开启动画")
        self.chk_anim.setChecked(bool(cfg.get("animations", True)))
        self.chk_anim.setToolTip(
            "轮盘弹出时的展开、释放音效时选中那格飞出去、暂停/恢复的提示，\n"
            "都走这一个开关。关掉之后全部变成瞬间出现、瞬间消失——\n"
            "晕动或者嫌动画挡视线就关掉。"
        )
        lay.addWidget(self.chk_anim)

        root.addWidget(card)

        # ---------------- 配色：主题色（界面）+ 轮盘色（每套各自一个） ----------------
        card_p, lay_p = _card("配色")

        self.theme_dot = QPushButton()
        self.theme_dot.setFixedSize(52, 28)
        self.theme_dot.setCursor(Qt.PointingHandCursor)
        self.theme_dot.setToolTip("点这里自由调色：界面的高亮、滑块、托盘图标都用它")
        self.theme_dot.clicked.connect(self._pick_theme_color)
        theme_row = QHBoxLayout()
        theme_row.setSpacing(8)
        theme_row.addWidget(self.theme_dot)
        for key in ("green", "orange", "blue", "purple"):
            b = QPushButton(theme.PALETTE_LABELS.get(key, key))
            b.setFixedSize(46, 28)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                "QPushButton{background:%s;color:#0d0f13;border:none;"
                "border-radius:8px;font-size:12px;font-weight:600;}"
                "QPushButton:hover{border:1px solid #ffffff;}"
                % theme.rgb_to_hex(theme.PALETTES[key])
            )
            b.clicked.connect(lambda _=False, k=key: self._pick_palette(k))
            theme_row.addWidget(b)
        theme_row.addStretch(1)
        lay_p.addWidget(_row("应用主题色", _wrap_row(theme_row)))

        self.wheel_dot = QPushButton()
        self.wheel_dot.setFixedSize(52, 28)
        self.wheel_dot.setCursor(Qt.PointingHandCursor)
        self.wheel_dot.setToolTip("只改当前这套轮盘的颜色")
        self.wheel_dot.clicked.connect(self._pick_wheel_color)
        self.chk_follow = QCheckBox("跟随主题色")
        self.chk_follow.toggled.connect(self._on_follow_theme)
        wrow = QHBoxLayout()
        wrow.setSpacing(8)
        wrow.addWidget(self.wheel_dot)
        wrow.addWidget(self.chk_follow)
        wrow.addStretch(1)
        lay_p.addWidget(_row("本套轮盘颜色", _wrap_row(wrow)))
        hint_p = QLabel(
            "上面那个是界面高亮和托盘图标的颜色；下面这个只管当前这套轮盘。"
            "每套轮盘可以各用各的颜色，勾「跟随主题色」就跟着上面那个走。"
        )
        hint_p.setObjectName("Hint")
        hint_p.setWordWrap(True)
        lay_p.addWidget(hint_p)
        root.addWidget(card_p)

        # ---------------- 轮盘库：最多 8 套，快速切换 ----------------
        card_w, lay_w = _card("轮盘库")
        hint_w = QLabel(
            "最多存 8 套轮盘。每套各自记自己的格子摆位、音效参数和颜色；"
            "「切换轮盘的轮盘」可以在游戏里直接切，不用开这个窗口。"
        )
        hint_w.setObjectName("Hint")
        hint_w.setWordWrap(True)
        lay_w.addWidget(hint_w)

        self.wheel_list = QListWidget()
        # 高度不写死：refresh_wheels 里按实际套数撑开。
        # 以前固定 150px，8 套根本放不下，得在列表里再滚一次才能看到后面几套。
        self.wheel_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.wheel_list.setMinimumHeight(84)
        self.wheel_list.currentRowChanged.connect(lambda _r: self._sync_wheel_buttons())
        self.wheel_list.itemDoubleClicked.connect(lambda _i: self._do_switch())
        lay_w.addWidget(self.wheel_list)

        wbtns = QHBoxLayout()
        wbtns.setSpacing(8)
        self.btn_w_switch = QPushButton("切换到这套")
        self.btn_w_switch.clicked.connect(self._do_switch)
        self.btn_w_new = QPushButton("另存为新轮盘")
        self.btn_w_new.clicked.connect(self._do_new_wheel)
        self.btn_w_rename = QPushButton("重命名")
        self.btn_w_rename.clicked.connect(self._do_rename_wheel)
        self.btn_w_clear = QPushButton("清空格子")
        self.btn_w_clear.clicked.connect(self._do_clear_wheel)
        self.btn_w_del = QPushButton("删除")
        self.btn_w_del.clicked.connect(self._do_delete_wheel)
        for b in (self.btn_w_switch, self.btn_w_new, self.btn_w_rename,
                  self.btn_w_clear, self.btn_w_del):
            b.setCursor(Qt.PointingHandCursor)
            wbtns.addWidget(b)
        wbtns.addStretch(1)
        lay_w.addLayout(wbtns)
        root.addWidget(card_w)

        card2, lay2 = _card("手感")
        self.sensitivity = self._slider(int(float(cfg.get("sensitivity", 0.85)) * 100), 30, 200, " %")
        lay2.addWidget(_row("鼠标灵敏度", self.sensitivity, ""))
        self.noise = self._slider(int(cfg.get("noise_floor", 2)), 0, 8, "")
        lay2.addWidget(_row("手抖过滤", self.noise, "越大越稳，但越迟钝"))
        hint_dz = QLabel(
            "中心那块白圈就是「不选中」的范围，由上面「中空比例」决定——"
            "想让它更灵敏就把中空比例调小。以前另有一个独立的「死区」滑块，"
            "和画面对不上（手还在中间、格子已经亮了），已经并进中空比例。"
        )
        hint_dz.setObjectName("Hint")
        hint_dz.setWordWrap(True)
        lay2.addWidget(hint_dz)
        root.addWidget(card2)
        root.addStretch(1)

        for w in (self.radius, self.inner, self.scale, self.opacity, self.outer_thick,
                  self.sensitivity, self.noise):
            w.slider.valueChanged.connect(self._push)
        self.chk_names.toggled.connect(self._push)
        self.chk_anim.toggled.connect(self._push)

        self.refresh_wheels()
        self._refresh_color_dots()

    # ---- 配色 ----
    def _paint_dot(self, btn: QPushButton, color: str, empty_hint: str = "") -> None:
        """把按钮画成一个色块。空颜色显示成"虚线小方块 + 文字"。"""
        if color:
            btn.setText("跟随" if empty_hint else "")
            btn.setStyleSheet(
                "QPushButton{background:%s;color:#0d0f13;font-size:11px;font-weight:600;"
                "border:2px solid %s;border-radius:8px;}"
                "QPushButton:hover{border-color:#ffffff;}"
                % (color, "#313744" if empty_hint else "#ffffff")
            )
        else:
            btn.setText(empty_hint or "—")
            btn.setStyleSheet(
                "QPushButton{background:#1a1d24;color:#8b93a3;border:1px dashed #3a414f;"
                "border-radius:8px;font-size:11px;}"
            )

    def _refresh_color_dots(self) -> None:
        cur = str(self.cfg.get("accent_color") or "#2ed36c")
        self._paint_dot(self.theme_dot, cur)
        wc = ""
        if self.scfg is not None:
            wc = self.scfg.wheel_color()
        # 跟随主题色时，色块直接显示"实际会用到的颜色"，一眼知道轮盘长什么样
        self._paint_dot(self.wheel_dot, wc or cur, "跟随" if not wc else "")
        self.chk_follow.blockSignals(True)
        self.chk_follow.setChecked(not wc)
        self.chk_follow.blockSignals(False)
        self.wheel_dot.setEnabled(bool(wc))

    def _pick_palette(self, key: str) -> None:
        rgb = theme.PALETTES.get(key, theme.DEF_ACCENT)
        hexv = theme.rgb_to_hex(rgb)
        self.cfg["accent_color"] = hexv
        self.cfg["accent_theme"] = key
        self._refresh_color_dots()
        self.palette_changed.emit(hexv)

    def _pick_theme_color(self) -> None:
        cur = theme.hex_to_rgb(str(self.cfg.get("accent_color") or "#2ed36c"))
        col = QColorDialog.getColor(QColor(*cur), self, "选择应用主题色")
        if not col.isValid():
            return
        hexv = theme.rgb_to_hex((col.red(), col.green(), col.blue()))
        self.cfg["accent_color"] = hexv
        self._refresh_color_dots()
        self.palette_changed.emit(hexv)

    def _pick_wheel_color(self) -> None:
        if self.scfg is None:
            return
        cur = theme.hex_to_rgb(self.scfg.wheel_color() or str(self.cfg.get("accent_color") or "#2ed36c"))
        col = QColorDialog.getColor(QColor(*cur), self, "选择这套轮盘的颜色")
        if not col.isValid():
            return
        hexv = theme.rgb_to_hex((col.red(), col.green(), col.blue()))
        self.scfg.set_wheel_color(hexv)
        scfg_save(self.scfg)
        self._refresh_color_dots()
        self.wheel_color_changed.emit(hexv)

    def _on_follow_theme(self, on: bool) -> None:
        if self.scfg is None or on == (self.scfg.wheel_color() == ""):
            return
        self.scfg.set_wheel_color("" if on else str(self.cfg.get("accent_color") or "#2ed36c"))
        scfg_save(self.scfg)
        self._refresh_color_dots()
        self.wheel_color_changed.emit(self.scfg.wheel_color())

    # ---- 轮盘库 ----
    def _fit_wheel_list(self) -> None:
        """让列表高度刚好放下全部轮盘（最多 8 套），不在列表内部再滚一次。

        以前这里写死 150px，8 套放不下，得先滚外层再滚列表才看得到后面几套，
        叠在一起就是"轮盘多了显示不出来"。
        """
        n = self.wheel_list.count()
        if n <= 0:
            self.wheel_list.setFixedHeight(84)
            return
        row_h = self.wheel_list.sizeHintForRow(0)
        # 构造时样式表还没套上，sizeHintForRow 会按默认行高给一个偏小的值，
        # 照它算就会少算出一截（8 套只能显示 5 套）。这里给个经验下限，
        # 样式表真正生效后 showEvent 会再校准一次。
        if row_h < 24:
            row_h = 26
        self.wheel_list.setFixedHeight(max(84, n * row_h + 18))

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # 显示时才拿得到真实行高（受样式表影响），这里再对一次
        if getattr(self, "wheel_list", None) is not None:
            self._fit_wheel_list()

    def refresh_wheels(self) -> None:
        """重建轮盘列表。当前那套加一个「正在用」标记。"""
        self.wheel_list.blockSignals(True)
        self.wheel_list.clear()
        if self.scfg is None:
            self.wheel_list.blockSignals(False)
            self._fit_wheel_list()
            self._sync_wheel_buttons()
            return
        cur = self.scfg.current
        for w in self.scfg.wheels:
            mark = "● 正在用   " if w.wid == cur else "○ "
            item = QListWidgetItem(f"{mark}{w.name or w.wid}    {len(w.order)} 个音效")
            item.setData(Qt.UserRole, w.wid)
            # 名字染成这套轮盘的颜色，方便一眼对上；但不能直接拿原色去染——
            # 用户挑了个深蓝/深紫时，文字在深色列表里就糊成一片看不见了。
            # 亮色保持原样，暗色提亮到看得清。
            rgb = theme.parse_rgb(w.color)
            if rgb is not None:
                if theme.is_light(rgb, 110):
                    item.setForeground(QColor(rgb[0], rgb[1], rgb[2]))
                else:
                    _b, light, _d = theme.derive(rgb)
                    item.setForeground(QColor(light[0], light[1], light[2]))
            self.wheel_list.addItem(item)
        # 默认选中当前那套
        for i in range(self.wheel_list.count()):
            if self.wheel_list.item(i).data(Qt.UserRole) == cur:
                self.wheel_list.setCurrentRow(i)
                break
        self.wheel_list.blockSignals(False)
        self._fit_wheel_list()
        self._sync_wheel_buttons()

    def _sel_wid(self) -> str:
        it = self.wheel_list.currentItem()
        return str(it.data(Qt.UserRole) or "") if it else ""

    def _sync_wheel_buttons(self) -> None:
        wid = self._sel_wid()
        cur = self.scfg.current if self.scfg is not None else ""
        total = len(self.scfg.wheels) if self.scfg is not None else 0
        self.btn_w_switch.setEnabled(bool(wid) and wid != cur)
        self.btn_w_new.setEnabled(total < 8)
        self.btn_w_rename.setEnabled(bool(wid))
        self.btn_w_clear.setEnabled(bool(wid))
        self.btn_w_del.setEnabled(total > 1 and bool(wid))

    def _do_switch(self) -> None:
        wid = self._sel_wid()
        if not wid or self.scfg is None or wid == self.scfg.current:
            return
        self.wheel_switch.emit(wid)

    def _do_new_wheel(self) -> None:
        if self.scfg is None:
            return
        if len(self.scfg.wheels) >= 8:
            QMessageBox.information(self, "轮盘库", "最多只能存 8 套轮盘。\n先删一套再用。")
            return
        name, ok = QInputDialog.getText(
            self, "另存为新轮盘",
            "新轮盘的名字（会完整复制当前这套的格子、参数和颜色）：",
            text=f"轮盘 {len(self.scfg.wheels) + 1}",
        )
        if not ok or not name.strip():
            return
        w = self.scfg.new_wheel(name.strip(), copy_current=True)
        if w is None:
            return
        scfg_save(self.scfg)
        self.refresh_wheels()
        self.changed.emit()

    def _do_rename_wheel(self) -> None:
        wid = self._sel_wid()
        if self.scfg is None or not wid:
            return
        w = self.scfg.wheel_by_id(wid)
        if w is None:
            return
        name, ok = QInputDialog.getText(self, "重命名轮盘", "新名字：", text=w.name)
        if not ok or not name.strip():
            return
        if self.scfg.rename_wheel(wid, name):
            scfg_save(self.scfg)
            self.refresh_wheels()
            self.changed.emit()

    def _do_clear_wheel(self) -> None:
        wid = self._sel_wid()
        if self.scfg is None or not wid:
            return
        w = self.scfg.wheel_by_id(wid)
        if w is None or not w.order:
            return
        ans = QMessageBox.question(
            self, "清空格子",
            f"把「{w.name}」上的 {len(w.order)} 个音效全部撤下来？\n"
            "音效文件和参数都还在，只是这套轮盘变空。",
        )
        if ans != QMessageBox.Yes:
            return
        if self.scfg.clear_wheel(wid):
            scfg_save(self.scfg)
            self.refresh_wheels()
            self.changed.emit()

    def _do_delete_wheel(self) -> None:
        wid = self._sel_wid()
        if self.scfg is None or not wid:
            return
        w = self.scfg.wheel_by_id(wid)
        if w is None or len(self.scfg.wheels) <= 1:
            return
        ans = QMessageBox.question(
            self, "删除轮盘",
            f"删掉「{w.name}」这套轮盘？\n"
            "只删这套的摆位和参数，音效文件不会动。",
        )
        if ans != QMessageBox.Yes:
            return
        if self.scfg.delete_wheel(wid):
            scfg_save(self.scfg)
            self.refresh_wheels()
            self.changed.emit()

    def _push(self) -> None:
        self.cfg["wheel_radius"] = int(self.radius.slider.value())
        self.cfg["inner_ratio"] = self.inner.slider.value() / 100.0
        self.cfg["wheel_scale"] = self.scale.slider.value() / 100.0
        self.cfg["opacity"] = self.opacity.slider.value() / 100.0
        self.cfg["outer_thickness"] = int(self.outer_thick.slider.value())
        self.cfg["show_names"] = bool(self.chk_names.isChecked())
        self.cfg["animations"] = bool(self.chk_anim.isChecked())
        self.cfg["sensitivity"] = self.sensitivity.slider.value() / 100.0
        self.cfg["noise_floor"] = int(self.noise.slider.value())
        self.changed.emit()

    @staticmethod
    def _slider(value: int, lo: int, hi: int, suffix: str) -> QWidget:
        """滑块 + 数值联动的一行。"""
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        sl = QSlider(Qt.Horizontal)
        sl.setRange(lo, hi)
        sl.setValue(value)
        val = QLabel(f"{value}{suffix}")
        val.setFixedWidth(58)
        val.setStyleSheet(f"color:{accent_hex()};font-size:12px;font-weight:600;")
        sl.valueChanged.connect(lambda v: val.setText(f"{v}{suffix}"))
        lay.addWidget(sl, 1)
        lay.addWidget(val)
        wrap.slider = sl          # 供后续取值
        wrap.value_label = val
        return wrap


class MicPage(QWidget):
    """麦克风注入：把音效混进游戏语音。

    这一页也负责"设备检测"：没装虚拟声卡的时候要明确告诉用户缺什么，
    而不是让功能悄悄不生效——那种"点了没反应"最容易让人以为软件坏了。
    """

    changed = Signal()          # 结构变化（开关/换设备），主程序据此重建链路
    level_changed = Signal(float)

    def __init__(self, cfg: dict, engine=None) -> None:
        super().__init__()
        self.cfg = cfg
        self.engine = engine
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(0, 12, 6, 0)
        root.setSpacing(12)
        scroll.setWidget(body)

        # ---- 开关与设备 ----
        card, lay = _card("麦克风注入")

        self.chk_enable = QCheckBox("把音效送进游戏语音（需要虚拟声卡）")
        self.chk_enable.setChecked(bool(cfg.get("mic_enabled", False)))
        lay.addWidget(self.chk_enable)

        self.cmb_mic = QComboBox()
        lay.addWidget(_row("采集麦克风", self.cmb_mic))
        self.cmb_cable = QComboBox()
        lay.addWidget(_row("虚拟声卡", self.cmb_cable))

        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_refresh = QPushButton("重新检测设备")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.btn_refresh)
        row.addStretch(1)
        lay.addLayout(row)

        self.lbl_status = _WrapLabel("")
        self.lbl_status.setObjectName("Hint")
        lay.addWidget(self.lbl_status)
        root.addWidget(card)

        # ---- 音量 ----
        card2, lay2 = _card("音量")
        self.snd_gain = WheelPage._slider(
            int(float(cfg.get("cable_effect_gain", 1.0)) * 100), 0, 150, " %"
        )
        lay2.addWidget(_row("音效·送对方", self.snd_gain))
        self.mic_gain = WheelPage._slider(int(float(cfg.get("mic_gain", 0.9)) * 100), 0, 200, " %")
        lay2.addWidget(_row("原声·送对方", self.mic_gain))
        self.chk_monitor = QCheckBox("音效也从自己的耳机里放出来（自己能听见）")
        self.chk_monitor.setChecked(bool(cfg.get("monitor_enabled", True)))
        lay2.addWidget(self.chk_monitor)
        self.mon_gain = WheelPage._slider(int(float(cfg.get("volume", 0.8)) * 100), 0, 150, " %")
        lay2.addWidget(_row("本地监听", self.mon_gain))
        self.latency = WheelPage._slider(int(cfg.get("mic_latency_ms", 60)), 20, 200, " ms")
        lay2.addWidget(_row("缓冲余量", self.latency, "越大越抗卡顿，但更延迟"))
        root.addWidget(card2)

        # ---- 说话测试 ----
        card3, lay3 = _card("说话测试")
        h = _WrapLabel(
            "点下面的按钮，随便说一句话。绿色条跟着你的声音动，"
            "就说明麦克风采集正常。\n"
            "程序不挑麦克风：蓝牙耳麦那种 16kHz 单声道的设备也能用，会自动转成"
            "内部需要的 48kHz 立体声。\n"
            "同一台麦克风会先把能试的格式全试一遍（48k 立体声 → 单声道 → 44.1k → 16k），"
            "才轮到换下一台；有些设备嘴上说支持、真打开却拒绝，这种也能自动退到能用的那一档。"
        )
        h.setObjectName("Hint")
        lay3.addWidget(h)

        row3 = QHBoxLayout()
        row3.setSpacing(10)
        self.btn_test = QPushButton("开始测试")
        self.btn_test.setCursor(Qt.PointingHandCursor)
        self.meter = QProgressBar()
        self.meter.setRange(0, 100)
        self.meter.setValue(0)
        self.meter.setTextVisible(False)
        self.meter.setFixedHeight(10)
        self.meter.setStyleSheet(
            "QProgressBar{background:#20242e;border:none;border-radius:5px;}"
            f"QProgressBar::chunk{{background:{accent_hex()};border-radius:5px;}}"
        )
        row3.addWidget(self.btn_test)
        row3.addWidget(self.meter, 1)
        lay3.addLayout(row3)
        root.addWidget(card3)

        # ---- 怎么用 ----
        card4, lay4 = _card("怎么用")
        steps = _WrapLabel(
            "1. 在上面选中你平时说话的麦克风，再选 CABLE Input 当虚拟声卡\n"
            "2. 勾上最上面的开关\n"
            "3. 进游戏/语音软件的设置，把「麦克风」选成 CABLE Output\n"
            "4. 说话的同时按音效键，对方就能同时听到你说话和音效\n\n"
            "注意：请戴耳机。外放音箱的话，音效会被麦克风再录一遍，"
            "对方会听到带回声的双重音效。"
        )
        steps.setObjectName("Hint")
        lay4.addWidget(steps)
        root.addWidget(card4)
        root.addStretch(1)

        # ---- 事件 ----
        self.chk_enable.toggled.connect(self._push)
        self.chk_monitor.toggled.connect(self._push)
        self.cmb_mic.currentIndexChanged.connect(self._on_device_changed)
        self.cmb_cable.currentIndexChanged.connect(self._on_device_changed)
        self.btn_refresh.clicked.connect(self.refresh_devices)
        self.btn_test.clicked.connect(self._toggle_test)
        for w in (self.snd_gain, self.mic_gain, self.mon_gain, self.latency):
            w.slider.valueChanged.connect(self._push)

        self.refresh_devices()

    # ---- 设备 ----
    def refresh_devices(self) -> None:
        """重新枚举设备。插拔之后点「重新检测设备」走这里。"""
        self.cmb_mic.blockSignals(True)
        self.cmb_cable.blockSignals(True)
        self.cmb_mic.clear()
        self.cmb_cable.clear()

        mics = sr.real_inputs()
        only_virtual = False
        if not mics:
            # 一个真麦克风都没筛出来（只装了虚拟声卡 / 名字撞了关键字）。
            # 空着显示"没检测到麦克风"等于让人无路可走，改为全列出来并标清楚原因。
            mics = sr.all_inputs()
            only_virtual = True
        for dev in mics:
            name = dev.description()
            if only_virtual:
                name += "（虚拟设备，选它对方听不到你说话）"
            self.cmb_mic.addItem(name, dev.description())
        if not mics:
            self.cmb_mic.addItem("（没检测到麦克风）", "")

        cables = sr.virtual_outputs()
        for dev in cables:
            self.cmb_cable.addItem(dev.description(), dev.description())
        if not cables:
            self.cmb_cable.addItem("（没装虚拟声卡）", "")

        # 选回配置里记的那个；没记就用自动挑的结果
        cur_mic = str(self.cfg.get("mic_device") or "")
        pick = cur_mic if cur_mic else ""
        if not pick:
            auto = sr.guess_capture_input("")
            pick = auto.description() if auto is not None else ""
        self._select(self.cmb_mic, pick)

        cur_cable = str(self.cfg.get("cable_device") or "")
        if not cur_cable:
            auto = sr.guess_virtual_output("")
            cur_cable = auto.description() if auto is not None else ""
        self._select(self.cmb_cable, cur_cable)

        self.cmb_mic.blockSignals(False)
        self.cmb_cable.blockSignals(False)
        self._refresh_status()

    @staticmethod
    def _select(box: QComboBox, name: str) -> None:
        idx = box.findData(name)
        if idx >= 0:
            box.setCurrentIndex(idx)
        elif box.count():
            box.setCurrentIndex(0)

    def _refresh_status(self) -> None:
        have_cable = bool(sr.virtual_outputs())
        lines = []
        # 装了 VB-CABLE 之后，Windows 的默认录音设备会被改成 CABLE Output。
        # 这时候如果不开注入，对方听到的是"虚拟声卡的回放端"，也就是一片静音——
        # 这个坑必须当面提示，否则会以为是自己麦克风坏了。
        default_in = QMediaDevices.defaultAudioInput()
        if (
            default_in is not None
            and sr.is_virtual_name(default_in.description())
            and not self.chk_enable.isChecked()
        ):
            lines.append("⚠ 系统默认录音设备已是虚拟声卡，不勾开关对方会听不到你说话")
        if not have_cable:
            lines.append("⚠ 没检测到虚拟声卡，音效送不进游戏语音。")
            lines.append("装 VB-CABLE（免费）后重启电脑，再点「重新检测设备」。")

        st = self.engine.audio_status() if self.engine is not None else {}
        mic = st.get("mic") or str(self.cmb_mic.currentText() or "")
        cable = st.get("cable") or str(self.cmb_cable.currentText() or "")
        if mic and self.cmb_mic.currentData():
            lines.append(f"采集：{mic}"
                         + (f"（{st['note']}）" if st.get("note") else ""))
        if cable and self.cmb_cable.currentData():
            lines.append(f"送声：{cable}")
        if st.get("error"):
            lines.append(f"⚠ {st['error']}")
        if st.get("cable_error"):
            lines.append(f"⚠ {st['cable_error']}")
        if not self.chk_enable.isChecked():
            lines.append("当前未启用：勾上最上面的开关才会送声")
        lines.append(f"估算延迟：约 {float(self.cfg.get('mic_latency_ms', 60)) + 60:.0f} ms"
                     "（你说话到对方听到）")
        self._set_status(lines)

    def _set_status(self, lines: list[str]) -> None:
        """换一段状态文字（高度由 _WrapLabel 自己撑）。"""
        self.lbl_status.setText("\n".join(lines))

    def _on_device_changed(self) -> None:
        self._push()

    # ---- 说话测试 ----
    def _toggle_test(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self.meter.setValue(0)
            self.btn_test.setText("开始测试")
            # 测试开着的那路采集这时候没人用了：不放掉的话，麦克风会一直被占用
            # （Windows 任务栏那个"正在使用麦克风"的图标一直亮着）。
            # 注意只在没开注入时放：开着注入时采集是人声的输入源，关掉等于把人声掐了。
            if self.engine is not None and not self.chk_enable.isChecked():
                self.engine.release_capture()
                self._refresh_status()
            return
        if self.engine is None:
            self.lbl_status.setText("⚠ 音频引擎没接上，无法测试")
            return
        ok = self.engine.restart_capture()
        self._refresh_status()
        if not ok:
            self.btn_test.setText("开始测试")
            return
        self.btn_test.setText("停止测试")
        self._timer.start()

    def _tick(self) -> None:
        if self.engine is None:
            return
        lv = self.engine.mic_level()
        # 平方一下更好看：小声也看得出来在动，大声才顶到满
        self.meter.setValue(int(min(1.0, lv * 3.0) ** 0.6 * 100))

    # ---- 写回配置 ----
    def _push(self) -> None:
        self.cfg["mic_enabled"] = bool(self.chk_enable.isChecked())
        self.cfg["monitor_enabled"] = bool(self.chk_monitor.isChecked())
        self.cfg["mic_device"] = str(self.cmb_mic.currentData() or "")
        self.cfg["cable_device"] = str(self.cmb_cable.currentData() or "")
        self.cfg["cable_effect_gain"] = self.snd_gain.slider.value() / 100.0
        self.cfg["mic_gain"] = self.mic_gain.slider.value() / 100.0
        self.cfg["volume"] = self.mon_gain.slider.value() / 100.0
        self.cfg["mic_latency_ms"] = int(self.latency.slider.value())
        self._refresh_status()
        self.changed.emit()


# ---------------------------------------------------------------- 说明页

class _FoldSection(QWidget):
    """可折叠的一节：标题一行，点开才展开内容。

    内容统一用纯文本 QLabel。_WrapLabel 的自动撑高是按字体度量量纯文本算的，
    富文本（带标签的字符串）会被量错、结果切掉半截；需要链接的地方单独放控件。
    """

    def __init__(self, title: str, expanded: bool = False, hot: bool = False) -> None:
        super().__init__()
        self.title = title
        self.hot = bool(hot)          # True = 这一节用应用主题色标出来
        self._labels: list[_WrapLabel] = []

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.head = QPushButton(self._head_text(False))
        self.head.setObjectName("FoldHead")
        self.head.setCheckable(True)
        self.head.setCursor(Qt.PointingHandCursor)
        v.addWidget(self.head)

        self.body = QFrame()
        self.body.setObjectName("FoldBody")
        self.bl = QVBoxLayout(self.body)
        self.bl.setContentsMargins(14, 6, 12, 14)
        self.bl.setSpacing(7)
        v.addWidget(self.body)

        if self.hot:
            # QSS 用 [hot="true"] 选中这两个控件；属性得在套样式表前设好
            for w in (self.head, self.body):
                w.setProperty("hot", True)

        self.head.toggled.connect(self.set_expanded)
        self.set_expanded(expanded)

    def _head_text(self, on: bool) -> str:
        return ("▼  " if on else "▶  ") + self.title

    def para(self, text: str, kind: str = "text") -> "_WrapLabel":
        """加一段文字。kind: head / text / hint。"""
        lab = _WrapLabel(text)
        lab.setObjectName({"head": "DocHead", "hint": "Hint"}.get(kind, "DocText"))
        lab.setTextInteractionFlags(Qt.TextSelectableByMouse)   # 想复制哪句都能选中
        self.bl.addWidget(lab)
        self._labels.append(lab)
        return lab

    def add_widget(self, w: QWidget) -> None:
        self.bl.addWidget(w)

    def set_expanded(self, on: bool) -> None:
        on = bool(on)
        self.head.blockSignals(True)
        self.head.setChecked(on)
        self.head.setText(self._head_text(on))
        self.head.blockSignals(False)
        self.body.setVisible(on)
        if on:
            # 刚展开时宽度还没定，量出来的高度偏小会把多行文字切掉；
            # 先量一遍，再等布局跑完一轮补一次
            for lab in self._labels:
                lab._fit()
            QTimer.singleShot(0, self._refit)

    def _refit(self) -> None:
        for lab in self._labels:
            lab._fit()


class HelpPage(QWidget):
    """说明页：安全声明 / 开发者说明 / 使用教程 / 常见问题。

    全部是静态文字，不和配置、音频、文件系统打交道 —— 这一页不会成为
    新的故障源，也不会因为用户点了几下就改变程序状态。
    """

    def __init__(self) -> None:
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(0, 12, 6, 8)
        root.setSpacing(10)
        scroll.setWidget(body)
        self.root_lay = root
        self.scroll = scroll

        # ---- 顶部：一句话 + 全部展开 / 收起 ----
        top = QFrame()
        top.setObjectName("Card")
        tl = QVBoxLayout(top)
        tl.setContentsMargins(14, 12, 14, 12)
        tl.setSpacing(8)
        tip = _WrapLabel(
            "作者：迟昼（b站账号：缪缪缪尔赛思）\n"
            "该软件仅供娱乐，安全性请使用者自行判断。"
        )
        tip.setObjectName("DocText")
        tl.addWidget(tip)
        root.addWidget(top)

        self.sections: list[_FoldSection] = []

        # ================= 一、安全声明 =================
        s1 = self._new_section("一、安全声明")
        s1.para(
            "该软件仅供娱乐，它的功能实现是通过读你的按键、播放你放进去的音效、"
            "最后把声音送到声卡。该软件不联网、不注入、不模拟按键，安全性请使用者"
            "自行判断，如若因滥用而发生封号事件，与软件作者无关。"
        )
        s1.para("它做了什么（可自行核对）", "head")
        s1.para(
            "· 收按键：用 Windows 官方的 Raw Input 接口 + 系统按键状态轮询。\n"
            "  只读，不拦截、不屏蔽、不转发、不模拟 —— 游戏收到的输入和没装它时完全一样。\n"
            "· 放声音：只读本文件夹 sounds 里的音频和 config.json / sounds.json，"
            "在本机解码、混音、送到声卡。\n"
            "· 送语音（可选）：开「把音效送进游戏语音」后，麦克风音频只在内存里实时混合，用完即丢。\n"
            "· 不写系统目录、不写 AppData、不装驱动、不装证书、不调用外部命令。"
        )
        s1.para("它写了哪些文件（可自行核对）", "head")
        s1.para(
            "· config.json —— 你的设置\n"
            "· sounds.json —— 轮盘摆位、每个音效的参数、组合音效、你的多套轮盘\n"
            "· sr_roulette.log —— 排障日志（纯文本，随时可删，下次运行自动重建）\n"
            "· 导出的 WAV —— 只有你点「导出 WAV」时，才会写到你选的位置"
        )
        s1.para(
            "注册表只在你自己打开「开机自动启动」时写一条："
            "HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run "
            "下名为 SR Voiceover Roulette 的值，内容是本程序的路径。"
            "关掉开关立刻删除，不动其它任何键，默认就是关的。"
        )
        s1.para(
            "日志里记的是音频设备型号、音量与缓冲参数、被按下的按键名"
            "（如 y、mouse_left）、音效解码与播放过程。"
            "不记录你输入的文字、聊天内容和任何录音，也不会外传。"
        )
        s1.para(
            "想核验：任务管理器 →「资源监视器」→ 网络，看不到它建立连接；"
            "注册表里搜 SR Voiceover Roulette，只有开过自启才有那一条。",
            "hint",
        )
        s1.para("必要提醒", "head")
        s1.para(
            "· 这是第三方工具，和游戏官方没有任何关系，"
            "也给不了「官方允许使用」这种资格。\n"
            "· 用任何第三方程序介入游戏过程，都可能与游戏用户协议冲突，"
            "理论上存在被警告、限权、封号的可能，风险由你判断并承担。\n"
            "· 在竞技对局里用音效误导对手是否属于不正当行为，由你和平台判断。"
        )

        # ================= 二、开发者说明 =================
        s2 = self._new_section("二、开发者说明")
        s2.para("作者：迟昼（B 站账号：缪缪缪尔赛思）")
        s2.para(
            "性质：免费的个人项目，不是商品。不收费、不办会员、不做引流、不接定制。"
        )
        s2.para("该软件为 AI 项目", "head")
        s2.para(
            "这个项目的代码是在 AI 辅助下写成的。需求、方案取舍、逐段审查、"
            "实机测试和最终判断由作者负责；大量具体代码由 AI 生成，"
            "作者验证通过后才合并进版本。"
        )
        s2.para("更新节奏", "head")
        s2.para(
            "按需更新。不承诺周期，不承诺修复任何特定问题。"
            "严重问题会修，小毛病可能一直放着。"
        )
        s2.para("反馈", "head")
        s2.para("B 站私信或评论区。由于作者较忙，回复慢或漏看评论请见谅。")
        s2.para("分发", "head")
        s2.para(
            "只从作者发布的渠道下载。别人重新打包的副本可能被改动（捆绑、植入），"
            "本说明的所有承诺只对作者提供的原始文件有效。"
            "请不要去掉或篡改安全声明后二次发布，更不要拿去卖，"
            "因此造成的任何损失作者不会负责。"
        )
        s2.para("音效素材", "head")
        s2.para(
            "sounds 目录里的音频不是本程序的原创作品，多为网络公开片段，"
            "适合个人私下娱乐。直播、录播、投稿、二创等公开场合使用，请自行确认授权。"
        )

        # ================= 三、详细使用教程 =================
        s3 = self._new_section("三、详细使用教程")
        steps = [
            (
                "1｜装好就能用",
                "解压到任意文件夹（中文路径也能用）→ 双击 SR Voiceover Roulette.exe → "
                "会弹 UAC 问「是否允许此应用对你的设备进行更改」，点「是」"
                "（程序需要管理员权限，否则在管理员身份的游戏前读不到按键）→ "
                "首次运行 Windows 可能还拦一下，点「更多信息」→「仍要运行」→ "
                "托盘出现一个圆环图标（颜色跟你设的应用主题色一致），不会弹窗口。",
            ),
            (
                "2｜放进你的音效",
                "托盘图标右键 →「打开 sounds 目录」→ 丢入 wav / mp3 / flac / ogg / m4a → "
                "再右键「重新扫描 sounds 目录」。建议按 01 xxx.wav 这样命名，列表会按名字排序。\n"
                "音效多了就建子文件夹分类（sounds/整活/、sounds/整活/尖叫/ 都行，几层都认），"
                "音效库会按文件夹分好组显示，每组标题写着有几个；不同文件夹里可以有同名文件。"
                "每个格子右边会显示时长（wav 瞬间读出，mp3 等首次读一下就好）。",
            ),
            (
                "3｜拖上轮盘",
                "设置窗口 →「音效库」→ 把音效拖到轮盘格子上。内圈 8 格，满了自动用外圈，最多 20 格。"
                "拖到中间圆 = 追加到末尾；把轮盘上的格子拖回音效库 = 下盘（文件还在）。\n"
                "压缩包里已经排好一组示例，随便改。你自己删掉或下盘的音效不会自己补回来"
                "（想把整盘重置，就删掉 sounds.json 再启动）。",
            ),
            (
                "4｜实战怎么按",
                "长按 Y（默认 0.25 秒）→ 轮盘出现 → 鼠标划方向 → 松开就播。\n"
                "圆点在正中松手：正在响就停掉，同时软件进入暂停（所有快捷键暂时失效）。"
                "解除有两条路：再按住热键、在中心松手一次；或者直接在轮盘上选个音效，播完顺手就恢复了。\n"
                "暂停期间轮盘键和「切换轮盘」的键都照常能用（它们不发声，不算破例），"
                "换一套轮盘之后仍然是暂停状态，不会把暂停顺手解掉。\n"
                "轮盘弹着时点鼠标左键 / 右键：立刻收起，什么都不播，这一按也不会再弹。\n"
                "单击 Y：直接重播上一个，不开轮盘。",
            ),
            (
                "5｜调每个音效",
                "右下卡片里能调：音量、变调（不改变 / 连续升调 / 连续降调 / 每次随机 / 固定变调）、"
                "变调幅度、速度（不改 / 加快 / 变慢）、连击窗口、单独的快捷键。\n"
                "例子：设成「升调 ±2 半音、窗口 2500ms」，2.5 秒内连按三次就是原调 → +2 → +4；"
                "停手超过 2.5 秒，下次又从原调开始。",
            ),
            (
                "6｜多套轮盘（最多 8 套）",
                "「轮盘」页右侧「轮盘库」里一行一套：点「另存为新轮盘」把当前这套复制一份再改名，"
                "「切换到这套」立刻换过去，「重命名 / 清空 / 删除」按需用（最后一套删不掉）。\n"
                "每套各自记着自己的格子布局、每个格子的音量/变调/速度/热键，还有这套自己的颜色，"
                "切过去就是完整的一套，不用重新调。\n"
                "切换还有两种快法：托盘右键 →「轮盘」子菜单直接选；或者按住「切换轮盘」热键"
                "（在「快捷键」页绑，默认不绑），屏幕中间弹出选择器，鼠标指向哪套松手就是哪套，"
                "正在响的音效不会被打断。\n"
                "选择器里一圈都是轮盘名，鼠标指到哪一格，"
                "那一整块就亮成它自己的颜色，中间的名字和鼠标点也跟着变色，",
            ),
            (
                "7｜配色（应用主题色 / 轮盘颜色是两回事）",
                "「轮盘」页上方「配色」：\n"
                "· 应用主题色 —— 整个设置窗口的配色（按钮、进度条、高亮全跟着它变）\n"
                "· 本套轮盘颜色 —— 只决定这个轮盘画出来是什么颜色\n"
                "两边都能点「选取…」自己调，不再是只有绿橙蓝紫四个死选项；下面四个小圆点是快捷预设。"
                "勾「跟随主题色」就一直是应用那个色，不勾可以单独设。",
            ),
            (
                "8｜组合音效",
                "「音效库」页最底部 →「＋ 新建组合」→ 左边双击加入（同一音效可以重复加）→ "
                "每一行设触发条件、延迟、音量、变调、速度 → 拖上轮盘，或者给它绑个专属热键。\n"
                "音效多到要翻半天？左边列表上方有搜索框，打几个字就筛出匹配项并自动滚到第一个，"
                "按回车直接加进组合。\n"
                "两个现成配方：① A 原版 → 0.2 秒后 A 升调加速 → 再 0.2 秒后 A 降调减速 → A 播完接 B；"
                "② ABCD 每次随机抽 3 个、间隔 1 秒。",
            ),
            (
                "9｜让队友也听到",
                "先装虚拟声卡 VB-CABLE（官方下载页见下）→ 到「麦克风」页：采集选你平时说话的麦克风，"
                "虚拟声卡选 CABLE Input → 进游戏或语音软件，把麦克风设成 CABLE Output → "
                "回本页调「音效·送对方 / 原声·送对方 / 本地监听 / 缓冲余量」。",
            ),
            (
                "10｜其它",
                "导出 WAV（可丢进剪辑软件）、开机自动启动开关、换电脑时整个文件夹拷走即可"
                "（配置和音效都在里面）。",
            ),
        ]
        for i, (head, text) in enumerate(steps):
            s3.para(head, "head")
            s3.para(text)
            if i == 8:
                s3.add_widget(self._link_row("VB-CABLE 下载页：", "https://vb-audio.com/Cable/"))

        # ---- 补充：触发方式与条件解锁（v0.9）----
        s3.para("补充｜触发方式与条件解锁", "head")
        s3.para(
            "右下那张卡片多了两行：「触发」和「条件」。它们决定快捷键按下之后"
            "到底什么时候响、什么时候停，以及要不要先按解锁键。"
        )
        s3.para("触发（四选一）", "head")
        s3.para(
            "· 点击触发（默认）：按下就响一次，松手不管。和以前的版本完全一样。\n"
            "· 长按触发：按住一直响，松手立刻停；再按一次会从头开始。"
            "适合引擎声、警报这种「按住才有」的声音。\n"
            "· 松手触发：按下不出声，松手的那一下才响。常和长按触发配对，"
            "做成「按住放前奏、松手接下一句」。\n"
            "· 长按连续触发：按下先响一次，之后只要还按着，就每隔一段时间"
            "「再点一次」，间隔在那个 ms 框里调（50~2000）。\n"
            "　 连击变调和变速会跟着一次次累加，所以按住不放就能做出"
            "「越连越高的鬼畜」效果。整段按住只算 1 次点击，不会把解锁次数扣光。"
        )
        s3.para("条件（两档）", "head")
        s3.para(
            "· 无条件（默认）：按了就能响。\n"
            "· 条件解锁：先按一下「解锁键」，这个音效才能在「解锁时间」内、"
            "「解锁次数」内被触发。\n"
            "　 解锁时间 0（显示「不限时」）= 一直有效，直到次数用完；\n"
            "　 解锁次数 0（显示「不限次」）= 只看时间；\n"
            "　 两个都 0 = 按一次解锁键，之后永远能用（留神别一直开着）。\n"
            "　 时间到了只是「不能再触发新的」，正在响的声音会继续响完，不会被掐断。\n"
            "　 同一个解锁键按一下，名下所有音效一起放开，各自算各自的时间和次数；"
            "重复按是刷新，不叠加。"
        )
        s3.para("一个现成玩法：长按播组合、松手播另一句", "head")
        s3.para(
            "1. 建组合「AAA」，挂鼠标左键，「触发」选长按触发；「条件」选条件解锁，"
            "解锁键 G、解锁时间 5000ms、次数不限。\n"
            "2. 建音效「B」，也挂鼠标左键，「触发」选松手触发；「条件」同样选条件解锁，"
            "解锁键 G、不限时、次数 1。\n"
            "3. 效果：不按 G 时点左键什么都不发生；按一下 G 之后长按左键，AAA 起播，"
            "松手 AAA 停、同时播 B。\n"
            "4. 就算按完 G 过了 4.9 秒才按下左键，AAA 也照样能响 —— 解锁只决定"
            "「能不能开始」，不负责「掐断」。\n"
            "注意：一个键挂好几个音效是允许的，上面这种就是两个音效共用一个键，"
            "各自的触发方式分别生效。"
        )

        # ---- 补充：全局通用（v0.9）----
        s3.para("补充｜全局通用（快捷键不跟轮盘走）", "head")
        s3.para(
            "每个音效的「快捷键」框右边都有一个「全局通用」勾选框。默认不勾，"
            "这时这个快捷键只在它所在的那套轮盘上使用。\n"
            "勾上之后就不一样了：切换到别的轮盘，按这个键照样能触发它 —— "
            "适合「不管在用哪套轮盘，这几个声音都想随手按得到」的情况。\n"
            "· 勾了之后，它的音量、变调、长按方式仍然按它自己那套轮盘的设置来，"
            "不会因为切了轮盘就变回默认值。\n"
            "· 没绑快捷键时勾了也不起作用，鼠标停在勾选框上会有提示。\n"
            "· 组合音效也有这一项。组合的定义是所有轮盘共用的，但它绑的那个键"
            "在别的轮盘上还算不算数，仍然单独决定 —— 勾上之后，在别的轮盘按它"
            "也能把这条组合放出来。\n"
            "· 如果这个键同时被「呼出轮盘」「重复上一个」这类全局键占着，"
            "音效仍然会让路（按下不响），「快捷键」页顶部会标出来。"
        )

        # ================= 四、常见问题 =================
        # 默认展开 + 主题色高亮：小白遇到问题第一反应是翻这里，
        # 让它藏在折叠条后面等于白写。
        s4 = self._new_section("四、常见问题", expanded=True, hot=True)
        faq = [
            (
                "Q1 长按 Y 没反应、轮盘不出来？",
                "按这个顺序查：\n"
                "① 设置窗口是不是就在最前面？它是当前窗口时热键不响应（免得在里面打字把轮盘弹出来）。"
                "点一下游戏窗口让它回到前台就好 —— 设置窗口留在后台开着没关系。\n"
                "② 当前这套轮盘是不是空的？一个音效都没上盘时按了不会有反应，"
                "日志里会写「当前这套轮盘是空的」。\n"
                "③ Y 是不是被游戏占用了？换个 F9 之类不常用的键试试。\n"
                "④ 游戏是不是「独占全屏」？它会把轮盘吞掉，改成无边框窗口就好。\n"
                "⑤ 程序还在不在？看右下角托盘的圆环图标。\n"
                "⑥ 游戏是管理员身份运行的话，本程序也要用管理员身份（双击时 UAC 点「是」）。\n"
                "另外「长按时长」调得太大时，按不够久也不会弹。",
            ),
            (
                "Q2 全屏游戏里看不到轮盘？",
                "同 Q1：改用「无边框窗口」或「窗口化全屏」。",
            ),
            (
                "Q3 队友听不到，但我自己听得到？",
                "「麦克风」页没勾「把音效送进游戏语音」，或者游戏里麦克风没选成 CABLE Output。",
            ),
            (
                "Q4 队友听得到，但我自己听不到？",
                "这是「虚拟声卡」这套玩法最容易踩的坑。按下面六条挨个对，基本都能自己解决：\n"
                "① 那个勾有没有勾上？「麦克风」页里有一行写着"
                "「音效也从自己的耳机里放出来（自己能听见）」，前面必须打勾。"
                "没打勾的时候，音效只往虚拟声卡里送一份，你自己这边是完全没声的 —— "
                "十有八九就是这一条。\n"
                "② 勾了以后，看它下面的「本地监听」滑块是不是被拖到 0% 了。"
                "这个滑块管的是「自己耳机里放多大声」，0% 等于静音，先拖回 80% 左右试。\n"
                "③ 电脑右下角那个小喇叭的「默认播放设备」可能被换掉了。"
                "程序是把声音放到 Windows 当前的默认播放设备上的。装了 VB-CABLE 之后，"
                "Windows 有可能自作主张把默认播放设备改成 CABLE Input —— 那你的音效等于被送进虚拟声卡里，"
                "从耳机这边当然一点都听不见。\n"
                "怎么办：点右下角小喇叭 → 点上面的设备名字（或者进 设置 → 系统 → 声音）→ "
                "在输出设备里选回你自己的耳机 / 音箱，别选带 CABLE 字样的那个。\n"
                "④ 是不是只有本程序没声？右键右下角小喇叭 → 打开「音量合成器」→ "
                "在列表里找到 SR Voiceover Roulette，看它的音量条有没有被拉到很低、或者被点了静音。\n"
                "⑤ 耳机本身通不通？蓝牙耳机没连上、插头没插到底都会这样。"
                "临时拔掉耳机、改让笔记本外放响一下，能响就说明问题在耳机这头，跟程序无关。\n"
                "⑥ 还是没声就看日志。打开程序目录里的 sr_roulette.log，搜「耳机输出=」，"
                "后面跟的那个名字就是程序实际在用的播放设备。"
                "如果那儿写的是带 CABLE 的名字，说明第 ③ 条还没改对。",
            ),
            (
                "Q5 装好 VB-CABLE 之后，电脑没声音了？",
                "这是 VB-CABLE 的「出厂设置」在捣乱，不是电脑坏了，一分钟能改回来。\n"
                "原因：VB-CABLE 是个「假声卡」，它有两个头 —— CABLE Input 是入口（往里灌声音的地方），"
                "CABLE Output 是出口（从这里把声音掏出来用）。装完以后 Windows 经常把默认播放设备"
                "直接改成 CABLE Input，这等于把全电脑的声音都倒进了虚拟声卡的肚子里；"
                "而这个肚子只有一个出口 CABLE Output，没人去听它，所以喇叭和耳机就一点动静都没有。\n"
                "怎么改回来：\n"
                "① 点右下角任务栏的小喇叭图标 → 弹出的小面板最上面有一行设备名 → 点它右边的小箭头，"
                "在弹出的列表里选回你的耳机或音箱（通常是「扬声器（Realtek…）」或者你耳机自己的名字）。"
                "找不到小喇叭就右键它 →「声音设置」→ 把「输出」那一栏的设备改回耳机。\n"
                "② 改完照常放首歌确认有声音。\n"
                "③ 别担心改这一步会影响这个软件：本软件要的 CABLE 是「虚拟声卡」那一栏里单独选的"
                "（「麦克风」页上手动指定 CABLE Input），跟 Windows 默认播放设备是两回事。"
                "默认播放设备还给耳机，本软件照样能把音效送进游戏。\n"
                "④ 顺带检查「录音」一侧：Windows 声音设置 → 输入 → 如果你的默认输入被改成了"
                "「CABLE Output」，也改回你自己的麦克风。不然你平时开语音软件说话，对方可能听不到你说话。\n"
                "⑤ 之后想彻底省心：别把 CABLE 那两个设备设成「默认设备」，"
                "只在游戏或语音软件里单独挑 CABLE Output 当麦克风就行。",
            ),
            (
                "Q6 某个音效不响？",
                "三种可能：格式不被解码器支持（转成 wav 试试）、文件不在 sounds 目录里、"
                "或者它被拖下了轮盘。查 sr_roulette.log 里有没有报错。",
            ),
            (
                "Q7 变调之后音效变长 / 变短了？",
                "正常。变调是按「不改变语速」的方式重采样的，音高变了长度也会跟着变"
                "（降 3 个半音大概会长两成）。想保持长度又改音高，目前做不到，"
                "可以用速度参数往回补一点。",
            ),
            (
                "Q8 组合只响了一部分？",
                "八成是有成员的音效文件被删了或改了名——编辑器里会标「⚠ 缺失」，"
                "换一个顶上就行。也可能是它设了「冷却」或「最多同时」，被自己拦下了。",
            ),
            (
                "Q9 杀毒软件 / Defender 报毒？",
                "打包出来的程序被启发式规则误判很常见（没有签名证书）。可以加白名单；"
                "更稳妥的做法是看代码自己跑——没有加密，也没有混淆。",
            ),
            (
                "Q10 会被封号吗？",
                "见第一节最后那句。这个判断只能你自己做，我能做的是把程序实际干了什么说清楚。",
            ),
            (
                "Q11 日志里记了我的按键，是不是在监视我？",
                "记的是按键名字（y、mouse_left），用来排查「为什么没触发」。"
                "它不看你打的字、不看窗口内容、不往外传。介意可以直接删掉这个文件，程序会自己重建。",
            ),
            (
                "Q12 更新版本会不会丢配置？",
                "不会。只替换 exe 就行，config.json、sounds.json、sounds 目录都保留。",
            ),
            (
                "Q13 能用在别的游戏上吗？",
                "能，它就是个全局热键 + 屏幕轮盘，不认游戏。第一节里的风险判断同样适用。",
            ),
            (
                "Q14 按住「切换轮盘」热键没反应？",
                "「快捷键」页里这一项默认是空的，得自己先绑一个键。绑好了还不行，"
                "大概率是跟游戏里同一个键撞了——换一个不常用的键最省事。",
            ),
            (
                "Q15 音效库里时长显示「—」？",
                "那个文件的长度没读出来（文件损坏，或者系统缺对应解码器）。不影响播放，"
                "只是算不出多长；转成 wav 就能正常显示。",
            ),
            (
                "Q16 存了好几套轮盘，换回旧版本程序会不会乱？",
                "不会。sounds.json 里除了多套轮盘，顶层还单独留了一份当前这套的旧格式记录，"
                "旧版本读的正是那份，所以照样是你的格子。同一份配置，两个版本各读各的。",
            ),
            (
                "Q17 提示「xxx 不支持 48kHz 立体声」，麦克风用不了？",
                "这句话是 v0.7.6 及更早版本才有的，那时候程序只认 48kHz 立体声浮点这一种格式，"
                "蓝牙耳麦、只给 44.1kHz 的 USB 麦会被直接判死。换成 v0.7.7 以后的版本就好。\n"
                "新版里同一台麦克风会先把所有能试的格式试穿（48k 立体声 → 单声道 → 44.1k → 16k），"
                "才轮到换下一台设备；就算设备谎报「支持」，真打不开也会自动往下退，"
                "状态栏会写「已自动适配到 16kHz 单声道」。"
                "真起不来时，日志里会写清楚试了几种格式、每一种是因为什么失败的。",
            ),
            (
                "Q18 按什么都没反应，是不是卡死了？（暂停功能）",
                "多半是你自己把软件「暂停」了，不是卡死。\n"
                "怎么进去的：长按轮盘键弹出轮盘、光标停在中间那个圆点上松手。"
                "这一下本来是「别放，停」，现在顺手把软件也暂停了，免得误触。\n"
                "怎么出来（两条路，任选其一）：\n"
                "　 ① 再长按轮盘键，光标停在圆点上松手一次；\n"
                "　 ② 长按轮盘键，正常划到某个音效上松手——音效会播，同时也解除暂停。\n"
                "　 暂停和恢复的瞬间屏幕中间会闪一个小提示，一闪就消失，不会一直挂在上面。\n"
                "　 嫌这个功能碍事？目前没法单独关掉它，但只要你不在圆点上松手就不会触发。",
            ),
            (
                "Q19 绑了快捷键，按下去却没声音？",
                "先看那个音效「条件」里是不是选了「条件解锁」——选了就得先按一下解锁键。\n"
                "再看「触发」：设成「松手触发」时，按下本来就不该响，得松手才响；"
                "设成「长按触发」时，松手就停，声音会很短。\n"
                "最后看「快捷键」页顶部的提示：如果这个键同时也是呼出轮盘 / 重复上一个 /"
                "顺序播放 / 切换轮盘，全局键优先，挂在它上面的音效会被让路，换个键就好。\n"
                "另外轮盘弹出的时候按鼠标左键/右键是「取消呼出」，那一下也不会播音效。",
            ),
            (
                "Q20 直播想让观众听到音效，但自己不想听？",
                "「麦克风」页勾上「把音效送进游戏语音」，虚拟声卡选 CABLE Input，"
                "然后把「音效也从自己的耳机里放出来」这个勾**取消**。\n"
                "这样音效只往虚拟声卡那一路走，你自己的耳朵里一点都没有。\n"
                "注意程序有条兜底：如果「本地监听」和「送对方」两个都关掉，"
                "它会自动把监听打开（不然整个软件就成了哑巴），所以不能靠「全关」来实现。\n"
                "直播/开黑软件里把音频输入设成 CABLE Output；"
                "如果不想把自己的说话声一起送过去，把「原声·送对方」拉到 0%。",
            ),
            (
                "Q21 用着用着老听到「叮」的提示音？",
                "先把锅分清楚：本程序的所有提示（切轮盘、麦克风掉线、重新扫描完成、"
                "启动就绪）都画在屏幕下方那条半透明小条里，一句都不出声。\n"
                "所以如果还在响，大概率不是它。常见的两个来源：\n"
                "· Windows 的通知音：设置 → 系统 → 通知 → 找到对应程序 → 关掉「播放声音」\n"
                "· 耳机 / USB 声卡插拔时系统自己的设备音（换接口、线松了都会响）\n"
                "想确认是不是本程序：把托盘图标右键退出，还响就是别人的。",
            ),
        ]
        for q, a in faq:
            s4.para(q, "head")
            s4.para(a)

        root.addStretch(1)

    # ---- 组装 ----
    def focus_faq(self) -> None:
        """跳到「四、常见问题」：展开、并把滚动条拉过去。首次启动引导用。"""
        target = None
        for sec in self.sections:
            if sec.title.startswith("四、"):
                sec.set_expanded(True)
                target = sec
                break
        if target is None:
            return
        # 展开后高度还没算完，等布局跑一轮再滚，否则滚不到位
        QTimer.singleShot(0, lambda: self.scroll.ensureWidgetVisible(target, 0, 0))

    def _new_section(self, title: str, expanded: bool = False, hot: bool = False) -> _FoldSection:
        sec = _FoldSection(title, expanded=expanded, hot=hot)
        self.sections.append(sec)
        self.root_lay.addWidget(sec)
        return sec

    @staticmethod
    def _link_row(prefix: str, url: str) -> QWidget:
        """一行外链：文字说明 + 可点的链接。

        用 QDesktopServices 让系统拿默认浏览器打开 —— 程序自己不发任何请求，
        「不联网」那句话仍然成立。
        """
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        lab = QLabel(prefix)
        lab.setStyleSheet("color:#b6bccb;font-size:12px;")
        h.addWidget(lab)
        link = QLabel(f'<a href="{url}" style="color:#5fd38b;">{url}</a>')
        link.setOpenExternalLinks(True)
        link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        link.setCursor(Qt.PointingHandCursor)
        link.setToolTip("用系统默认浏览器打开（本程序自己不联网）")
        h.addWidget(link)
        h.addStretch(1)
        return w


# ---------------------------------------------------------------- 右侧

def _drag_pixmap(text: str, width: int = 150, height: int = 38) -> QPixmap:
    """拖动时跟着鼠标走的那个小卡片。"""
    pm = QPixmap(width, height)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setBrush(QColor(30, 34, 42, 238))
    p.setPen(QPen(accent(255), 1.5))
    p.drawRoundedRect(QRectF(0.5, 0.5, width - 1, height - 1), 8, 8)
    p.setPen(QColor(234, 236, 242))
    f = QFont(UI_FONT)
    f.setPointSize(8)
    p.setFont(f)
    fm = p.fontMetrics()
    p.drawText(
        QRectF(12, 0, width - 22, height),
        Qt.AlignVCenter | Qt.AlignLeft,
        fm.elidedText(text, Qt.ElideRight, width - 26),
    )
    p.end()
    return pm


# 预览框比轮盘本身多留的边（左右各 PREVIEW_PAD/2）。
# v0.9 从 48 收窄到 36：右下角那张卡片多了「触发 / 条件」两行，
# 少留点白，最小窗口、最大直径时预览也不会被裁掉。
PREVIEW_PAD = 36


def preview_radius_of(cfg: dict) -> int:
    """预览用的轮盘半径：跟「直径」等比，但夹在 150~235 之间。

    180（默认直径）对应 190，比老版本那个 172 大约 10%——用户反馈预览
    "看着比以前小一圈"，实际上是无处安放的留白太多，整体放大一点点就正常了。
    直径调大时预览框跟着长，否则把轮盘调到 215、预览还停在老尺寸会更显小。
    上限 210 是为了别把预览卡片撑破：最小窗口（980×800）下卡片高度只有 468，
    预览控件 210×2+36=456 刚好塞得下。
    """
    try:
        r = int(round(float(cfg.get("wheel_radius", 180)) * 190.0 / 180.0))
    except (TypeError, ValueError):
        r = 190
    return max(150, min(210, r))


class WheelPreview(sr.WheelWidget):
    """配置窗口里的轮盘：能接收拖放，也能把扇区拖出去。

    拖放规则（v0.5.5 起）
      · 从音效库拖到某个格子 -> 放进/替换那一格（格子数不变）
      · 从音效库拖到中间圆 -> 追加到末尾（装满内圈 8 个后自动进外圈）
      · 外圈空位可以放东西，也可以被拖进拖出
      · 轮盘上拖动格子到另一个格子 -> **两格互换**（拖到外圈空位则原位变空）
      · 内圈和外圈之间也能互换，前提是外圈那一格有音效；
        内圈拖到外圈空位仍然拒绝（内圈 8 格必须满，空一格整个轮盘就不好判定）
      · 拖到左侧音效库 -> 从轮盘移除
    """

    # (文件名, 目标槽位)：目标槽位为 ADD_TO_END 表示追加到末尾
    lib_dropped = Signal(str, int)
    slot_dropped = Signal(int, int)   # (源位置, 目标位置)
    slot_clicked = Signal(int)

    def __init__(self, cfg: dict, bank: sr.SoundBank) -> None:
        super().__init__(cfg, embedded=True)
        self.bank = bank        # 构造时就挂上，别依赖调用方再补一刀
        self.setAcceptDrops(True)
        self.drop_target: int | None = None
        self._press_pos: QPoint | None = None
        self._press_idx: int | None = None     # 音效下标（能不能拖/点）
        self._press_sid: int | None = None     # 槽位号（拖出去要带的位置）
        self._dragging = False

    # ---- 几何 ----
    def _center(self) -> tuple[float, float]:
        return self.width() / 2.0, self.height() / 2.0

    def slots(self) -> int:
        return max(1, len(self.bank) if self.bank is not None else 0)

    def count(self) -> int:
        return len(self.bank) if self.bank is not None else 0

    @property
    def center_hint(self) -> str:
        """拖到中心时，中心那行小字改成"添加到末尾"。"""
        if self.drop_target == ADD_TO_END:
            return "＋ 添加到末尾"
        return ""

    def ring_geometry(self) -> tuple[dict, float]:
        """当前预览的环布局 + 缩放比（只是预览框的适配比例）。

        必须和 _paint_body 用同一个系数（paint_scale），否则预览里的
        点选/拖放会整体偏一圈。预览固定按 100% 画，不吃「整体大小」。
        """
        scale = self.paint_scale()
        return sr.ring_layout(self.cfg, self.count(), scale), scale

    def _to_world(self, pos: QPoint) -> tuple[float, float]:
        cx, cy = self._center()
        _, scale = self.ring_geometry()
        s = scale if scale > 0 else 1.0
        return (pos.x() - cx) / s, (pos.y() - cy) / s

    def _dist_px(self, pos: QPoint) -> float:
        """到圆心的距离，用控件像素 —— 和 geo 里的半径同一套单位。"""
        cx, cy = self._center()
        return math.hypot(pos.x() - cx, pos.y() - cy)

    def inside_wheel(self, pos: QPoint) -> bool:
        geo, _ = self.ring_geometry()
        return self._dist_px(pos) <= geo["extent"] + 12

    def slot_at(self, pos: QPoint) -> int | None:
        """控件坐标 -> 槽位号（含空着的外圈位置）；中空区 / 轮盘外返回 None。

        槽位号是"位置"：0~7 内圈，8~19 外圈 12 个固定位置。
        外圈允许留空，所以这里不管那一格有没有音效，位置算得出来就返回。
        """
        if self.count() == 0:
            return None
        geo, _ = self.ring_geometry()
        dist = self._dist_px(pos)
        if dist <= geo["hole"] * 0.98 or dist > geo["extent"] + 12:
            return None
        dx, dy = self._to_world(pos)
        if geo["two_ring"] and dist >= geo["outer_r0"]:
            p = sr.sector_from_delta(dx, dy, sr.OUTER_MAX, 0.0)
            return None if p is None else sr.INNER_MAX + p
        return sr.sector_from_delta(dx, dy, int(geo["inner_n"]), 0.0)

    def index_of_slot(self, sid: int | None) -> int | None:
        """槽位号 -> 音效下标；那一格空着返回 None。"""
        if self.bank is None:
            return None
        return sr.index_of_slot(sid, self.count(), sr.outer_index_map_of(self.bank))

    def _target_at(self, pos: QPoint) -> int | None:
        """拖放落点：槽位号（放/换到那一格）、ADD_TO_END（追加）、None（不接受）。

        外圈的任意位置都收 —— 空格子能放进去，有内容的两格互换。
        """
        geo, _ = self.ring_geometry()
        dist = self._dist_px(pos)          # 控件像素（geo 已按 scale 缩过）
        if self.count() == 0:
            return ADD_TO_END if dist <= geo["extent"] + 12 else None
        if dist <= geo["hole"] * 0.98:
            return ADD_TO_END
        sid = self.slot_at(pos)
        if sid is None:
            return None
        if sid < sr.INNER_MAX:
            return sid if sid < self.count() else None
        return sid

    # ---- 鼠标：单击选中，按住移动则发起拖放 ----
    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() != Qt.LeftButton:
            return
        self._press_pos = e.position().toPoint()
        self._press_sid = self.slot_at(self._press_pos)
        self._press_idx = self.index_of_slot(self._press_sid)
        self._dragging = False

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._press_pos is None or not (e.buttons() & Qt.LeftButton):
            return
        pos = e.position().toPoint()
        if (pos - self._press_pos).manhattanLength() < 10:
            return
        idx, sid = self._press_idx, self._press_sid
        if idx is None or sid is None or self.bank is None or idx >= len(self.bank):
            return
        self._dragging = True
        name = self.bank.items[idx].name

        mime = QMimeData()
        # 带的是"槽位号"而不是音效下标：外圈能留空，位置和序号不是一回事
        mime.setData(MIME_SLOT, str(sid).encode("utf-8"))
        mime.setText(name)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(_drag_pixmap(self.bank.name_at(idx)))
        drag.exec(Qt.MoveAction)
        self._press_pos = None
        self._press_sid = None
        self._dragging = False

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if self._press_pos is not None and not self._dragging:
            idx = self._press_idx
            if idx is not None and self.bank is not None and idx < len(self.bank):
                self.slot_clicked.emit(idx)
        self._press_pos = None
        self._press_sid = None
        self._press_idx = None

    # ---- 接收拖放 ----
    def _accepts(self, mime) -> bool:
        return mime.hasFormat(MIME_LIB) or mime.hasFormat(MIME_SLOT)

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if self._accepts(e.mimeData()):
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:  # noqa: N802
        if not self._accepts(e.mimeData()):
            return
        target = self._target_at(e.position().toPoint())
        if target != self.drop_target:
            self.drop_target = target
            self.update()
        e.acceptProposedAction()

    def dragLeaveEvent(self, e) -> None:  # noqa: N802
        self.drop_target = None
        self.update()

    def dropEvent(self, e) -> None:  # noqa: N802
        md = e.mimeData()
        target = self._target_at(e.position().toPoint())
        self.drop_target = None
        self.update()
        if target is None:
            e.ignore()
            return
        if md.hasFormat(MIME_LIB):
            name = bytes(md.data(MIME_LIB)).decode("utf-8")
            self.lib_dropped.emit(name, target)
        elif md.hasFormat(MIME_SLOT):
            src = int(bytes(md.data(MIME_SLOT)).decode("utf-8"))
            self.slot_dropped.emit(src, target)
        e.acceptProposedAction()

    # ---- 拖放落点高亮 ----
    def paintEvent(self, e) -> None:  # noqa: N802
        super().paintEvent(e)
        tgt = self.drop_target
        if tgt is None or self.bank is None:
            return

        geo, _ = self.ring_geometry()
        cx, cy = self._center()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(QColor(255, 255, 255, 44))
        p.setPen(QPen(QColor(255, 255, 255, 170), 2.0, Qt.DashLine))

        if tgt == ADD_TO_END:
            # 中间圆：这是"添加"，不是"替换"。文字交给中心那行提示去写，
            # 否则会压在音效名上糊成一片
            r = geo["hole"] * 0.96
            p.drawEllipse(QPointF(cx, cy), r, r)
            p.end()
            return

        geom = sr.slot_geometry(geo, tgt)   # tgt 已经是槽位号
        if geom is None:
            p.end()
            return
        r0, r1, start, span = geom
        p.drawPath(sr.ring_sector_path(cx, cy, r0, r1, start, span))
        p.end()


class SlotDetail(QFrame):
    """右侧下方：当前选中音效的详细参数。"""

    setting_changed = Signal(str)    # 某个音效的参数变了
    preview_requested = Signal(str)  # 想试听某个音效
    edit_combo_requested = Signal(str)   # 想编辑某个组合（cid）

    def __init__(self, scfg) -> None:
        super().__init__()
        self.scfg = scfg
        self.current: str | None = None
        self._is_combo = False
        self._loading = False
        self.setObjectName("Card")
        # 高度写死，免得内容增减时面板自己跳；改动行数后记得同步这个值
        # 188 → 246：v0.9 加了「触发」和「条件」两行
        self.setFixedHeight(246)

        lay = QVBoxLayout(self)
        # v0.9：多了「触发 / 条件」两行，上下留白和行距都收一点，
        # 否则卡片要再长 10 多个像素，窗口就得多长一点
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(4)

        head = QHBoxLayout()
        self.title = QLabel("未选中音效")
        self.title.setObjectName("CardTitle")
        head.addWidget(self.title)
        head.addStretch(1)
        self.btn_combo = QPushButton("编辑组合")
        self.btn_combo.setCursor(Qt.PointingHandCursor)
        self.btn_combo.hide()
        head.addWidget(self.btn_combo)
        self.btn_play = QPushButton("试听")
        self.btn_play.setFixedWidth(64)
        head.addWidget(self.btn_play)
        lay.addLayout(head)

        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(4)

        vol_row = QHBoxLayout()
        vl = QLabel("音量")
        vl.setFixedWidth(52)
        vl.setStyleSheet("color:#a9b0c0;font-size:12px;")
        vol_row.addWidget(vl)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 200)
        self.volume.setValue(100)
        vol_row.addWidget(self.volume, 1)
        self.vol_val = QLabel("100%")
        self.vol_val.setFixedWidth(46)
        self.vol_val.setStyleSheet(f"color:{accent_hex()};font-size:12px;font-weight:600;")
        vol_row.addWidget(self.vol_val)
        body.addLayout(vol_row)

        pitch_row = QHBoxLayout()
        self.lbl_pitch = pl = QLabel("变调")
        pl.setFixedWidth(52)
        pl.setStyleSheet("color:#a9b0c0;font-size:12px;")
        pitch_row.addWidget(pl)
        self.pitch_mode = QComboBox()
        for mode in PITCH_MODES:
            self.pitch_mode.addItem(PITCH_MODE_LABEL.get(mode, mode), mode)
        pitch_row.addWidget(self.pitch_mode, 1)
        # 幅度：升/降调时是"每次变多少"，随机时是"随机范围 ±N"
        self.pitch_step = QComboBox()
        for n in (1, 2, 3, 5, 7, 12):
            self.pitch_step.addItem(f"±{n} 半音", float(n))
        self.pitch_step.setToolTip(
            "升调/降调：每次连击变化多少半音\n随机变调：随机范围（±N 半音）"
        )
        pitch_row.addWidget(self.pitch_step)
        # 固定变调：直接变 N 半音（正升负降），只在"固定变调"模式下露出来
        self.pitch_fixed = QDoubleSpinBox()
        self.pitch_fixed.setRange(-24.0, 24.0)
        self.pitch_fixed.setSingleStep(1.0)
        self.pitch_fixed.setDecimals(1)
        self.pitch_fixed.setSuffix(" 半音")
        self.pitch_fixed.setToolTip(
            "每次播放都直接变这么多半音：正数升调、负数降调。\n"
            "比如 -5 就是把声音压沉 5 个半音。"
        )
        self.pitch_fixed.hide()
        pitch_row.addWidget(self.pitch_fixed)
        body.addLayout(pitch_row)

        # 速度：时间拉伸，只改快慢不改音调，和上面那行互不影响
        spd_row = QHBoxLayout()
        self.lbl_speed = sl = QLabel("速度")
        sl.setFixedWidth(52)
        sl.setStyleSheet("color:#a9b0c0;font-size:12px;")
        spd_row.addWidget(sl)
        self.speed_mode = QComboBox()
        for mode in SPEED_MODES:
            self.speed_mode.addItem(SPEED_MODE_LABEL.get(mode, mode), mode)
        self.speed_mode.setToolTip(
            "连续播放时越按越快 / 越慢。\n"
            "和\"变调\"不同：这个不会把嗓子变尖变沉，只是说话的语速变了。\n"
            "两个可以同时开，比如又升调又加快。"
        )
        spd_row.addWidget(self.speed_mode, 1)
        self.speed_step = QComboBox()
        for pct in (5, 8, 10, 15, 20, 30):
            self.speed_step.addItem(f"每次 {pct}%", pct / 100.0)
        self.speed_step.setToolTip("每连击一次快/慢多少（上限 ±60%）")
        spd_row.addWidget(self.speed_step)
        body.addLayout(spd_row)

        win_row = QHBoxLayout()
        self.lbl_window = QLabel("连击窗口")
        self.lbl_window.setFixedWidth(52)
        self.lbl_window.setStyleSheet("color:#a9b0c0;font-size:12px;")
        win_row.addWidget(self.lbl_window)
        self.pitch_window = QSpinBox()
        self.pitch_window.setRange(200, 10000)
        self.pitch_window.setSingleStep(100)
        self.pitch_window.setValue(2500)
        self.pitch_window.setSuffix(" ms")
        self.pitch_window.setToolTip("多少毫秒内再按算一次连击（变调和速度共用）")
        win_row.addWidget(self.pitch_window)
        # 随机模式下连击窗口没有意义：把这一格换成一句说明，比留个灰框清楚
        self.lbl_rand_hint = QLabel("每次按都重新抽一个半音，不看连击窗口")
        self.lbl_rand_hint.setObjectName("Hint")
        self.lbl_rand_hint.hide()
        win_row.addWidget(self.lbl_rand_hint)
        # 固定变调同理：每次都一样，窗口没有意义
        self.lbl_fixed_hint = QLabel("每次都直接变固定的半音数，不看连击窗口")
        self.lbl_fixed_hint.setObjectName("Hint")
        self.lbl_fixed_hint.hide()
        win_row.addWidget(self.lbl_fixed_hint)
        win_row.addStretch(1)
        hl = QLabel("快捷键")
        hl.setFixedWidth(52)
        hl.setStyleSheet("color:#a9b0c0;font-size:12px;")
        win_row.addWidget(hl)
        self.hotkey = KeyBox("", 116)
        win_row.addWidget(self.hotkey)
        # 全局通用：勾上之后这个键不再跟着轮盘走。组合音效也有这一项 ——
        # 组合的定义全盘共用，但"这个键在别的盘上还算不算数"仍然要单独决定。
        # 文字用两字"全局"：这一行元素已经排满（连击窗口 + 快捷键 + 清除键），
        # 四字在最小窗口下会把按键框挤扁，完整说明放提示里。
        self.chk_global = QCheckBox("全局")
        self.chk_global.setObjectName("GlobalChk")
        self.chk_global.setToolTip(
            "「全局通用」：勾上之后，这个快捷键不再跟着轮盘走，\n"
            "切换到别的轮盘，按这个键照样能触发它。\n"
            "不勾的时候只在它所在的这一套轮盘上生效（和以前一样）。\n"
            "没绑快捷键时这一项不起作用。"
        )
        win_row.addWidget(self.chk_global)
        body.addLayout(win_row)

        # 组合条目专用说明：变调/变速在组合编辑器里逐项设
        self.lbl_combo_hint = QLabel(
            "组合的变调 / 变速在「编辑组合」里逐项设置，\n"
            "这里只管整体音量和直按键。"
        )
        self.lbl_combo_hint.setObjectName("Hint")
        self.lbl_combo_hint.setWordWrap(True)
        self.lbl_combo_hint.hide()
        body.addWidget(self.lbl_combo_hint)

        # ---- 触发方式（v0.9）：按下响 / 长按响 / 松手响 / 按住连发 ----
        trig_row = QHBoxLayout()
        self.lbl_trigger = tl = QLabel("触发")
        tl.setFixedWidth(52)
        tl.setStyleSheet("color:#a9b0c0;font-size:12px;")
        trig_row.addWidget(tl)
        self.trigger_mode = QComboBox()
        for mode in TRIGGER_MODES:
            self.trigger_mode.addItem(TRIGGER_MODE_LABEL.get(mode, mode), mode)
        self.trigger_mode.setToolTip(
            "按下快捷键之后，这个音效什么时候响、什么时候停。\n"
            "点击触发：按下就响一次（和以前一样）\n"
            "长按触发：按住一直响，松手立刻停\n"
            "松手触发：按下不出声，松手那一下才响\n"
            "长按连续触发：按住不放就按间隔一直「点」下去，\n"
            "　　　　　　　连击变调/变速会跟着累加"
        )
        trig_row.addWidget(self.trigger_mode, 1)
        self.repeat_ms = QSpinBox()
        self.repeat_ms.setRange(REPEAT_MS_MIN, REPEAT_MS_MAX)
        self.repeat_ms.setSingleStep(10)
        self.repeat_ms.setValue(200)
        self.repeat_ms.setSuffix(" ms")
        self.repeat_ms.setFixedWidth(94)
        self.repeat_ms.setToolTip(
            "长按连续触发的间隔：按住时每隔这么久再响一次。\n"
            "小一点（100ms 左右）= 连成一片；大一点 = 一下一下地蹦。"
        )
        trig_row.addWidget(self.repeat_ms)
        self.lbl_repeat_hint = QLabel("按住时每隔这么久再响一次")
        self.lbl_repeat_hint.setObjectName("Hint")
        trig_row.addWidget(self.lbl_repeat_hint)
        trig_row.addStretch(1)
        body.addLayout(trig_row)

        # ---- 触发条件（v0.9）：无条件 / 先用解锁键开门 ----
        cond_row = QHBoxLayout()
        self.lbl_unlock = cl = QLabel("条件")
        cl.setFixedWidth(52)
        cl.setStyleSheet("color:#a9b0c0;font-size:12px;")
        cond_row.addWidget(cl)
        self.unlock_mode = QComboBox()
        for mode in UNLOCK_MODES:
            self.unlock_mode.addItem(UNLOCK_MODE_LABEL.get(mode, mode), mode)
        self.unlock_mode.setToolTip(
            "无条件：按了就能响。\n"
            "条件解锁：先按一下「解锁键」，这个音效才能被触发。"
        )
        cond_row.addWidget(self.unlock_mode, 1)
        self.unlock_key = KeyBox("", 96)
        self.unlock_key.setToolTip(
            "解锁键：按一下它，名下所有音效一起放开（各自算各自的时间和次数）。\n"
            "重复按是刷新，不会叠加次数。"
        )
        cond_row.addWidget(self.unlock_key)
        self.unlock_ms = QSpinBox()
        self.unlock_ms.setRange(0, UNLOCK_MS_MAX)
        self.unlock_ms.setSingleStep(500)
        self.unlock_ms.setSuffix(" ms")
        self.unlock_ms.setSpecialValueText("不限时")
        self.unlock_ms.setFixedWidth(96)
        self.unlock_ms.setToolTip(
            "解锁后多久之内可以触发。0 = 不限时（一直到次数用完）。\n"
            "注意：时间到了只是「不能再触发新的」，正在响的声音会继续响完。"
        )
        cond_row.addWidget(self.unlock_ms)
        self.unlock_count = QSpinBox()
        self.unlock_count.setRange(0, UNLOCK_COUNT_MAX)
        self.unlock_count.setSingleStep(1)
        self.unlock_count.setSuffix(" 次")
        self.unlock_count.setSpecialValueText("不限次")
        self.unlock_count.setFixedWidth(90)
        self.unlock_count.setToolTip(
            "解锁一次能用几次。0 = 不限次。\n"
            "长按连续触发整段按住也只算 1 次。"
        )
        cond_row.addWidget(self.unlock_count)
        body.addLayout(cond_row)

        lay.addWidget(self.body)
        lay.addStretch(1)

        # 控件改动即时写回配置
        self.volume.valueChanged.connect(self._push)
        self.pitch_mode.currentIndexChanged.connect(self._push)
        self.pitch_step.currentIndexChanged.connect(self._push)
        self.pitch_fixed.valueChanged.connect(self._push)
        self.pitch_window.valueChanged.connect(self._push)
        self.speed_mode.currentIndexChanged.connect(self._push)
        self.speed_step.currentIndexChanged.connect(self._push)
        self.hotkey.key_changed.connect(self._on_hotkey_changed)
        self.chk_global.toggled.connect(self._on_global_toggled)
        self.trigger_mode.currentIndexChanged.connect(self._on_trigger_changed)
        self.repeat_ms.valueChanged.connect(self._push)
        self.unlock_mode.currentIndexChanged.connect(self._on_unlock_changed)
        self.unlock_key.key_changed.connect(lambda _v: self._push())
        self.unlock_ms.valueChanged.connect(self._push)
        self.unlock_count.valueChanged.connect(self._push)
        self.btn_play.clicked.connect(
            lambda: self.current and self.preview_requested.emit(self.current)
        )
        self.btn_combo.clicked.connect(self._emit_edit_combo)

        self.set_sound(None)

    def set_sound(self, name: str | None) -> None:
        """切换当前编辑的音效；None 表示没选中，控件置灰。

        传进来的必须是**带扩展名的文件名**（和 sounds.json 的键一致），
        界面标题上再显示去掉扩展名的样子。
        """
        self._loading = True
        self.current = name
        self._is_combo = bool(name) and is_combo_key(name)

        if name is None:
            self.title.setText("未选中音效")
            self.title.setStyleSheet("color:#6f7686;")
            # 没选中时把触发相关控件复位，免得留着上一个音效的值骗人
            self.trigger_mode.setCurrentIndex(0)
            self.repeat_ms.setValue(200)
            self.unlock_mode.setCurrentIndex(0)
            self.unlock_key.set_key("")
            self.unlock_ms.setValue(0)
            self.unlock_count.setValue(0)
            self.chk_global.setChecked(False)
        else:
            self.title.setText(
                self.scfg.display_name(name) if self._is_combo else Path(name).stem
            )
            self.title.setStyleSheet("color:#f2f4f8;")
            st = self.scfg.setting(name)
            self.volume.setValue(int(round(st.volume * 100)))
            self.vol_val.setText(f"{self.volume.value()}%")
            mi = self.pitch_mode.findData(st.pitch_mode)
            self.pitch_mode.setCurrentIndex(max(0, mi))
            si = self.pitch_step.findData(float(st.pitch_step))
            if si < 0:
                # 老配置里可能是 4、6 这种下拉里没有的幅度：就近选一个
                vals = [self.pitch_step.itemData(k) for k in range(self.pitch_step.count())]
                si = min(range(len(vals)), key=lambda k: abs(vals[k] - float(st.pitch_step)))
            self.pitch_step.setCurrentIndex(max(0, si))
            self.pitch_fixed.setValue(float(st.pitch_fixed))
            self.pitch_window.setValue(int(st.pitch_window_ms))
            mi = self.speed_mode.findData(st.speed_mode)
            self.speed_mode.setCurrentIndex(max(0, mi))
            si2 = self.speed_step.findData(float(st.speed_step))
            if si2 < 0:
                # 老配置里可能是 12%、25% 这类下拉里没有的幅度：就近选一个
                vals = [self.speed_step.itemData(k) for k in range(self.speed_step.count())]
                si2 = min(range(len(vals)), key=lambda k: abs(vals[k] - float(st.speed_step)))
            self.speed_step.setCurrentIndex(max(0, si2))
            self.hotkey.set_key(st.hotkey)
            self.chk_global.setChecked(bool(getattr(st, "global_hotkey", False)))

            # ---- 触发方式 / 触发条件 ----
            ti = self.trigger_mode.findData(st.trigger_mode)
            self.trigger_mode.setCurrentIndex(max(0, ti))
            self.repeat_ms.setValue(int(getattr(st, "repeat_ms", 200)))
            ui = self.unlock_mode.findData(st.unlock_mode)
            self.unlock_mode.setCurrentIndex(max(0, ui))
            self.unlock_key.set_key(getattr(st, "unlock_key", "") or "")
            self.unlock_ms.setValue(int(getattr(st, "unlock_ms", 0)))
            self.unlock_count.setValue(int(getattr(st, "unlock_count", 0)))

        for w in (self.volume, self.pitch_mode, self.pitch_step,
                  self.pitch_fixed,
                  self.speed_mode, self.speed_step,
                  self.pitch_window, self.hotkey, self.btn_play,
                  self.trigger_mode, self.repeat_ms,
                  self.unlock_mode, self.unlock_key,
                  self.unlock_ms, self.unlock_count, self.chk_global):
            w.setEnabled(name is not None)
        self.btn_combo.setVisible(self._is_combo)
        self._sync_pitch_enabled()
        self._sync_trigger_ui()
        self._sync_global_hint()
        self._loading = False

    def _sync_trigger_ui(self) -> None:
        """按当前选择显示/藏起"用不上"的那几个格子。

        长按连续触发才需要间隔；条件解锁才需要解锁键/时间/次数。
        其余一律藏掉 —— 面板就这么点地方，留着灰框只会让人猜。
        """
        mode = str(self.trigger_mode.currentData() or "")
        is_repeat = mode == TRIGGER_REPEAT
        self.repeat_ms.setVisible(is_repeat)
        self.lbl_repeat_hint.setVisible(is_repeat)

        locked = str(self.unlock_mode.currentData() or "") == UNLOCK_KEY
        self.unlock_key.setVisible(locked)
        self.unlock_ms.setVisible(locked)
        self.unlock_count.setVisible(locked)
        # 选了"条件解锁"却没设键：等于没锁，直接在提示里说清楚，
        # 免得用户以为设置坏了
        if locked and self.current is not None and not self.unlock_key.key_name:
            self.lbl_repeat_hint.setText("注意：还没设解锁键，现在等于无条件")
            self.lbl_repeat_hint.setVisible(True)
        elif is_repeat:
            self.lbl_repeat_hint.setText("按住时每隔这么久再响一次")

    def _on_trigger_changed(self) -> None:
        self._sync_trigger_ui()
        self._push()

    def _on_unlock_changed(self) -> None:
        self._sync_trigger_ui()
        self._push()

    def _sync_pitch_enabled(self) -> None:
        """随机/固定变调都不看连击窗口：那一格换成一句说明。

        但如果速度那条开着，窗口对速度仍然有用，所以不能藏。
        """
        if self._is_combo:
            # 组合的每项变调/变速在编辑器里逐项设置，这里整排藏掉
            for w in (self.lbl_pitch, self.pitch_mode, self.pitch_step,
                      self.pitch_fixed, self.lbl_speed, self.speed_mode,
                      self.speed_step, self.lbl_window, self.pitch_window,
                      self.lbl_rand_hint, self.lbl_fixed_hint):
                w.setVisible(False)
            self.lbl_combo_hint.setVisible(self.current is not None)
            # 组合的变调/变速不在这儿管，但"全局通用"照样要有：
            # 组合的定义全盘共用 != 它的快捷键每套轮盘都认。
            self.chk_global.setVisible(True)
            return
        # 普通音效：先把组合模式藏掉的那批"无条件放回来"，再按当前模式做减法。
        # 隐藏是粘性的 —— 只要没显式 setVisible(True)，控件就永远不再出现，
        # 所以这里必须逐个还原，不能只还原"可能要藏的那几个"。
        self.lbl_combo_hint.setVisible(False)
        self.chk_global.setVisible(True)
        self.lbl_pitch.setVisible(True)
        self.pitch_mode.setVisible(True)
        self.lbl_speed.setVisible(True)
        self.speed_mode.setVisible(True)
        self.speed_step.setVisible(True)
        mode = self.pitch_mode.currentData()
        no_window = mode in (PITCH_RANDOM, PITCH_FIXED)
        fixed = mode == PITCH_FIXED
        self.pitch_step.setVisible(not fixed)
        self.pitch_fixed.setVisible(fixed)
        speed_on = self.speed_mode.currentData() != SPEED_NONE
        hide_win = no_window and not speed_on
        usable = self.current is not None and not hide_win
        self.lbl_window.setVisible(not hide_win)
        self.pitch_window.setVisible(not hide_win)
        self.pitch_window.setEnabled(usable)
        self.lbl_rand_hint.setVisible(bool(mode == PITCH_RANDOM and not speed_on
                                           and self.current is not None))
        self.lbl_fixed_hint.setVisible(bool(fixed and not speed_on
                                            and self.current is not None))

    def _on_hotkey_changed(self, _key: str = "") -> None:
        self._sync_global_hint()
        self._push()

    def _on_global_toggled(self, _on: bool = False) -> None:
        self._sync_global_hint()
        self._push()

    def _sync_global_hint(self) -> None:
        """勾了「全局通用」却没绑键时，把"它暂时不生效"直接说出来。

        不改复选框的文字（那一行已经排满，加字会挤），改成换提示，
        鼠标悬停就能看到原因，免得用户以为功能没做好。
        """
        if self.chk_global.isChecked() and not self.hotkey.key_name:
            self.chk_global.setToolTip(
                "已经勾上了，但这个音效还没绑快捷键 ——\n"
                "没有键可以按，这一项暂时不会生效。先在左边绑一个键。"
            )
        else:
            self.chk_global.setToolTip(
                "「全局通用」：勾上之后，这个快捷键不再跟着轮盘走，\n"
                "切换到别的轮盘，按这个键照样能触发它。\n"
                "不勾的时候只在它所在的这一套轮盘上生效（和以前一样）。"
            )

    def _emit_edit_combo(self) -> None:
        if self.current and is_combo_key(self.current):
            self.edit_combo_requested.emit(self.current[len(COMBO_PREFIX):])

    def _push(self) -> None:
        if self._loading or self.current is None:
            return
        st = self.scfg.setting(self.current)
        st.volume = self.volume.value() / 100.0
        # 触发方式和触发条件对普通音效和组合一视同仁
        st.trigger_mode = str(self.trigger_mode.currentData() or "tap")
        st.repeat_ms = int(self.repeat_ms.value())
        st.unlock_mode = str(self.unlock_mode.currentData() or "none")
        st.unlock_key = self.unlock_key.key_name
        st.unlock_ms = int(self.unlock_ms.value())
        st.unlock_count = int(self.unlock_count.value())
        if self._is_combo:
            # 组合没有"整体变调/速度"这回事，逐项参数归编辑器管
            st.hotkey = self.hotkey.key_name
            st.global_hotkey = bool(self.chk_global.isChecked())
            self.vol_val.setText(f"{self.volume.value()}%")
            self.setting_changed.emit(self.current)
            return
        st.pitch_mode = str(self.pitch_mode.currentData() or "none")
        st.pitch_step = float(self.pitch_step.currentData() or 1.0)
        st.pitch_fixed = round(float(self.pitch_fixed.value()), 1)
        st.pitch_window_ms = int(self.pitch_window.value())
        st.speed_mode = str(self.speed_mode.currentData() or "none")
        st.speed_step = float(self.speed_step.currentData() or 0.10)
        st.hotkey = self.hotkey.key_name
        st.global_hotkey = bool(self.chk_global.isChecked())
        self.vol_val.setText(f"{self.volume.value()}%")
        self._sync_pitch_enabled()
        self.setting_changed.emit(self.current)


class _FirstRunTip(QWidget):
    """首次启动浮在设置窗口上的一张提示卡：告诉用户去翻「常见问题」。

    做成窗口内的覆盖层，而不是独立对话框：
    它跟着主窗口一起移动/关闭，不需要额外的窗口管理，也不会变成孤儿窗口。
    """

    open_faq = Signal()
    dismissed = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("TipMask")
        self.setAttribute(Qt.WA_StyledBackground, True)

        v = QVBoxLayout(self)
        v.setContentsMargins(28, 28, 28, 28)
        v.addStretch(1)

        h = QHBoxLayout()
        h.addStretch(1)

        card = QFrame()
        card.setObjectName("TipCard")
        card.setFixedWidth(420)
        self.card = card
        cv = QVBoxLayout(card)
        cv.setContentsMargins(22, 18, 22, 16)
        cv.setSpacing(10)

        title = QLabel("第一次用？")
        title.setObjectName("TipTitle")
        cv.addWidget(title)

        body = _WrapLabel(
            "遇到问题先翻「说明」页最后那节「四、常见问题」——"
            "按了热键轮盘不出来、队友听不到、自己听不到、"
            "装了 VB-CABLE 之后电脑没声音，这些坑都写在那儿了。\n"
            "「说明」页里你主题色那一条就是了（它默认已经展开）。"
        )
        body.setObjectName("TipText")
        cv.addWidget(body)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch(1)

        self.btn_later = QPushButton("知道了")
        self.btn_later.setCursor(Qt.PointingHandCursor)
        self.btn_later.clicked.connect(self._later)
        row.addWidget(self.btn_later)

        self.btn_go = QPushButton("去看看")
        self.btn_go.setObjectName("Primary")
        self.btn_go.setCursor(Qt.PointingHandCursor)
        self.btn_go.clicked.connect(self._go)
        row.addWidget(self.btn_go)
        cv.addLayout(row)

        h.addWidget(card)
        h.addStretch(1)
        v.addLayout(h)
        v.addStretch(1)

    def _later(self) -> None:
        self.dismissed.emit()

    def _go(self) -> None:
        self.open_faq.emit()

    def mousePressEvent(self, e) -> None:  # noqa: N802
        # 点卡片外面任意处也当作「我知道了」，省得用户找不到关掉的按钮；
        # 点卡片本身（文字、空白）不算，否则想选中文字就顺手关掉了
        pos = e.position().toPoint()
        if self.card.rect().contains(self.card.mapFrom(self, pos)):
            e.accept()
            return
        e.accept()
        self.dismissed.emit()


class SettingsWindow(QWidget):
    """配置主窗口。"""

    closed = Signal()
    changed = Signal()             # 轮盘内容/顺序变了，主程序要重新解码
    params_changed = Signal()      # 只是参数变了（音量/变调/按键），不用重解码
    audio_changed = Signal()       # 麦克风那套参数变了，主程序要重建音频链路
    preview_requested = Signal(str)  # 试听某个音效
    wheel_switch_requested = Signal(str)  # 要切到另一套轮盘（wid），由主程序执行

    def __init__(self, cfg: dict, scfg, bank: sr.SoundBank, engine=None) -> None:
        super().__init__()
        self.cfg = cfg
        self.scfg = scfg
        self.bank = bank
        self.engine = engine

        self.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowMinimizeButtonHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("SR Voiceover Roulette 设置")
        # 高度 780 → 840：v0.9 的音效卡片多了「触发」「条件」两行，
        # 不把窗口放高一点，右下角那块和轮盘预览会互相挤
        self.resize(1120, 840)
        self.setMinimumSize(980, 800)
        self.setStyleSheet(build_qss())

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.root = QWidget()
        self.root.setObjectName("Root")
        outer.addWidget(self.root)

        v = QVBoxLayout(self.root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.titlebar = TitleBar(self)
        self.titlebar.btn_min.clicked.connect(self.showMinimized)
        self.titlebar.btn_close.clicked.connect(self.close)
        v.addWidget(self.titlebar)

        body = QHBoxLayout()
        body.setContentsMargins(20, 6, 20, 20)
        body.setSpacing(20)
        v.addLayout(body, 1)

        # ---- 左：标签页 ----
        left = QWidget()
        left.setFixedWidth(470)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(8)

        self.tabs = QTabWidget()
        self.page_lib = LibraryPage(bank, scfg)
        self.page_lib.slot_removed.connect(self._on_slot_removed)
        self.page_lib.combo_new.connect(self._on_combo_new)
        self.page_lib.combo_edit.connect(self._open_combo_editor)
        self.page_lib.combo_delete.connect(self._on_combo_delete)
        self.page_key = HotkeyPage(cfg, bank, scfg)
        self.page_wheel = WheelPage(cfg, scfg)
        self.page_mic = MicPage(cfg, engine)
        self.page_help = HelpPage()
        self.tabs.addTab(self.page_lib, "音效库")
        self.tabs.addTab(self.page_key, "快捷键")
        self.tabs.addTab(self.page_wheel, "轮盘")
        self.tabs.addTab(self.page_mic, "麦克风")
        self.tabs.addTab(self.page_help, "说明")
        # 切回音效库时重新扫一遍：用户可能刚在文件夹里放了新文件
        self.tabs.currentChanged.connect(
            lambda i: self.page_lib.refresh() if i == 0 else None
        )
        ll.addWidget(self.tabs)
        body.addWidget(left)

        # ---- 右：轮盘 + 选中详情 ----
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(14)

        wheel_holder = QFrame()
        wheel_holder.setObjectName("Card")
        wh = QVBoxLayout(wheel_holder)
        wh.setContentsMargins(16, 12, 16, 14)
        wh.setSpacing(4)

        cap = QHBoxLayout()
        cap_title = QLabel("轮盘预览")
        cap_title.setObjectName("SectionLabel")
        cap.addWidget(cap_title)
        cap.addStretch(1)
        self.lbl_count = QLabel(f"{len(bank)} 个槽位")
        self.lbl_count.setObjectName("Hint")
        cap.addWidget(self.lbl_count)
        wh.addLayout(cap)

        self.preview_cfg = dict(cfg)
        # 预览框大小跟着「直径」走（180 对应 172 基准，和以前一样），
        # 之前固定写死 172，导致直径调到 215 了预览还是老尺寸，看着偏小
        self.preview_cfg["wheel_radius"] = preview_radius_of(cfg)
        self.preview = WheelPreview(self.preview_cfg, bank)
        side = int(self.preview_cfg["wheel_radius"] * 2 + PREVIEW_PAD)
        self.preview.setFixedSize(side, side)
        self.preview.bank = bank
        self.preview.selected = 0 if len(bank) else None
        self.preview.accent_rgb = (scfg.wheel_color() or None) if scfg is not None else None
        self.preview.lib_dropped.connect(self._on_lib_dropped)
        self.preview.slot_dropped.connect(self._on_slot_dropped)
        self.preview.slot_clicked.connect(self._on_slot_clicked)
        wh.addWidget(self.preview, 1, Qt.AlignCenter)
        rl.addWidget(wheel_holder, 1)

        self.page_wheel.changed.connect(self._on_wheel_changed)
        self.page_wheel.palette_changed.connect(self._on_palette)
        self.page_wheel.wheel_color_changed.connect(self._on_wheel_color)
        self.page_wheel.wheel_switch.connect(self.wheel_switch_requested.emit)
        self.page_key.changed.connect(self._on_cfg_changed)
        self.page_mic.changed.connect(self._on_audio_changed)

        self.detail = SlotDetail(scfg)
        self.detail.setting_changed.connect(self._on_setting_changed)
        self.detail.preview_requested.connect(self.preview_requested.emit)
        self.detail.edit_combo_requested.connect(self._open_combo_editor)
        sel = self.preview.selected
        self.detail.set_sound(bank.full_at(sel) if sel is not None else None)
        rl.addWidget(self.detail)
        body.addWidget(right, 1)

        self._tip: _FirstRunTip | None = None

    # ---- 首次启动引导 ----
    def _maybe_show_help_tip(self) -> None:
        """第一次打开设置窗口时，浮一张卡告诉用户去翻常见问题。看过就不再弹。"""
        if self._tip is not None or bool(self.cfg.get("help_tip_shown", False)):
            return
        # 等窗口先画出来再浮上来，避免开窗口的瞬间跟界面一起闪
        QTimer.singleShot(400, self._show_help_tip)

    def _show_help_tip(self) -> None:
        if self._tip is not None or not self.isVisible():
            return
        tip = _FirstRunTip(self)
        tip.setGeometry(self.root.geometry())
        tip.open_faq.connect(self._on_tip_go)
        tip.dismissed.connect(self._close_help_tip)
        tip.show()
        tip.raise_()
        self._tip = tip

    def _on_tip_go(self) -> None:
        """「去看看」：关掉卡片，直接把人送到常见问题那一节。"""
        self._close_help_tip()
        self.tabs.setCurrentWidget(self.page_help)
        self.page_help.focus_faq()

    def _close_help_tip(self) -> None:
        tip, self._tip = self._tip, None
        if tip is not None:
            tip.hide()
            tip.deleteLater()
        if not bool(self.cfg.get("help_tip_shown", False)):
            self.cfg["help_tip_shown"] = True
            try:
                sr.save_config(self.cfg)
            except Exception as e:      # 存不下也不该拦住用户用软件
                print(f"[cfg] 引导标记没存下：{e}")

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        if self._tip is not None:
            self._tip.setGeometry(self.root.geometry())

    # ---- 拖放与增删 ----
    def _apply(self) -> None:
        """改动落实：存盘、按新顺序重排槽位、刷新界面、通知主程序。"""
        self.scfg.save()
        self.bank.reload()
        self._refresh_all()

    def _refresh_all(self) -> None:
        self.preview.bank = self.bank
        self.preview.update()
        n = len(self.bank)
        self.lbl_count.setText(f"{n} 个槽位")
        if n == 0:
            self.preview.selected = None
            self.detail.set_sound(None)
        else:
            sel = self.preview.selected
            if sel is None or sel >= n:
                sel = n - 1
                self.preview.selected = sel
            self.detail.set_sound(self.bank.full_at(sel))
        self.page_lib.refresh()
        self.changed.emit()

    def _on_lib_dropped(self, name: str, sid: int) -> None:
        """从音效库拖到轮盘：丢在中心 = 追加，丢在格子上 = 放进/替换那一格。"""
        if sid == ADD_TO_END:
            ok = self.scfg.add(name)
        else:
            ok = self.scfg.put_at_slot(sid, name)
        if not ok:
            return
        self._apply()
        # 落位之后 order 可能重排，用"名字 -> 新下标"重新定位选中项
        if self.scfg.is_on_wheel(name):
            self.preview.selected = self.scfg.order.index(self.scfg.canon(name))
            self.preview.update()
            self.detail.set_sound(self.bank.full_at(self.preview.selected))

    def _on_slot_dropped(self, src: int, dst: int) -> None:
        """轮盘内部拖动：两个槽位互换（外圈可以换成空格子）。"""
        if src == dst:
            return
        if self.scfg.swap_slots(src, dst):
            self._apply()

    # ---- 组合音效 ----
    def _on_combo_new(self) -> None:
        """新建一个空组合并立刻打开编辑器（新建却看不到东西最让人迷惑）。"""
        cdef = self.scfg.new_combo()
        self.scfg.save()
        self._apply()
        self._open_combo_editor(cdef.cid)

    def _on_combo_delete(self, cid: str) -> None:
        cdef = self.scfg.combos.get(cid)
        if cdef is None:
            return
        ret = QMessageBox.question(
            self, "删除组合",
            f"确定删除组合「{cdef.name}」吗？\n"
            "它只是从轮盘上撤下来，成员音效文件不会被删。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        self.scfg.delete_combo(cid)
        self.scfg.save()
        self._apply()

    def _open_combo_editor(self, cid: str) -> None:
        cdef = self.scfg.combos.get(cid)
        if cdef is None:
            return
        dlg = ComboEditorDialog(self.scfg, cdef, self.engine, self, self.cfg)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        # 编辑期间改了成员/参数：轮盘名字、槽位详情、引擎解码都得跟着刷新
        dlg.changed.connect(self._on_combo_changed)
        # 关掉编辑器就把这条组合预渲染进缓存，下次按键零等待
        dlg.finished.connect(lambda _r, c=cdef: self._warm_combo(c))
        dlg.show()

    def _warm_combo(self, cdef) -> None:
        if self.engine is None:
            return
        try:
            self.engine.warm_combo(cdef)
        except Exception:
            pass

    def _on_combo_changed(self) -> None:
        """组合被改动：攒一小会儿再刷新，别每敲一下就把整盘重来一遍。

        以前这里每次改动都会走到"重新解码全部音效"，编辑时拖一下数字
        就要等一次全量解码，手感很糟；而且音频参数是播放时实时读的，
        根本没有重新解码的必要。
        """
        if getattr(self, "_combo_timer", None) is None:
            self._combo_timer = QTimer(self)
            self._combo_timer.setSingleShot(True)
            self._combo_timer.setInterval(150)
            self._combo_timer.timeout.connect(self._refresh_combo_now)
        self._combo_timer.start()
        # 只重绑快捷键（组合可能刚设了专属热键），不重新解码音频
        self.params_changed.emit()

    def _refresh_combo_now(self) -> None:
        self.bank.reload()
        self.preview.bank = self.bank
        sel = self.preview.selected
        if sel is not None:
            self.detail.set_sound(self.bank.full_at(sel))
        self.preview.update()
        self.page_lib.refresh()

    def _on_slot_removed(self, sid: int) -> None:
        """把轮盘格子拖回音效库 = 从轮盘下盘。

        传进来的是**槽位号**（0~7 内圈 / 8~19 外圈位置），不是音效下标。
        内圈里两者数值恰好相等，所以以前只在第 0 格上试是看不出问题的；
        外圈槽位号是 8~19，直接拿去当 order 下标会全部越界被挡掉，
        表现就是"外圈的音效怎么拖都取消不掉"。必须先换算。
        """
        if self.bank is None:
            return
        idx = sr.index_of_slot(sid, len(self.bank), sr.outer_index_map_of(self.bank))
        if idx is None or not (0 <= idx < len(self.scfg.order)):
            return
        self.scfg.remove(self.scfg.order[idx])
        self._apply()

    def _on_slot_clicked(self, idx: int) -> None:
        self.preview.selected = idx
        self.preview.update()
        self.detail.set_sound(self.bank.full_at(idx))

    def _on_setting_changed(self, _name: str) -> None:
        # 只存盘 + 重绑快捷键。参数是播放时实时读的，没必要重新解码音频，
        # 否则拖一下音量滑块就会把整盘音效解码几十遍，界面直接卡住。
        self.scfg.save()
        self.page_key.refresh_conflicts()
        self.params_changed.emit()

    def _on_cfg_changed(self) -> None:
        sr.save_config(self.cfg)
        self.changed.emit()

    def _on_audio_changed(self) -> None:
        """麦克风相关改动：只重建音频链路，不用重新解码音效。"""
        sr.save_config(self.cfg)
        self.audio_changed.emit()

    def _on_wheel_changed(self) -> None:
        """外观改了要立刻反映到预览上，否则改半天看不到效果。"""
        cfg = self.cfg
        self.preview_cfg["inner_ratio"] = cfg["inner_ratio"]
        self.preview_cfg["opacity"] = cfg["opacity"]
        self.preview_cfg["outer_thickness"] = cfg["outer_thickness"]
        self.preview_cfg["show_names"] = cfg["show_names"]
        # 「整体大小」不传给预览：预览固定按 100% 的样子画，
        # 拖那个滑块时只有游戏里的轮盘会变，预览保持稳定不跟着涨缩
        self.preview_cfg["wheel_scale"] = 1.0
        # 预览半径按比例缩放，跟着真实半径走但始终放得下
        r = preview_radius_of(cfg)
        if r != int(self.preview_cfg["wheel_radius"]):
            self.preview_cfg["wheel_radius"] = r
            side = int(r * 2 + PREVIEW_PAD)
            self.preview.setFixedSize(side, side)
        self.preview.update()
        sr.save_config(cfg)

    def _on_palette(self, hexv: str) -> None:
        """应用主题色变了：换色 + 重新套一遍样式表，整个界面立刻跟着变。"""
        theme.set_accent(hexv)
        self.apply_theme()
        sr.save_config(self.cfg)
        # 托盘图标也是按特征色画的，得让主程序重画一次
        self.changed.emit()

    def apply_theme(self) -> None:
        """把当前主题色套到所有窗口和内置的着色控件上。"""
        self.setStyleSheet(build_qss())
        self._restyle_children()
        self._sync_preview_color()
        self.preview.update()
        self.page_wheel.refresh_wheels()   # 列表里的颜色标记也要重画

    def _restyle_children(self) -> None:
        """行内写死了 accent 颜色的地方，换色后手动补一次。

        这些控件在构造时把颜色拼进了 styleSheet（父窗口的 QSS 管不到），
        数量不多，集中在这里处理，比给每个控件挂 objectName 简单。
        """
        from PySide6.QtWidgets import QLabel as _L

        for lab in self.findChildren(_L):
            ss = lab.styleSheet()
            if "font-size:11px;font-weight:600" in ss or "font-weight:600" in ss:
                if "#2ed36c" in ss.lower() or "color:" in ss:
                    lab.setStyleSheet(
                        f"color:{accent_hex()};font-size:{'11' if '11px' in ss else '12'}px;"
                        "font-weight:600;background:transparent;"
                    )

    def _sync_preview_color(self) -> None:
        """让预览用"当前这套轮盘"的颜色（没设就跟随主题色）。"""
        color = ""
        if self.scfg is not None:
            try:
                color = self.scfg.wheel_color()
            except Exception:
                color = ""
        self.preview.accent_rgb = color or None

    def _on_wheel_color(self, hexv: str) -> None:
        """只换了轮盘颜色：重画预览，界面配色不动。"""
        self._sync_preview_color()
        self.preview.update()
        self.page_wheel.refresh_wheels()

    def on_wheel_switched(self) -> None:
        """主程序真的切完轮盘了：把界面上的东西全刷一遍。"""
        self.bank.reload()
        self._sync_preview_color()
        self._refresh_all()
        self.page_wheel.refresh_wheels()
        self.page_wheel._refresh_color_dots()
        self.detail.set_sound(
            self.bank.full_at(self.preview.selected)
            if self.preview.selected is not None else None
        )

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        # 每次打开都重新扫一遍：用户可能刚在文件夹里放了/删了文件
        self.bank.reload()
        self._sync_preview_color()
        self._refresh_all()
        self.page_wheel.refresh_wheels()
        self.page_wheel._refresh_color_dots()
        self._maybe_show_help_tip()

    def closeEvent(self, e) -> None:  # noqa: N802
        e.ignore()
        # 引导卡还开着就一起收掉，顺便把「看过」记下来，下次打开别再打扰
        if self._tip is not None:
            self._close_help_tip()
        self.hide()
        self.closed.emit()
