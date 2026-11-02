"""Injected jamo routing only; does not inspect or change the real IME."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'windows'))
from ime_bridge import JamoMapper, JAMO_KEYS, MARKER, ForegroundIme, is_plain_remote_space


class JamoTests(unittest.TestCase):
    def setUp(self):
        self.mapper = JamoMapper()
        self.modes = []
        self.keys = []

    def mode(self, native):
        self.modes.append(native)
        return True

    def tap(self, vk, shifted):
        self.keys.append((vk, shifted))
        return True

    def event(self, character, up=False, flags=0x10, extra=0, shortcut=False):
        return self.mapper.handle(0xE7, ord(character), flags | (0x80 if up else 0), extra,
                                  self.mode, self.tap, shortcut)

    def test_ganada_jamo_is_forwarded_as_two_beolsik_keys(self):
        for character in 'ㄱㅏㄴㅏㄷㅏ':
            self.assertTrue(self.event(character))
            self.assertTrue(self.event(character, up=True))
        self.assertEqual(''.join(chr(vk).lower() for vk, shifted in self.keys), 'rkskek')
        self.assertTrue(all(self.modes))

    def test_shifted_jamo_keeps_double_consonant_and_vowel_distinctions(self):
        for character in 'ㄲㄸㅃㅆㅉㅒㅖ':
            self.event(character)
        self.assertEqual(self.keys, [(ord(key), True) for key in 'REQTWO'+'P'])

    def test_english_source_commits_korean_and_switches_back(self):
        self.event('ㄱ')
        self.mapper.handle(0x41, 0, 0x10, 0, self.mode, self.tap)
        self.assertEqual(self.modes, [True, False])

    def test_unicode_english_source_is_also_recognized(self):
        self.event('ㄱ')
        self.event('a')
        self.assertEqual(self.modes, [True, False])

    def test_ascii_in_legacy_caps_mode_does_not_override_server_ime(self):
        self.mapper.handle(0x52, 0, 0x10, 0, self.mode, self.tap)
        self.assertEqual(self.modes, [])

    def test_explicit_remote_hangul_key_returns_to_legacy_switching(self):
        self.event('ㄱ')
        self.mapper.handle(0x15, 0, 0x10, 0, self.mode, self.tap)
        self.mapper.handle(0x41, 0, 0x10, 0, self.mode, self.tap)
        self.assertEqual(self.modes, [True])

    def test_ctrl_shortcuts_do_not_change_input_language(self):
        self.event('ㄱ')
        self.mapper.handle(0x43, 0, 0x10, 0, self.mode, self.tap, shortcut=True)
        self.assertEqual(self.modes, [True])

    def test_physical_and_self_injected_events_are_not_reinterpreted(self):
        self.assertFalse(self.event('ㄱ', flags=0))
        self.assertFalse(self.event('ㄱ', extra=MARKER))
        self.assertEqual(self.keys, [])

    def test_complete_syllables_and_compound_jamo_are_untouched(self):
        for text in ('가','ㄳ','A','é'):
            self.assertFalse(self.event(text))
        self.assertEqual(self.keys, [])

    def test_blocked_ime_does_not_drop_original_jamo(self):
        handled = self.mapper.handle(0xE7, ord('ㄱ'), 0x10, 0, lambda _: False, self.tap)
        self.assertFalse(handled)
        self.assertEqual(self.keys, [])

    def test_blocked_native_injection_keeps_original_down_and_up(self):
        self.assertFalse(self.mapper.handle(0xE7, ord('ㄱ'), 0x10, 0, self.mode, lambda *_: False))
        self.assertFalse(self.event('ㄱ', up=True))

    def test_only_the_approved_single_jamo_are_mapped(self):
        self.assertEqual(len(JAMO_KEYS), 33)
        self.assertTrue(all(len(value)==1 and value.isascii() and value.isalpha() for value in JAMO_KEYS.values()))


class FakeIme(ForegroundIme):
    def __init__(self, mode=9):
        self.mode, self.opened, self.cache, self.calls = mode, 1, None, []

    def foreground(self):
        return 10, 0x4120412, 11

    def command(self, window, command, value=0):
        self.calls.append((command, value))
        if command == 1:
            return self.mode
        if command == 5:
            return self.opened
        if command == 2:
            self.mode = value
        if command == 6:
            self.opened = value
        return 0


class WidthTests(unittest.TestCase):
    def test_hangul_selection_clears_full_width_without_changing_other_modes(self):
        ime = FakeIme(mode=8 | 0x40)
        self.assertTrue(ime.set_native(True))
        self.assertEqual(ime.mode, 1 | 0x40)

    def test_english_selection_also_clears_full_width(self):
        ime = FakeIme()
        self.assertTrue(ime.set_native(False))
        self.assertEqual(ime.mode, 0)
        self.assertEqual(ime.opened, 0)

    def test_same_field_cache_does_not_hide_an_external_width_change(self):
        ime = FakeIme()
        self.assertTrue(ime.set_native(True))
        ime.mode |= 8
        self.assertTrue(ime.set_native(True))
        self.assertEqual(ime.mode, 1)

    def test_space_preserves_native_language_and_other_conversion_flags(self):
        ime = FakeIme(mode=1 | 8 | 0x40)
        self.assertTrue(ime.ensure_half_width())
        self.assertEqual(ime.mode, 1 | 0x40)
        self.assertFalse(any(command == 6 for command, value in ime.calls))

    def test_already_normal_space_does_not_reset_the_input_context(self):
        ime = FakeIme(mode=1)
        self.assertTrue(ime.ensure_half_width())
        self.assertEqual(ime.calls, [(1, 0)])

    def test_blocked_ime_width_change_reports_failure(self):
        ime = FakeIme()
        original = ime.command
        ime.command = lambda window, command, value=0: None if command == 2 else original(window, command, value)
        self.assertFalse(ime.ensure_half_width())
        self.assertEqual(ime.mode, 9)

    def test_only_injected_plain_space_down_requests_width_correction(self):
        self.assertTrue(is_plain_remote_space(0x20, 0, 0x10, 0))
        self.assertTrue(is_plain_remote_space(0xE7, 0x20, 0x10, 0))
        self.assertFalse(is_plain_remote_space(0x20, 0, 0, 0))
        self.assertFalse(is_plain_remote_space(0x20, 0, 0x90, 0))
        self.assertFalse(is_plain_remote_space(0x20, 0, 0x10, MARKER))
        self.assertFalse(is_plain_remote_space(0x20, 0, 0x10, 0, shortcut=True))

    def test_explicit_unicode_full_width_space_is_preserved(self):
        self.assertFalse(is_plain_remote_space(0xE7, 0x3000, 0x10, 0))


if __name__ == '__main__':
    unittest.main()
