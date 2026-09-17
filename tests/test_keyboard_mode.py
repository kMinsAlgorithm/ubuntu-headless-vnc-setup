"""Settings transaction tests; no live keyboard or home-directory changes."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('keyboard_mode_test', Path(__file__).resolve().parents[1] / 'keyboard-mode/keyboard_mode.py')
k = importlib.util.module_from_spec(spec)
spec.loader.exec_module(k)


class FakeBackend:
    def __init__(self):
        self.current_ime = {'value': 'Hangul,Super_R,Alt_L', 'user': None}
        self.current_vnc = {'identity': 'boot:10:20', 'remap': 'F8-F9', 'skip_lockkeys': '1'}
        self.caps = True
        self.fail_once = False

    def ime(self):
        return dict(self.current_ime)

    def vnc(self):
        return dict(self.current_vnc)

    def set_ime(self, value):
        self.current_ime = dict(value)
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError('simulated settings failure')

    def set_vnc(self, value):
        self.current_vnc = dict(value)

    def clear_caps(self):
        self.caps = False


class KeyboardModeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        for name, value in [('STATE_DIR', self.folder), ('STATE_FILE', self.folder / 'state.json')]:
            override = patch.object(k, name, value)
            override.start()
            self.addCleanup(override.stop)
        self.backend = FakeBackend()

    def test_enable_disable_restores_exact_user_unset_state_and_other_remaps(self):
        ime, vnc = self.backend.ime(), self.backend.vnc()
        k.enable_mode(self.backend)
        self.assertEqual(self.backend.current_ime, k.TARGET_IME)
        self.assertTrue(self.backend.current_vnc['remap'].startswith('F8-F9,Caps_Lock-Hangul,'))
        self.assertEqual(self.backend.current_vnc['skip_lockkeys'], '0')
        self.assertFalse(self.backend.caps)
        k.disable_mode(self.backend)
        self.assertEqual(self.backend.ime(), ime)
        self.assertEqual(self.backend.vnc(), vnc)
        self.assertFalse(k.load_state()['enabled'])

    def test_repeated_enable_preserves_original_baseline(self):
        before = self.backend.ime(), self.backend.vnc()
        k.enable_mode(self.backend)
        k.enable_mode(self.backend)
        k.disable_mode(self.backend)
        self.assertEqual((self.backend.ime(), self.backend.vnc()), before)
        self.assertEqual(len(list(self.folder.glob('backup-*.json'))), 1)

    def test_partial_enable_failure_rolls_back(self):
        before = self.backend.ime(), self.backend.vnc()
        self.backend.fail_once = True
        with self.assertRaisesRegex(RuntimeError, 'simulated'):
            k.enable_mode(self.backend)
        self.assertEqual((self.backend.ime(), self.backend.vnc()), before)
        self.assertFalse(k.load_state()['enabled'])

    def test_external_ime_edit_is_not_overwritten_on_enable_or_disable(self):
        k.enable_mode(self.backend)
        self.backend.current_ime = {'value': 'F12', 'user': 'F12'}
        for operation in (k.enable_mode, k.disable_mode):
            with self.assertRaisesRegex(RuntimeError, '외부'):
                operation(self.backend)
            self.assertEqual(self.backend.current_ime['value'], 'F12')

    def test_external_vnc_edit_is_not_overwritten(self):
        k.enable_mode(self.backend)
        self.backend.current_vnc['remap'] = 'F10-F11'
        with self.assertRaisesRegex(RuntimeError, '외부'):
            k.disable_mode(self.backend)
        self.assertEqual(self.backend.current_vnc['remap'], 'F10-F11')

    def test_new_server_gets_its_own_restore_baseline(self):
        old_ime = self.backend.ime()
        k.enable_mode(self.backend)
        self.backend.current_vnc = {'identity': 'newboot:12:30', 'remap': 'F2-F3', 'skip_lockkeys': '0'}
        new_vnc = self.backend.vnc()
        k.enable_mode(self.backend)
        k.disable_mode(self.backend)
        self.assertEqual(self.backend.vnc(), new_vnc)
        self.assertEqual(self.backend.ime(), old_ime)

    def test_off_does_not_restore_options_into_an_unmanaged_new_server(self):
        k.enable_mode(self.backend)
        self.backend.current_vnc = {'identity': 'newboot:12:30', 'remap': 'F2-F3', 'skip_lockkeys': '0'}
        expected = self.backend.vnc()
        k.disable_mode(self.backend)
        self.assertEqual(self.backend.vnc(), expected)

    def test_remap_files_are_rejected_before_mutation(self):
        before = self.backend.ime()
        self.backend.current_vnc['remap'] = '/private/custom-remap'
        with self.assertRaisesRegex(RuntimeError, '특수 형식'):
            k.enable_mode(self.backend)
        self.assertEqual(self.backend.ime(), before)
        self.assertIsNone(k.load_state())

    def test_conflicting_caps_mapping_is_restored(self):
        self.backend.current_vnc['remap'] = 'Caps_Lock-Escape,F8-F9'
        k.enable_mode(self.backend)
        self.assertTrue(self.backend.current_vnc['remap'].startswith('F8-F9,Caps_Lock-Hangul,'))
        k.disable_mode(self.backend)
        self.assertEqual(self.backend.current_vnc['remap'], 'Caps_Lock-Escape,F8-F9')

    def test_upgrade_enabled_caps_only_profile_preserves_original_settings(self):
        before = self.backend.ime(), self.backend.vnc()
        with patch.object(k, 'remap_for_vnc', return_value='F8-F9,Caps_Lock-Hangul'):
            k.enable_mode(self.backend)
        k.enable_mode(self.backend)
        self.assertIn('U3131-r', self.backend.vnc()['remap'])
        k.disable_mode(self.backend)
        self.assertEqual((self.backend.ime(), self.backend.vnc()), before)
        self.assertEqual(len(list(self.folder.glob('backup-*.json'))), 1)

    def test_jamo_alias_conflicts_restore_and_other_keys_stay_untouched(self):
        original = 'Hangul_Kiyeog-F1,0x01003131-F2,U314F-F3,0xFFE5-Escape,F8-F9'
        self.backend.current_vnc['remap'] = original
        k.enable_mode(self.backend)
        actual = self.backend.vnc()['remap']
        self.assertNotIn('-F1', actual)
        self.assertNotIn('-F2', actual)
        self.assertNotIn('-F3', actual)
        self.assertNotIn('-Escape', actual)
        self.assertTrue(actual.startswith('F8-F9,Caps_Lock-Hangul,'))
        self.assertIn('U3143-Q', actual)  # Deliberately shifted ㅃ must remain shifted.
        self.assertNotIn('U3133-', actual)  # Compound ㄳ is not one keystroke.
        self.assertNotIn('UAC00-', actual)  # Committed 가 is not a keystroke.
        self.assertNotIn('A-a', actual)  # Do not erase actual Shift/case.
        k.disable_mode(self.backend)
        self.assertEqual(self.backend.vnc()['remap'], original)

    def test_upgrade_failure_restores_previous_enabled_profile(self):
        with patch.object(k, 'remap_for_vnc', return_value='F8-F9,Caps_Lock-Hangul'):
            k.enable_mode(self.backend)
        old_state = k.load_state()
        before = self.backend.ime(), self.backend.vnc()
        self.backend.fail_once = True
        with self.assertRaisesRegex(RuntimeError, 'simulated'):
            k.enable_mode(self.backend)
        self.assertEqual((self.backend.ime(), self.backend.vnc()), before)
        self.assertEqual(k.load_state(), old_state)

    def test_optional_caps_bridge_enables_and_restores_exact_baseline(self):
        self.backend.current_vnc['caps_bridge'] = '0'
        before = self.backend.vnc()
        k.enable_mode(self.backend)
        self.assertEqual(self.backend.vnc()['caps_bridge'], '1')
        k.disable_mode(self.backend)
        self.assertEqual(self.backend.vnc(), before)

    def test_stale_optional_bridge_setting_is_not_accepted(self):
        self.backend.current_vnc['caps_bridge'] = '0'
        k.enable_mode(self.backend)
        self.backend.current_vnc['caps_bridge'] = 'unrecognized'
        with self.assertRaisesRegex(RuntimeError, '외부'):
            k.enable_mode(self.backend)
        with self.assertRaisesRegex(RuntimeError, '외부'):
            k.disable_mode(self.backend)

    def test_command_mapping_restores_aliases_without_swapping_physical_control(self):
        original = 'Alt_L-Super_L,0xFFE9-Meta_L,Meta_L-Alt_R,F8-F9'
        self.backend.current_vnc['remap'] = original
        k.enable_mode(self.backend)
        active = self.backend.vnc()['remap'].split(',')
        self.assertIn('Alt_L-Control_L', active)
        self.assertIn('Meta_L-Alt_R', active)
        self.assertIn('F8-F9', active)
        self.assertNotIn('Alt_L-Super_L', active)
        self.assertNotIn('0xFFE9-Meta_L', active)
        self.assertFalse(any(pair.startswith('Control_L-') for pair in active))
        self.assertFalse(any(pair.startswith('Super_L-') for pair in active))
        k.disable_mode(self.backend)
        self.assertEqual(self.backend.vnc()['remap'], original)

    def test_backup_is_private(self):
        k.enable_mode(self.backend)
        for path in self.folder.glob('*.json'):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
