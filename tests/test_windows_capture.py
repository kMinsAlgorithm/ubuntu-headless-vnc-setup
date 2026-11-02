"""Screenshot hotkeys; no screenshot or clipboard access in automated tests."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'windows'))
from capture_keys import CaptureKeys, MARKER


class CaptureKeyTests(unittest.TestCase):
    def setUp(self):
        self.keys = CaptureKeys(enabled=True)

    def event(self, key, up=False, flags=0x10, extra=0):
        return self.keys.handle(key, flags | (0x80 if up else 0), extra)

    def chord(self, digit):
        self.event(0xA2)
        self.event(0xA0)
        self.assertTrue(self.event(digit))

    def release(self, digit):
        self.assertTrue(self.event(digit, up=True))
        self.event(0xA0, up=True)
        self.event(0xA2, up=True)

    def test_full_screen_waits_for_modifier_and_digit_release(self):
        self.chord(0x33)
        self.assertIsNone(self.keys.take())
        self.release(0x33)
        self.assertEqual(self.keys.take(), 'full')
        self.assertIsNone(self.keys.take())

    def test_region_and_right_hand_modifiers(self):
        self.event(0xA3)
        self.event(0xA1)
        self.assertTrue(self.event(0x34))
        self.event(0xA3, up=True)
        self.event(0xA1, up=True)
        self.assertTrue(self.event(0x34, up=True))
        self.assertEqual(self.keys.take(), 'region')

    def test_repeated_down_does_not_create_multiple_captures(self):
        self.chord(0x33)
        self.assertTrue(self.event(0x33))
        self.release(0x33)
        self.assertEqual(self.keys.take(), 'full')
        self.assertIsNone(self.keys.take())

    def test_physical_and_self_injected_control_combinations_are_untouched(self):
        for extra, flags in ((0, 0), (MARKER, 0x10)):
            for key in (0xA2, 0xA0, 0x33):
                self.assertFalse(self.event(key, flags=flags, extra=extra))
        self.assertEqual(self.keys.modifiers, set())
        self.assertIsNone(self.keys.take())

    def test_command_shift_is_not_used_for_the_windows_capture(self):
        self.event(0xA4)
        self.event(0xA2, extra=MARKER)
        self.event(0xA0)
        self.assertFalse(self.event(0x33))
        self.assertIsNone(self.keys.take())

    def test_copy_paste_and_plain_numbers_are_not_intercepted(self):
        for key in (0x33, 0x34, 0x41, 0x43, 0x56):
            self.assertFalse(self.event(key))
        self.event(0xA2)
        self.assertFalse(self.event(0x43))
        self.assertFalse(self.event(0x56))

    def test_disabled_profile_never_intercepts_or_tracks_keys(self):
        keys = CaptureKeys(enabled=False)
        for key in (0xA2, 0xA0, 0x34):
            self.assertFalse(keys.handle(key, 0x10, 0))
        self.assertIsNone(keys.take())

    def test_pending_capture_is_bounded_while_keys_are_held(self):
        self.chord(0x33)
        self.assertTrue(self.event(0x34))
        self.assertEqual(list(self.keys.pending), ['full'])

    def test_altgr_and_windows_modifier_combinations_are_untouched(self):
        for extra_modifier in (0xA5, 0x5B, 0x5C):
            keys = CaptureKeys(enabled=True)
            for key in (0xA2, 0xA0, extra_modifier):
                self.assertFalse(keys.handle(key, 0x10, 0))
            self.assertFalse(keys.handle(0x34, 0x10, 0))
            self.assertIsNone(keys.take())


if __name__ == '__main__':
    unittest.main()
