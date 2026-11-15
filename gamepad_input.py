"""通过 Windows XInput 读取手柄快捷键。"""

from __future__ import annotations

import ctypes
import time
from collections.abc import Callable


_DIGITAL_BUTTONS = {
    "pad_a": (0x1000, "手柄 A"),
    "pad_b": (0x2000, "手柄 B"),
    "pad_x": (0x4000, "手柄 X"),
    "pad_y": (0x8000, "手柄 Y"),
    "pad_lb": (0x0100, "手柄 LB"),
    "pad_rb": (0x0200, "手柄 RB"),
    "pad_back": (0x0020, "手柄 Back"),
    "pad_start": (0x0010, "手柄 Start"),
    "pad_ls": (0x0040, "手柄 LS"),
    "pad_rs": (0x0080, "手柄 RS"),
    "pad_up": (0x0001, "手柄 ↑"),
    "pad_down": (0x0002, "手柄 ↓"),
    "pad_left": (0x0004, "手柄 ←"),
    "pad_right": (0x0008, "手柄 →"),
}
BUTTON_LABELS = {token: label for token, (_, label) in _DIGITAL_BUTTONS.items()}
BUTTON_LABELS.update(pad_lt="手柄 LT", pad_rt="手柄 RT")

_SCAN_INTERVAL = 1.0
_TRIGGER_PRESS = 128
_TRIGGER_RELEASE = 100
_LOAD_LIBRARY_SEARCH_SYSTEM32 = 0x0800

# 按键位掩码、LT、RT。None 表示该槽位没有可读的手柄。
_Reader = Callable[[int], tuple[int, int, int] | None]


class _XInputGamepad(ctypes.Structure):
    _fields_ = [
        ("wButtons", ctypes.c_uint16),
        ("bLeftTrigger", ctypes.c_uint8),
        ("bRightTrigger", ctypes.c_uint8),
        ("sThumbLX", ctypes.c_int16),
        ("sThumbLY", ctypes.c_int16),
        ("sThumbRX", ctypes.c_int16),
        ("sThumbRY", ctypes.c_int16),
    ]


class _XInputState(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_uint32), ("Gamepad", _XInputGamepad)]


def _load_reader() -> _Reader | None:
    load_dll = getattr(ctypes, "WinDLL", None)
    if load_dll is None:
        return None
    for name in ("xinput1_4.dll", "xinput9_1_0.dll"):
        try:
            get_state = load_dll(name, winmode=_LOAD_LIBRARY_SEARCH_SYSTEM32).XInputGetState
        except (OSError, AttributeError):
            continue
        get_state.argtypes = (ctypes.c_uint32, ctypes.POINTER(_XInputState))
        get_state.restype = ctypes.c_uint32
        state = _XInputState()

        def read(index: int) -> tuple[int, int, int] | None:
            if get_state(index, ctypes.byref(state)) != 0:
                return None
            gamepad = state.Gamepad
            return gamepad.wButtons, gamepad.bLeftTrigger, gamepad.bRightTrigger

        return read
    return None


class GamepadInput:
    """每次轮询刷新按键状态。断开当前手柄的当次轮询会标记 cancelled。"""

    def __init__(self, *, reader: _Reader | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self._read = reader if reader is not None else _load_reader()
        self._clock = clock
        self._next_scan = float("-inf")
        self._held: set[str] = set()
        self._suppressed: set[str] = set()
        self.buttons: set[str] = set()
        self.controller_index: int | None = None
        self.cancelled = False

    @property
    def available(self) -> bool:
        return self._read is not None

    @property
    def connected(self) -> bool:
        return self.controller_index is not None

    def down(self, token: str) -> bool:
        return token in self.buttons

    def update(self) -> None:
        self.cancelled = False
        if self._read is None:
            return

        index = self.controller_index
        connecting = index is None
        if index is None:
            now = self._clock()
            if now < self._next_scan:
                return
            self._next_scan = now + _SCAN_INTERVAL
            for candidate in range(4):
                frame = self._read(candidate)
                if frame is not None:
                    self.controller_index = candidate
                    break
            else:
                return
        else:
            frame = self._read(index)
            if frame is None:
                self.controller_index = None
                self.cancelled = True
                self._held.clear()
                self._suppressed.clear()
                self.buttons.clear()
                self._next_scan = self._clock() + _SCAN_INTERVAL
                return

        mask, lt, rt = frame
        held = {token for token, (bit, _) in _DIGITAL_BUTTONS.items() if mask & bit}
        for token, value in (("pad_lt", lt), ("pad_rt", rt)):
            threshold = _TRIGGER_RELEASE + 1 if token in self._held else _TRIGGER_PRESS
            if value >= threshold:
                held.add(token)
        self._held = held
        if connecting:
            # 连上时已经按住的键要先松开，免得意外触发快捷键。
            self._suppressed = held.copy()
        else:
            self._suppressed.intersection_update(held)
        self.buttons = held - self._suppressed
