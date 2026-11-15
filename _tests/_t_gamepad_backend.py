"""验证 XInput 的原始数据读取、设备切换和按键状态。"""

import ctypes
import struct
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gamepad_input import BUTTON_LABELS, GamepadInput


class GamepadBackendTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.frames = {}
        self.calls = []
        self.pad = GamepadInput(reader=self.read, clock=lambda: self.now)

    def read(self, index):
        self.calls.append(index)
        return self.frames.get(index)

    def test_decodes_digital_buttons_and_ignores_reserved_bits(self):
        self.frames[0] = (0, 0, 0)
        self.pad.update()

        expected = {
            0x0001: "pad_up", 0x0002: "pad_down", 0x0004: "pad_left",
            0x0008: "pad_right", 0x0010: "pad_start", 0x0020: "pad_back",
            0x0040: "pad_ls", 0x0080: "pad_rs", 0x0100: "pad_lb",
            0x0200: "pad_rb", 0x1000: "pad_a", 0x2000: "pad_b",
            0x4000: "pad_x", 0x8000: "pad_y",
        }
        self.assertEqual(set(BUTTON_LABELS), {*expected.values(), "pad_lt", "pad_rt"})
        for mask, token in expected.items():
            with self.subTest(token=token):
                self.frames[0] = (mask | 0x0C00, 0, 0)
                self.pad.update()
                self.assertEqual(self.pad.buttons, {token})

        self.frames[0] = (0x1101, 0, 0)
        self.pad.update()
        self.assertEqual(self.pad.buttons, {"pad_a", "pad_lb", "pad_up"})

    def test_triggers_have_independent_press_and_release_thresholds(self):
        self.frames[0] = (0, 0, 0)
        self.pad.update()
        for lt, rt, expected in (
            (127, 128, {"pad_rt"}),
            (128, 101, {"pad_lt", "pad_rt"}),
            (110, 100, {"pad_lt"}),
            (100, 110, set()),
            (110, 128, {"pad_rt"}),
        ):
            with self.subTest(lt=lt, rt=rt):
                self.frames[0] = (0, lt, rt)
                self.pad.update()
                self.assertEqual(self.pad.buttons, expected)

    def test_connection_suppresses_only_the_buttons_already_held(self):
        self.frames[0] = (0x1000, 180, 0)
        self.pad.update()
        self.assertTrue(self.pad.available)
        self.assertTrue(self.pad.connected)
        self.assertEqual(self.pad.buttons, set())

        self.frames[0] = (0x3000, 110, 0)
        self.pad.update()
        self.assertEqual(self.pad.buttons, {"pad_b"})

        self.frames[0] = (0, 100, 0)
        self.pad.update()
        self.frames[0] = (0x1000, 128, 0)
        self.pad.update()
        self.assertEqual(self.pad.buttons, {"pad_a", "pad_lt"})

    def test_active_slot_survives_new_device_and_loss_cancels_one_update(self):
        self.frames[1] = (0, 0, 0)
        self.frames[3] = (0, 0, 0)
        self.pad.update()
        self.assertEqual(self.pad.controller_index, 1)
        self.assertEqual(self.calls, [0, 1])

        self.now = 3.0
        self.frames[0] = (0x2000, 0, 0)
        self.frames[1] = (0x1000, 0, 0)
        self.pad.update()
        self.assertEqual(self.calls, [0, 1, 1])
        self.assertTrue(self.pad.down("pad_a"))

        del self.frames[1]
        self.pad.update()
        self.assertTrue(self.pad.cancelled)
        self.assertFalse(self.pad.connected)
        self.assertIsNone(self.pad.controller_index)
        self.assertEqual(self.pad.buttons, set())

        self.pad.update()
        self.assertFalse(self.pad.cancelled)
        self.assertEqual(self.calls, [0, 1, 1, 1])

        self.now = 4.0
        self.pad.update()
        self.assertEqual(self.pad.controller_index, 0)
        self.assertFalse(self.pad.down("pad_b"))
        self.frames[0] = (0, 0, 0)
        self.pad.update()
        self.frames[0] = (0x2000, 0, 0)
        self.pad.update()
        self.assertTrue(self.pad.down("pad_b"))

    def test_disconnected_scans_at_most_once_per_second(self):
        self.pad.update()
        for tick in range(1, 125):
            self.now = tick * 0.008
            self.pad.update()
        self.assertEqual(self.calls, [0, 1, 2, 3])
        self.assertFalse(self.pad.cancelled)
        self.now = 1.0
        self.pad.update()
        self.assertEqual(self.calls, [0, 1, 2, 3, 0, 1, 2, 3])

    def test_native_reader_falls_back_and_decodes_windows_state_layout(self):
        mask, lt, rt = 0, 0, 0

        def get_state(index, state):
            if index != 0:
                return 1167  # ERROR_DEVICE_NOT_CONNECTED
            data = struct.pack("<IHBBhhhh", 1, mask, lt, rt, -32768, 32767, 0, 0)
            ctypes.memmove(state, data, len(data))
            return 0

        def load_dll(name, *, winmode):
            if name == "xinput1_4.dll":
                raise OSError("XInput 1.4 unavailable")
            self.assertEqual(name, "xinput9_1_0.dll")
            return SimpleNamespace(XInputGetState=get_state)

        with patch("ctypes.WinDLL", side_effect=load_dll, create=True):
            pad = GamepadInput()
        pad.update()
        mask, lt, rt = 0x8008, 255, 128
        pad.update()
        self.assertEqual(pad.buttons, {"pad_y", "pad_right", "pad_lt", "pad_rt"})


if __name__ == "__main__":
    unittest.main()
