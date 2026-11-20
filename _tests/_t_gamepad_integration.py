"""验证手柄录入、配置读写与音效触发。"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QWidget

import sr_roulette as sr
from gamepad_input import GamepadInput
from settings_window import SettingsWindow
from sounds_config import (
    TRIGGER_HOLD,
    TRIGGER_RELEASE,
    TRIGGER_REPEAT,
    TRIGGER_TAP,
    SoundsConfig,
)


PAD_A = 0x1000
PAD_B = 0x2000
APP = QApplication.instance() or QApplication([])


class AudioRecorder:
    def __init__(self, scfg):
        self.bank = SimpleNamespace(scfg=scfg)
        self.played = []
        self.stopped = []
        self.token = 0
        self.repeated = 0

    def new_token(self):
        self.token += 1
        return self.token

    def play_named(self, name, token=0):
        self.played.append((name, token))

    def stop_token(self, token):
        self.stopped.append(token)

    def play_repeat_last(self):
        self.repeated += 1

    @property
    def names(self):
        return [name for name, _ in self.played]


class GamepadIntegrationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.scfg = SoundsConfig(self.root / "sounds.json")
        self.cfg = dict(sr.DEFAULT_CONFIG, hotkey="y", repeat_last_key="",
                        cycle_key="", switch_key="")
        self.now = 0.0
        self.frame = (0, 0, 0)
        self.keyboard = set()
        self.enterContext(patch.object(sr, "is_down", self.keyboard.__contains__))
        self.enterContext(patch.object(sr.time, "monotonic", lambda: self.now))

    def read(self, index):
        return self.frame if index == 0 else None

    def gamepad(self):
        return GamepadInput(reader=self.read, clock=lambda: self.now)

    def bind(self, name, hotkey, mode=TRIGGER_TAP):
        self.scfg.order.append(name)
        setting = self.scfg.setting(name)
        setting.hotkey = hotkey
        setting.trigger_mode = mode
        setting.repeat_ms = 200
        return setting

    def start_poller(self):
        self.audio = AudioRecorder(self.scfg)
        self.poller = sr.InputPoller(self.cfg, SimpleNamespace(active=False),
                                     self.audio, gamepad=self.gamepad())

    def tick(self, mask, elapsed=0):
        self.now += elapsed
        self.frame = None if mask is None else (mask, 0, 0)
        self.poller.tick()

    def test_shared_button_runs_each_mode_and_keyboard_still_works(self):
        self.bind("tap.wav", "pad_a")
        self.bind("hold.wav", "pad_a", TRIGGER_HOLD)
        self.bind("release.wav", "pad_a", TRIGGER_RELEASE)
        self.bind("repeat.wav", "pad_a", TRIGGER_REPEAT)
        self.bind("key.wav", "f8")
        self.start_poller()

        self.tick(PAD_A)
        self.assertEqual(self.audio.names, ["tap.wav", "hold.wav", "repeat.wav"])
        hold_token = self.audio.played[1][1]
        self.tick(PAD_A, elapsed=0.1)
        self.assertEqual(len(self.audio.played), 3)
        self.tick(PAD_A, elapsed=0.11)
        self.assertEqual(self.audio.played[-1], self.audio.played[2])
        self.tick(0)
        self.assertEqual(self.audio.names[-1], "release.wav")
        self.assertEqual(self.audio.stopped, [hold_token])

        self.keyboard.add(sr.vk_of("f8"))
        self.tick(0)
        self.tick(0)
        self.assertEqual(self.audio.names[-1], "key.wav")
        self.assertEqual(self.audio.names.count("key.wav"), 1)

    def test_disconnect_stops_hold_and_repeat_without_playing_release(self):
        self.bind("hold.wav", "pad_a", TRIGGER_HOLD)
        self.bind("release.wav", "pad_a", TRIGGER_RELEASE)
        self.bind("repeat.wav", "pad_a", TRIGGER_REPEAT)
        self.start_poller()

        self.tick(PAD_A)
        hold_token = self.audio.played[0][1]
        self.tick(None, elapsed=0.3)
        self.assertEqual(self.audio.stopped, [hold_token])
        self.tick(PAD_A, elapsed=1.1)
        self.tick(PAD_A, elapsed=0.3)
        self.tick(0)
        self.assertEqual(self.audio.names, ["hold.wav", "repeat.wav"])

        self.tick(PAD_A)
        self.tick(0)
        self.assertEqual(self.audio.names[-3:], ["hold.wav", "repeat.wav", "release.wav"])

    def test_press_during_settings_or_user_pause_does_not_play_after_resuming(self):
        self.bind("tap.wav", "pad_a")
        self.bind("release.wav", "pad_a", TRIGGER_RELEASE)
        self.start_poller()

        for pause in ("settings", "user"):
            with self.subTest(pause=pause):
                self.audio.played.clear()
                if pause == "settings":
                    self.poller.paused = lambda: True
                else:
                    self.poller.set_user_pause(True)
                self.tick(PAD_A)

                if pause == "settings":
                    self.poller.paused = None
                else:
                    self.poller.set_user_pause(False)
                self.tick(PAD_A)
                self.tick(0)
                self.assertEqual(self.audio.names, [])
                self.tick(PAD_A)
                self.tick(0)
                self.assertEqual(self.audio.names, ["tap.wav", "release.wav"])

    def test_rebuilding_while_button_is_held_does_not_play_its_release(self):
        self.bind("release.wav", "pad_a", TRIGGER_RELEASE)
        self.start_poller()
        self.frame = (PAD_A, 0, 0)
        self.poller.rebuild_bindings()
        self.tick(PAD_A)
        self.tick(0)
        self.assertEqual(self.audio.names, [])
        self.tick(PAD_A)
        self.tick(0)
        self.assertEqual(self.audio.names, ["release.wav"])

    def test_saved_global_binding_follows_wheel_and_ignores_retired_repeat_key(self):
        self.bind("global.wav", "pad_a").global_hotkey = True
        self.bind("local.wav", "pad_a")
        alternate = self.scfg.new_wheel(copy_current=False)
        self.assertTrue(self.scfg.switch_wheel(alternate.wid))
        self.scfg.save()
        self.scfg = SoundsConfig(self.scfg.path)
        self.scfg.load()
        self.assertEqual(self.scfg.current, alternate.wid)
        self.start_poller()

        self.tick(PAD_A)
        self.assertEqual(self.audio.names, ["global.wav"])
        self.tick(0)
        # v0.9.3 删掉了「重复上一个」全局键：老配置里残留的 repeat_last_key
        # 不再抢注，再按一次靠的是音效自己的全局热键重放。
        self.cfg["repeat_last_key"] = "pad_a"
        self.poller.rebuild_bindings()
        self.tick(PAD_A)
        self.assertEqual(self.audio.names, ["global.wav", "global.wav"])
        self.assertEqual(self.audio.repeated, 0)

    def test_focused_capture_saves_and_clears_without_capturing_in_background(self):
        sound = "record.wav"
        self.bind(sound, "f8")
        (self.root / sound).touch()
        self.enterContext(patch.object(sr, "SOUNDS_DIR", self.root))
        self.enterContext(patch.object(sr, "CONFIG_PATH", self.root / "config.json"))
        self.enterContext(patch.object(sr, "GamepadInput", self.gamepad))
        bank = sr.SoundBank(sr.MAX_SLOTS, self.scfg)
        settings = SettingsWindow(self.cfg, self.scfg, bank)
        self.addCleanup(settings.close)
        settings.detail.set_sound(sound)
        key_box = settings.detail.hotkey
        key_edit = key_box.edit
        self.frame = (PAD_A, 0, 0)
        settings.show()
        settings.activateWindow()
        key_edit.setFocus()
        APP.processEvents()
        self.assertTrue(key_edit.hasFocus())
        key_edit._poll_gamepad()
        self.assertEqual(key_box.key_name, "f8")

        self.frame = (0, 0, 0)
        key_edit._poll_gamepad()
        self.frame = (PAD_A, 0, 0)
        key_edit._poll_gamepad()
        self.assertEqual(key_box.key_name, "pad_a")
        self.assertEqual(key_box.text(), sr.BUTTON_LABELS["pad_a"])
        saved = SoundsConfig(self.scfg.path)
        saved.load()
        self.assertEqual(saved.setting(sound).hotkey, "pad_a")

        background = QWidget()
        self.addCleanup(background.close)
        background.show()
        background.activateWindow()
        APP.processEvents()
        self.assertFalse(key_edit.hasFocus())
        self.frame = (PAD_B, 0, 0)
        key_edit._poll_gamepad()
        self.assertEqual(key_box.key_name, "pad_a")

        key_box.clear_key()
        saved.load()
        self.assertEqual(saved.setting(sound).hotkey, "")

    def test_modeless_child_dialog_keeps_settings_hotkeys_paused(self):
        settings = QWidget()
        child = QDialog(settings)
        self.addCleanup(settings.close)
        self.addCleanup(child.close)
        settings.show()
        child.show()
        child.activateWindow()
        APP.processEvents()
        self.assertIs(APP.activeWindow(), child)
        self.assertTrue(sr.settings_blocks_hotkey(settings))


if __name__ == "__main__":
    unittest.main(verbosity=2)
