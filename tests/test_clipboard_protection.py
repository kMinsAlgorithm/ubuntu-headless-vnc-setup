"""Clipboard profile migration and recovery, with no real desktop changes."""
import unittest
from unittest.mock import patch
import test_keyboard_mode as base
k = base.k


class ClipboardTests(unittest.TestCase):
    setUp = base.KeyboardModeTests.setUp

    def receive(self, clipboard='1', primary='1'):
        self.backend.current_vnc.update(setclipboard=clipboard, setprimary=primary)

    def test_protection_toggle_restores_original_receive_flags(self):
        self.receive(primary='0')
        original = self.backend.vnc()
        k.enable_mode(self.backend, protect_clipboard=True)
        self.assertEqual(self.backend.vnc()['setclipboard'], '0')
        k.enable_mode(self.backend, protect_clipboard=False)
        self.assertEqual(self.backend.vnc()['setclipboard'], '1')
        self.assertEqual(self.backend.vnc()['setprimary'], '0')
        k.disable_mode(self.backend)
        self.assertEqual(self.backend.vnc(), original)

    def test_direct_mode_restores_receive_and_remembers_preference(self):
        self.receive()
        original = self.backend.vnc()
        k.enable_mode(self.backend, protect_clipboard=True)
        k.disable_mode(self.backend)
        self.assertEqual(self.backend.vnc(), original)
        k.enable_mode(self.backend)
        self.assertEqual(self.backend.vnc()['setclipboard'], '0')
        self.assertEqual(self.backend.vnc()['setprimary'], '0')

    def test_upgrade_captures_only_new_fields_without_replacing_original_keys(self):
        original = self.backend.vnc()
        k.enable_mode(self.backend)
        self.receive(primary='0')
        k.enable_mode(self.backend, protect_clipboard=True)
        k.disable_mode(self.backend)
        self.assertEqual(self.backend.vnc(), {**original, 'setclipboard': '1', 'setprimary': '0'})

    def test_off_of_legacy_profile_does_not_change_clipboard_settings(self):
        original = self.backend.vnc()
        k.enable_mode(self.backend)
        self.receive(clipboard='0')
        k.disable_mode(self.backend)
        self.assertEqual(self.backend.vnc(), {**original, 'setclipboard': '0', 'setprimary': '1'})

    def test_failed_upgrade_restores_previous_state_and_clipboard(self):
        k.enable_mode(self.backend)
        previous = k.load_state()
        self.receive()
        before = self.backend.vnc()
        self.backend.fail_once = True
        with self.assertRaisesRegex(RuntimeError, 'simulated'):
            k.enable_mode(self.backend, protect_clipboard=True)
        self.assertEqual(k.load_state(), previous)
        self.assertEqual(self.backend.vnc(), before)

    def test_new_server_uses_its_own_clipboard_baseline(self):
        self.receive()
        k.enable_mode(self.backend, protect_clipboard=True)
        self.backend.current_vnc = {'identity': 'newboot:12:30', 'remap': '',
                                    'skip_lockkeys': '0', 'setclipboard': '0', 'setprimary': '1'}
        original = self.backend.vnc()
        k.enable_mode(self.backend)
        self.assertEqual(self.backend.vnc()['setprimary'], '0')
        k.disable_mode(self.backend)
        self.assertEqual(self.backend.vnc(), original)

    def test_clipboard_only_change_preserves_caps_generation_and_key_mapping(self):
        backend = k.Backend.__new__(k.Backend)
        current = {'identity': 'boot:10:20', 'remap': 'Alt_L-Control_L',
                   'skip_lockkeys': '0', 'caps_bridge': '1', 'setclipboard': '1', 'setprimary': '1'}
        target = {**current, 'setclipboard': '0', 'setprimary': '0'}
        with patch.object(backend, 'vnc', side_effect=[current, target]), \
             patch.object(k, 'run') as run, patch.object(k, 'x_cardinal', return_value=[10, 1]) as cardinal:
            backend.set_vnc(target)
        self.assertEqual([call.args[-1] for call in run.call_args_list], ['nosetclipboard', 'nosetprimary'])
        cardinal.assert_called_once_with('_VNC_KEYBOARD_CAPS_BRIDGE')
